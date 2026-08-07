"""GCS persistence layer – secondary storage for recommendation results and thumbnails.

All GCS operations are best-effort: failures are logged but never block the main
request flow.  When *GCS_BUCKET_NAME* is not set the module silently becomes a
no-op so local-only development works without any cloud credentials.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

GCS_BUCKET_NAME: str | None = os.getenv("GCS_BUCKET_NAME")
GCS_RESULT_PREFIX: str = os.getenv("GCS_RESULT_PREFIX", "ai-tryon-results")

_client = None
_bucket = None


def _ensure_bucket():
    """Lazy-initialise the GCS client and bucket handle."""
    global _client, _bucket  # noqa: PLW0603
    if _bucket is not None:
        return _bucket
    if not GCS_BUCKET_NAME:
        return None
    try:
        from google.cloud import storage  # type: ignore[import-untyped]

        _client = storage.Client()
        _bucket = _client.bucket(GCS_BUCKET_NAME)
        return _bucket
    except Exception as exc:
        logger.warning("GCS client init failed (will use local-only): %s", exc)
        return None


# ---------------------------------------------------------------------------
# Result JSON persistence
# ---------------------------------------------------------------------------

def save_result_json(result_id: str, payload: dict[str, Any]) -> str | None:
    """Upload a result JSON blob and return its GCS URI, or *None* on failure."""
    bucket = _ensure_bucket()
    if bucket is None:
        return None
    blob_name = f"{GCS_RESULT_PREFIX}/results/{result_id}.json"
    try:
        blob = bucket.blob(blob_name)
        blob.upload_from_string(
            json.dumps(payload, ensure_ascii=False, indent=2),
            content_type="application/json",
        )
        logger.info("Saved result JSON to gs://%s/%s", GCS_BUCKET_NAME, blob_name)
        return f"gs://{GCS_BUCKET_NAME}/{blob_name}"
    except Exception as exc:
        logger.warning("Failed to save result JSON to GCS: %s", exc)
        return None


def get_result_json(result_id: str) -> dict[str, Any] | None:
    """Download a result JSON from GCS, or return *None* on failure."""
    bucket = _ensure_bucket()
    if bucket is None:
        return None
    blob_name = f"{GCS_RESULT_PREFIX}/results/{result_id}.json"
    try:
        blob = bucket.blob(blob_name)
        if not blob.exists():
            return None
        return json.loads(blob.download_as_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read result JSON from GCS: %s", exc)
        return None


# ---------------------------------------------------------------------------
# User photo persistence
# ---------------------------------------------------------------------------

def save_user_photo(result_id: str, image_bytes: bytes, content_type: str = "image/jpeg") -> str | None:
    """Upload user photo to GCS and return its URL, or *None* on failure."""
    bucket = _ensure_bucket()
    if bucket is None:
        return None
    ext = "png" if "png" in content_type else "jpg"
    blob_name = f"{GCS_RESULT_PREFIX}/user_photos/{result_id}.{ext}"
    try:
        blob = bucket.blob(blob_name)
        blob.upload_from_string(image_bytes, content_type=content_type)
        logger.info("Saved user photo to gs://%s/%s", GCS_BUCKET_NAME, blob_name)
        return blob.public_url
    except Exception as exc:
        logger.warning("Failed to save user photo to GCS: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Thumbnail persistence
# ---------------------------------------------------------------------------

def save_thumbnail(result_id: str, image_bytes: bytes, content_type: str = "image/png") -> str | None:
    """Upload a thumbnail and return its URL, or *None* on failure."""
    bucket = _ensure_bucket()
    if bucket is None:
        return None
    blob_name = f"{GCS_RESULT_PREFIX}/thumbnails/{result_id}.png"
    try:
        blob = bucket.blob(blob_name)
        blob.upload_from_string(image_bytes, content_type=content_type)
        logger.info("Saved thumbnail to gs://%s/%s", GCS_BUCKET_NAME, blob_name)
        return blob.public_url
    except Exception as exc:
        logger.warning("Failed to save thumbnail to GCS: %s", exc)
        return None


# ---------------------------------------------------------------------------
# History index persistence
# ---------------------------------------------------------------------------

def save_history_index(entries: list[dict[str, Any]], retries: int = 3) -> bool:
    """Persist the full history index JSON to GCS with retry. Returns success flag."""
    bucket = _ensure_bucket()
    if bucket is None:
        return False
    blob_name = f"{GCS_RESULT_PREFIX}/history_index.json"
    data = json.dumps(entries, ensure_ascii=False, indent=2)
    for attempt in range(retries):
        try:
            blob = bucket.blob(blob_name)
            blob.upload_from_string(data, content_type="application/json")
            return True
        except Exception as exc:
            logger.warning("Failed to save history index to GCS (attempt %d/%d): %s", attempt + 1, retries, exc)
    return False


def load_history_index() -> list[dict[str, Any]] | None:
    """Load the history index from GCS, or return *None* on failure."""
    bucket = _ensure_bucket()
    if bucket is None:
        return None
    blob_name = f"{GCS_RESULT_PREFIX}/history_index.json"
    try:
        blob = bucket.blob(blob_name)
        if not blob.exists():
            return []
        return json.loads(blob.download_as_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load history index from GCS: %s", exc)
        return None
