"""Backward-compatible history helper backed by the selected object provider."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from typing import Any

from app.object_storage import get_object_storage, load_object_storage_settings

logger = logging.getLogger(__name__)
GCS_BUCKET_NAME: str | None = os.getenv("GCS_BUCKET_NAME") or None
GCS_RESULT_PREFIX: str = os.getenv("GCS_RESULT_PREFIX", "ai-tryon-results").strip("/")
_USER_PHOTO_EPHEMERAL_SECRET = secrets.token_hex(32)
_SAFE_MEDIA_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _media_signing_secret() -> bytes:
    secret = (
        os.getenv("USER_PHOTO_TOKEN_SECRET")
        or os.getenv("TASK_TOKEN_SECRET")
        or os.getenv("INGEST_SECRET_KEY")
        or os.getenv("FERNET_SECRET_KEY")
        or os.getenv("JWT_SECRET_KEY")
        or _USER_PHOTO_EPHEMERAL_SECRET
    )
    return secret.encode("utf-8")


def build_signed_user_photo_url(photo_name: str, ttl_seconds: int = 3600) -> str:
    clean_name = str(photo_name or "").strip().lstrip("/")
    expires = int(time.time()) + max(60, int(ttl_seconds))
    sig = hmac.new(
        _media_signing_secret(),
        f"user_photo:{clean_name}:{expires}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    return f"/api/media/user-photos/{clean_name}?st={expires}.{sig}"


def verify_signed_user_photo_token(photo_name: str, token: str | None) -> bool:
    clean_name = str(photo_name or "").strip()
    if not clean_name or not _SAFE_MEDIA_NAME_RE.match(clean_name) or ".." in clean_name:
        return False
    raw = str(token or "").strip()
    if "." not in raw:
        return False
    exp_str, sig = raw.split(".", 1)
    try:
        expires = int(exp_str)
    except ValueError:
        return False
    if expires < int(time.time()):
        return False
    expected = hmac.new(
        _media_signing_secret(),
        f"user_photo:{clean_name}:{expires}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    return hmac.compare_digest(expected, sig)


def _object_name(kind: str, value: str | None = None) -> str:
    parts = [GCS_RESULT_PREFIX, kind]
    if value:
        parts.append(str(value).lstrip("/"))
    return "/".join(part for part in parts if part)


def _ensure_bucket():
    """Compatibility hook for old callers; it returns the selected adapter."""
    return get_object_storage()


def save_result_json(result_id: str, payload: dict[str, Any]) -> str | None:
    try:
        return get_object_storage().upload_bytes(
            _object_name("results", f"{result_id}.json"),
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            content_type="application/json",
            cache_control="no-store",
        )
    except Exception as exc:
        logger.warning("Failed to save result JSON to object storage: %s", type(exc).__name__)
        return None


def get_result_json(result_id: str) -> dict[str, Any] | None:
    try:
        data = get_object_storage().download_bytes(_object_name("results", f"{result_id}.json"))
        return json.loads(data.decode("utf-8")) if data else None
    except Exception as exc:
        logger.warning("Failed to read result JSON from object storage: %s", type(exc).__name__)
        return None


def save_user_photo(result_id: str, image_bytes: bytes, content_type: str = "image/jpeg") -> str | None:
    normalized_type = str(content_type or "").lower()
    ext = "png" if "png" in normalized_type else ("webp" if "webp" in normalized_type else "jpg")
    photo_name = f"{result_id}.{ext}"
    try:
        storage = get_object_storage()
        uploaded_url = storage.upload_bytes(
            _object_name("user_photos", photo_name),
            image_bytes,
            content_type=content_type,
            cache_control="no-store, max-age=0",
        )
        provider = getattr(getattr(storage, "settings", None), "provider", "")
        force_private = os.getenv("FORCE_PRIVATE_USER_PHOTOS", "").strip().lower() in ("1", "true", "yes")
        if provider == "azure" and not os.getenv("PUBLIC_MEDIA_BASE_URL", "").strip():
            # Azure media container is private; never expose product-container or private Blob URLs.
            force_private = True
        if uploaded_url and not force_private:
            return uploaded_url
        return build_signed_user_photo_url(photo_name)
    except Exception as exc:
        logger.warning("Failed to save user photo to object storage: %s", type(exc).__name__)
        return None


def get_user_photo(photo_name: str) -> tuple[bytes, str] | None:
    clean_name = str(photo_name or "").strip()
    if not clean_name or not _SAFE_MEDIA_NAME_RE.match(clean_name) or ".." in clean_name:
        return None
    try:
        data = get_object_storage().download_bytes(_object_name("user_photos", clean_name))
        if not data:
            return None
        lower = clean_name.lower()
        content_type = (
            "image/png" if lower.endswith(".png")
            else ("image/webp" if lower.endswith(".webp") else "image/jpeg")
        )
        return data, content_type
    except Exception as exc:
        logger.warning("Failed to read user photo from object storage: %s", type(exc).__name__)
        return None


def save_thumbnail(result_id: str, image_bytes: bytes, content_type: str = "image/png") -> str | None:
    try:
        return get_object_storage().upload_bytes(
            _object_name("thumbnails", f"{result_id}.png"),
            image_bytes,
            content_type=content_type,
            cache_control="no-store, max-age=0",
        )
    except Exception as exc:
        logger.warning("Failed to save thumbnail to object storage: %s", type(exc).__name__)
        return None


def get_thumbnail(result_id: str) -> bytes | None:
    try:
        data = get_object_storage().download_bytes(_object_name("thumbnails", f"{result_id}.png"))
        return data or None
    except Exception as exc:
        logger.warning("Failed to read thumbnail from object storage: %s", type(exc).__name__)
        return None


def delete_history_blobs(result_id: str) -> None:
    storage = get_object_storage()
    for name in (
        _object_name("results", f"{result_id}.json"),
        _object_name("thumbnails", f"{result_id}.png"),
        _object_name("user_photos", f"{result_id}.jpg"),
        _object_name("user_photos", f"{result_id}.png"),
    ):
        try:
            storage.delete_blob(name)
        except Exception:
            pass


def save_history_index(entries: list[dict[str, Any]], retries: int = 3) -> bool:
    payload = json.dumps(entries, ensure_ascii=False, indent=2).encode("utf-8")
    for attempt in range(max(1, retries)):
        try:
            get_object_storage().upload_bytes(
                _object_name("history_index.json"),
                payload,
                content_type="application/json",
                cache_control="no-store",
            )
            return True
        except Exception as exc:
            logger.warning("Object storage history upload failed on attempt %d: %s", attempt + 1, type(exc).__name__)
    return False


def load_history_index() -> list[dict[str, Any]] | None:
    try:
        data = get_object_storage().download_bytes(_object_name("history_index.json"))
        if not data:
            return []
        value = json.loads(data.decode("utf-8"))
        return value if isinstance(value, list) else []
    except Exception as exc:
        logger.warning("Failed to load history index from object storage: %s", type(exc).__name__)
        return None


def health_check() -> dict[str, Any]:
    settings = load_object_storage_settings()
    return get_object_storage().health_check() | {"container": settings.container}
