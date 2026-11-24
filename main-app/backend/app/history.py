"""History management – dual-write to Cloud Run local disk (/tmp) and GCS.

Local disk is the *primary* fast path; GCS is the durable secondary store.
When GCS is unavailable the system continues to work using local-only storage.
"""

from __future__ import annotations

import io
import json
import logging
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
from sqlalchemy import desc, select

from app import gcs_storage
from app.catalog_seed import resolve_local_image_path
from app.database import DEFAULT_SQLITE_PATH, ENGINE, PROJECT_ROOT, RecommendationHistory, SessionLocal
from app.i18n.catalog import localize_recommendation_result, localize_style_lab_result
from app.i18n.catalog_assets import get_catalog_translation
from app.i18n.domain_labels import localized_style
from app.i18n.locale import DEFAULT_LOCALE, normalize_locale
from app.i18n.messages import history_message

logger = logging.getLogger(__name__)

_DEFAULT_LOCAL_HISTORY_DIR = Path(os.getenv("HISTORY_DIR", "/tmp/history"))
LOCAL_HISTORY_DIR = _DEFAULT_LOCAL_HISTORY_DIR
LOCAL_RESULTS_DIR = LOCAL_HISTORY_DIR / "results"
LOCAL_THUMBS_DIR = LOCAL_HISTORY_DIR / "thumbnails"
LOCAL_INDEX_PATH = LOCAL_HISTORY_DIR / "index.json"

MAX_HISTORY_ENTRIES = 5000
_INDEX_LOCK = threading.RLock()
LOCAL_PRODUCT_IMAGE_DIR = PROJECT_ROOT / "downloaded_jd_images" / "羽绒服_png"


def _ensure_local_dirs() -> None:
    LOCAL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_THUMBS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Thumbnail generation
# ---------------------------------------------------------------------------

def _read_local_product_image(url: str) -> bytes | None:
    path = unquote(urlparse(url).path)
    if not path.startswith("/static/products/"):
        return None

    image_path = resolve_local_image_path(path.removeprefix("/static/products/"))
    if image_path is None:
        return None

    try:
        return image_path.read_bytes()
    except OSError as exc:
        logger.warning("Failed to read local product image for thumbnail: %s", exc)
        return None


def _download_image_bytes(url: str) -> bytes | None:
    """Download an image from a URL (product image). Returns None on failure."""
    local_bytes = _read_local_product_image(url)
    if local_bytes is not None:
        return local_bytes

    try:
        response = httpx.get(url, timeout=10, follow_redirects=True)
        response.raise_for_status()
        return response.content
    except Exception as exc:
        logger.warning("Failed to download image for thumbnail: %s", exc)
        return None


def _make_thumbnail(image_bytes: bytes, size: tuple[int, int] = (120, 160)) -> bytes | None:
    """Resize image bytes to a thumbnail. Returns PNG bytes or None on failure."""
    try:
        from PIL import Image  # type: ignore[import-untyped]

        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail(size, Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:
        logger.warning("Thumbnail generation failed: %s", exc)
        return None


def _resolve_first_image_url(result: dict[str, Any], base_url: str | None = None) -> str | None:
    """Extract the first product image URL from a recommendation / style-lab result."""
    # Recommendation result
    items = result.get("items")
    if items and isinstance(items, list) and len(items) > 0:
        url = items[0].get("image_url", "")
        if url:
            return _absolutify(url, base_url)

    # Style-lab result
    product = result.get("product")
    if product and isinstance(product, dict):
        url = product.get("image_url", "")
        if url:
            return _absolutify(url, base_url)

    return None


def _absolutify(url: str, base_url: str | None) -> str:
    if url.startswith(("http://", "https://")):
        return url
    if base_url:
        return f"{base_url.rstrip('/')}/{url.lstrip('/')}"
    return url


# ---------------------------------------------------------------------------
# Local index helpers
# ---------------------------------------------------------------------------

def _read_local_index() -> list[dict[str, Any]]:
    if not LOCAL_INDEX_PATH.exists():
        return []
    try:
        return json.loads(LOCAL_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write_local_index(entries: list[dict[str, Any]]) -> None:
    _ensure_local_dirs()
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=LOCAL_INDEX_PATH.parent,
                                         prefix=".history-index-", delete=False) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(entries, temporary, ensure_ascii=False, indent=2)
        os.replace(temporary_path, LOCAL_INDEX_PATH)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_result_id() -> str:
    """Create a unique result id (timestamp + random)."""
    ts = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d%H%M%S")
    return f"{ts}-{uuid.uuid4().hex[:8]}"


def build_summary(result: dict[str, Any], result_type: str, locale: str = DEFAULT_LOCALE) -> str:
    """Create a one-line summary string from a result payload."""
    if result_type == "recommend":
        items = result.get("items", [])
        inference = result.get("inference", {})
        size = (inference.get("display") or {}).get("size") or inference.get("resolved_size", "?")
        style = (inference.get("display") or {}).get("style") or localized_style(str(inference.get("resolved_style") or ""), locale)
        return history_message("recommend", locale, count=len(items), size=size, style=style)

    if result_type == "style-lab":
        analysis = result.get("analysis", {})
        product = result.get("product", {})
        score = analysis.get("total_score", 0)
        title = (product.get("display") or {}).get("title") or product.get("title", "Unknown product")
        return history_message("styleLab", locale, title=str(title)[:40], score=f"{score:.1f}")

    return history_message("legacy", locale, id="unknown")


def _summary_params(result: dict[str, Any], result_type: str) -> dict[str, Any]:
    inference = result.get("inference") or {}
    product = result.get("product") or {}
    first_item = (result.get("items") or [{}])[0] if isinstance(result.get("items") or [{}], list) else {}
    return {
        "count": len(result.get("items") or []) if result_type == "recommend" else 1,
        "size": inference.get("resolved_size") or "?",
        "style": inference.get("resolved_style") or "",
        "product_key": product.get("product_key") or first_item.get("product_key"),
        "product_id": product.get("id") or first_item.get("id"),
        "title": product.get("title") or first_item.get("title"),
        "score": float((result.get("analysis") or {}).get("total_score") or 0),
    }


def _localized_entry_summary(entry: dict[str, Any], locale: str) -> str:
    params = entry.get("summary_params")
    if not isinstance(params, dict):
        return history_message("legacy", locale, id=entry.get("id", "unknown"))
    result_type = entry.get("type")
    if result_type == "recommend":
        return history_message(
            "recommend",
            locale,
            count=params.get("count", 0),
            size=params.get("size") or "?",
            style=localized_style(str(params.get("style") or ""), locale),
        )
    title = params.get("title") or "Unknown product"
    product_key = params.get("product_key")
    if product_key:
        translation = get_catalog_translation(str(product_key), locale)
        if translation and translation.get("title"):
            title = translation["title"]
    return history_message("styleLab", locale, title=str(title)[:40], score=f"{float(params.get('score') or 0):.1f}")


def localize_history_result(result: dict[str, Any], locale: str) -> dict[str, Any]:
    payload = dict(result)
    payload.pop("history_snapshot", None)
    if result.get("result_type") == "style-lab" or result.get("analysis"):
        return localize_style_lab_result(payload, locale)
    return localize_recommendation_result(payload, locale)


def _db_history_enabled() -> bool:
    """Enable DB persistence unless an isolated local test patched HISTORY_DIR without patching DB."""
    if os.getenv("HISTORY_DB_ENABLED", "").strip().lower() in ("1", "true", "yes"):
        return True
    if ENGINE.dialect.name != "sqlite":
        return True
    default_db = str(DEFAULT_SQLITE_PATH).replace("\\", "/")
    current_db = str(ENGINE.url).replace("\\", "/")
    if default_db not in current_db:
        return True
    return LOCAL_HISTORY_DIR == _DEFAULT_LOCAL_HISTORY_DIR


def _ensure_history_table() -> None:
    RecommendationHistory.__table__.create(bind=ENGINE, checkfirst=True)


def _persist_history_db(
    entry: dict[str, Any],
    persisted_result: dict[str, Any],
    *,
    has_thumbnail: bool,
    user_photo_blob_path: str | None = None,
) -> None:
    if not _db_history_enabled():
        return
    try:
        _ensure_history_table()
        result_id = str(entry["id"])
        thumb_blob = f"{gcs_storage.GCS_RESULT_PREFIX}/thumbnails/{result_id}.png" if has_thumbnail else None
        result_blob = f"{gcs_storage.GCS_RESULT_PREFIX}/results/{result_id}.json"
        payload_text = json.dumps(persisted_result, ensure_ascii=False)
        with SessionLocal() as session:
            row = session.get(RecommendationHistory, result_id)
            if row is None:
                row = RecommendationHistory(
                    id=result_id,
                    created_at=str(entry.get("timestamp") or ""),
                    result_type=str(entry.get("type") or "recommend"),
                    summary=str(entry.get("summary") or "")[:512],
                    summary_params=entry.get("summary_params"),
                    translation_version=str(entry.get("translation_version") or "catalog-v1"),
                    created_locale=str(entry.get("created_locale") or DEFAULT_LOCALE),
                    thumbnail_blob_path=thumb_blob,
                    result_blob_path=result_blob,
                    user_photo_blob_path=user_photo_blob_path,
                    item_count=int(entry.get("item_count") or 1),
                    total_score=entry.get("total_score"),
                    payload_json=payload_text,
                )
                session.add(row)
            else:
                row.summary = str(entry.get("summary") or "")[:512]
                row.summary_params = entry.get("summary_params")
                row.thumbnail_blob_path = thumb_blob or row.thumbnail_blob_path
                row.payload_json = payload_text
            session.commit()
    except Exception as exc:
        logger.warning("Failed to persist recommendation history to DB: %s", type(exc).__name__)


def _list_history_db(limit: int) -> list[dict[str, Any]] | None:
    if not _db_history_enabled():
        return None
    try:
        _ensure_history_table()
        with SessionLocal() as session:
            rows = session.scalars(
                select(RecommendationHistory)
                .order_by(desc(RecommendationHistory.created_at))
                .limit(max(1, limit))
            ).all()
        if not rows:
            return []
        items: list[dict[str, Any]] = []
        for row in rows:
            items.append(
                {
                    "id": row.id,
                    "timestamp": row.created_at,
                    "type": row.result_type,
                    "summary": row.summary,
                    "summary_params": row.summary_params,
                    "translation_version": row.translation_version,
                    "created_locale": row.created_locale,
                    "thumbnail_url": f"/api/history/{row.id}/thumbnail" if row.thumbnail_blob_path else None,
                    "item_count": row.item_count,
                    "total_score": row.total_score,
                }
            )
        return items
    except Exception as exc:
        logger.warning("Failed to query recommendation history from DB: %s", type(exc).__name__)
        return None


def _get_history_detail_db(result_id: str) -> dict[str, Any] | None:
    if not _db_history_enabled():
        return None
    try:
        _ensure_history_table()
        with SessionLocal() as session:
            row = session.get(RecommendationHistory, result_id)
        if row is not None and row.payload_json:
            return json.loads(row.payload_json)
    except Exception as exc:
        logger.warning("Failed to load history detail from DB: %s", type(exc).__name__)
    return None


def save_history(
    result: dict[str, Any],
    result_type: str,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Persist a result and return the history entry metadata.

    Writes to PostgreSQL/SQLite DB, local disk, and Object Storage (private Blob).
    """
    _ensure_local_dirs()
    result_id = generate_result_id()

    # 1. Save the result plus a canonical/history contract locally.  The
    # localized fields remain backward-compatible cache data; readers rebuild
    # presentation from product_key and canonical fields for their locale.
    persisted_result = dict(result)
    persisted_result["result_type"] = result_type
    persisted_result["history_snapshot"] = {
        "created_locale": normalize_locale(str(result.get("locale") or DEFAULT_LOCALE)) or DEFAULT_LOCALE,
        "translation_version": "catalog-v1",
        "summary_params": _summary_params(result, result_type),
        "product_keys": [
            item.get("product_key")
            for item in (result.get("items") or [])
            if isinstance(item, dict) and item.get("product_key")
        ] or ([((result.get("product") or {}).get("product_key"))] if (result.get("product") or {}).get("product_key") else []),
    }
    local_result_path = LOCAL_RESULTS_DIR / f"{result_id}.json"
    local_result_path.write_text(
        json.dumps(persisted_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 2. Save result JSON to object storage (best-effort)
    gcs_storage.save_result_json(result_id, persisted_result)

    # 3. Generate and save thumbnail (always route frontend access via backend proxy)
    thumbnail_url: str | None = None
    has_thumbnail = False
    image_url = _resolve_first_image_url(result, base_url)
    if image_url:
        raw_bytes = _download_image_bytes(image_url)
        if raw_bytes:
            thumb_bytes = _make_thumbnail(raw_bytes)
            if thumb_bytes:
                has_thumbnail = True
                # Save thumbnail locally
                local_thumb_path = LOCAL_THUMBS_DIR / f"{result_id}.png"
                local_thumb_path.write_bytes(thumb_bytes)

                thumbnail_url = f"/api/history/{result_id}/thumbnail"

                # Upload to private object storage (best-effort)
                gcs_storage.save_thumbnail(result_id, thumb_bytes)

    # 4. Build history entry
    entry = {
        "id": result_id,
        "timestamp": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "type": result_type,
        "summary": build_summary(result, result_type, normalize_locale(str(result.get("locale") or DEFAULT_LOCALE)) or DEFAULT_LOCALE),
        "summary_params": _summary_params(result, result_type),
        "translation_version": "catalog-v1",
        "created_locale": normalize_locale(str(result.get("locale") or DEFAULT_LOCALE)) or DEFAULT_LOCALE,
        "thumbnail_url": thumbnail_url,
        "item_count": len(result.get("items", [])) if result_type == "recommend" else 1,
        "total_score": (
            result.get("analysis", {}).get("total_score")
            if result_type == "style-lab"
            else None
        ),
    }

    # 5. Persist to shared DB (primary cross-replica source) + local/blob index cache
    _persist_history_db(entry, persisted_result, has_thumbnail=has_thumbnail)
    with _INDEX_LOCK:
        entries = _read_local_index()
        entries.insert(0, entry)
        entries = entries[:MAX_HISTORY_ENTRIES]
        _write_local_index(entries)
        gcs_storage.save_history_index(entries)

    return entry


def list_history(limit: int = 50, locale: str = DEFAULT_LOCALE) -> list[dict[str, Any]]:
    """Return the most recent history entries from shared DB, local index, or object storage."""
    entries = _list_history_db(limit)
    if not entries:
        with _INDEX_LOCK:
            entries = _read_local_index()
            if not entries:
                gcs_entries = gcs_storage.load_history_index()
                if gcs_entries:
                    entries = gcs_entries
                    _write_local_index(entries)

    normalized_locale = normalize_locale(locale) or DEFAULT_LOCALE
    localized_entries = []
    for entry in (entries or [])[:limit]:
        localized_entry = dict(entry)
        localized_entry["summary"] = _localized_entry_summary(localized_entry, normalized_locale)
        localized_entry["locale"] = normalized_locale
        localized_entries.append(localized_entry)
    return localized_entries


def _safe_history_path(root: Path, result_id: str, suffix: str) -> Path | None:
    if not isinstance(result_id, str) or not result_id.strip():
        return None
    decoded = result_id
    for _ in range(4):
        if decoded in (".", "..") or any(ch in decoded for ch in '/\\:*?"<>|\x00'):
            return None
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    else:
        return None
    try:
        root_path = root.resolve()
        local_path = (root_path / f"{result_id}{suffix}").resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    return local_path if local_path.is_relative_to(root_path) else None


def get_history_detail(result_id: str) -> dict[str, Any] | None:
    """Load a specific result by id.

    Tries local first, shared DB second, and object storage third.
    """
    local_path = _safe_history_path(LOCAL_RESULTS_DIR, result_id, ".json")
    if local_path is None:
        return None
    if local_path.exists():
        try:
            return json.loads(local_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    db_payload = _get_history_detail_db(result_id)
    if db_payload is not None:
        return db_payload

    return gcs_storage.get_result_json(result_id)


def get_thumbnail_path(result_id: str) -> Path | None:
    """Return the local thumbnail path, or None."""
    local_path = _safe_history_path(LOCAL_THUMBS_DIR, result_id, ".png")
    if local_path is None:
        return None
    return local_path if local_path.exists() else None


def get_thumbnail_bytes(result_id: str) -> bytes | None:
    """Return thumbnail bytes from local disk or private object storage."""
    local_path = get_thumbnail_path(result_id)
    if local_path is not None:
        try:
            return local_path.read_bytes()
        except OSError:
            pass
    if _safe_history_path(LOCAL_THUMBS_DIR, result_id, ".png") is None:
        return None
    return gcs_storage.get_thumbnail(result_id)
