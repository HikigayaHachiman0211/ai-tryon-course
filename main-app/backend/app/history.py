"""History management – dual-write to Cloud Run local disk (/tmp) and GCS.

Local disk is the *primary* fast path; GCS is the durable secondary store.
When GCS is unavailable the system continues to work using local-only storage.
"""

from __future__ import annotations

import io
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from app import gcs_storage
from app.catalog_seed import resolve_local_image_path
from app.database import PROJECT_ROOT

logger = logging.getLogger(__name__)

LOCAL_HISTORY_DIR = Path(os.getenv("HISTORY_DIR", "/tmp/history"))
LOCAL_RESULTS_DIR = LOCAL_HISTORY_DIR / "results"
LOCAL_THUMBS_DIR = LOCAL_HISTORY_DIR / "thumbnails"
LOCAL_INDEX_PATH = LOCAL_HISTORY_DIR / "index.json"

MAX_HISTORY_ENTRIES = 5000
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
    LOCAL_INDEX_PATH.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_result_id() -> str:
    """Create a unique result id (timestamp + random)."""
    ts = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d%H%M%S")
    return f"{ts}-{uuid.uuid4().hex[:8]}"


def build_summary(result: dict[str, Any], result_type: str) -> str:
    """Create a one-line summary string from a result payload."""
    if result_type == "recommend":
        items = result.get("items", [])
        inference = result.get("inference", {})
        size = inference.get("resolved_size", "?")
        style = inference.get("resolved_style", "?")
        return f"推荐 {len(items)} 件 · 尺码 {size} · {style}"

    if result_type == "style-lab":
        analysis = result.get("analysis", {})
        product = result.get("product", {})
        score = analysis.get("total_score", 0)
        title = product.get("title", "未知商品")
        return f"{title[:20]} · 评分 {score:.1f}"

    return "分析记录"


def save_history(
    result: dict[str, Any],
    result_type: str,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Persist a result and return the history entry metadata.

    Writes to both local disk AND GCS (best-effort on GCS).
    """
    _ensure_local_dirs()
    result_id = generate_result_id()

    # 1. Save result JSON locally
    local_result_path = LOCAL_RESULTS_DIR / f"{result_id}.json"
    local_result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 2. Save result JSON to GCS (best-effort)
    gcs_storage.save_result_json(result_id, result)

    # 3. Generate and save thumbnail
    thumbnail_url: str | None = None
    image_url = _resolve_first_image_url(result, base_url)
    if image_url:
        raw_bytes = _download_image_bytes(image_url)
        if raw_bytes:
            thumb_bytes = _make_thumbnail(raw_bytes)
            if thumb_bytes:
                # Save thumbnail locally
                local_thumb_path = LOCAL_THUMBS_DIR / f"{result_id}.png"
                local_thumb_path.write_bytes(thumb_bytes)

                thumbnail_url = f"{base_url.rstrip('/')}/api/history/{result_id}/thumbnail" if base_url else f"/api/history/{result_id}/thumbnail"

                # Upload to GCS (best-effort)
                gcs_url = gcs_storage.save_thumbnail(result_id, thumb_bytes)
                if gcs_url:
                    thumbnail_url = gcs_url

    # 4. Build history entry
    entry = {
        "id": result_id,
        "timestamp": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "type": result_type,
        "summary": build_summary(result, result_type),
        "thumbnail_url": thumbnail_url,
        "item_count": len(result.get("items", [])) if result_type == "recommend" else 1,
        "total_score": (
            result.get("analysis", {}).get("total_score")
            if result_type == "style-lab"
            else None
        ),
    }

    # 5. Update local index
    entries = _read_local_index()
    entries.insert(0, entry)
    entries = entries[:MAX_HISTORY_ENTRIES]
    _write_local_index(entries)

    # 6. Sync index to GCS (best-effort)
    gcs_storage.save_history_index(entries)

    return entry


def list_history(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent history entries.

    Tries local index first, falls back to GCS if local is empty.
    """
    entries = _read_local_index()
    if not entries:
        gcs_entries = gcs_storage.load_history_index()
        if gcs_entries:
            entries = gcs_entries
            # Repopulate local cache
            _write_local_index(entries)

    return entries[:limit]


def get_history_detail(result_id: str) -> dict[str, Any] | None:
    """Load a specific result by id.

    Tries local first, then GCS.
    """
    local_path = LOCAL_RESULTS_DIR / f"{result_id}.json"
    if local_path.exists():
        try:
            return json.loads(local_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    return gcs_storage.get_result_json(result_id)


def get_thumbnail_path(result_id: str) -> Path | None:
    """Return the local thumbnail path, or None."""
    local_path = LOCAL_THUMBS_DIR / f"{result_id}.png"
    return local_path if local_path.exists() else None
