"""GCS helper — wraps google-cloud-storage; gracefully degrades when unavailable."""
from __future__ import annotations

import io
import logging
import os
from typing import Iterator

from app.config import get_settings
from app.routers import to_beijing_str

logger = logging.getLogger(__name__)

_client = None
_bucket = None


def _init():
    global _client, _bucket
    if _client is not None:
        return
    try:
        from google.cloud import storage
        _client = storage.Client()
        _bucket = _client.bucket(get_settings().GCS_BUCKET_NAME)
    except Exception as exc:
        logger.warning("GCS unavailable: %s", exc)
        _client = False  # sentinel: tried & failed


def _get_bucket():
    _init()
    if _bucket is None:
        return None
    return _bucket


def list_blobs(prefix: str, max_results: int = 500) -> list[dict]:
    bucket = _get_bucket()
    if not bucket:
        return []
    blobs = bucket.list_blobs(prefix=prefix, max_results=max_results)
    result = []
    for b in blobs:
        result.append({
            "name": b.name,
            "size": b.size,
            "updated": to_beijing_str(b.updated),
            "content_type": b.content_type,
            "url": b.public_url,
        })
    return result


def list_blobs_paged(prefix: str, page: int = 1, size: int = 50) -> tuple[list[dict], int]:
    bucket = _get_bucket()
    if not bucket:
        return [], 0
    all_blobs = list(bucket.list_blobs(prefix=prefix))
    total = len(all_blobs)
    start = (page - 1) * size
    end = start + size
    result = []
    for b in all_blobs[start:end]:
        result.append({
            "name": b.name,
            "size": b.size,
            "updated": to_beijing_str(b.updated),
            "content_type": b.content_type,
            "url": b.public_url,
        })
    return result, total


def upload_blob(destination_name: str, data: bytes, content_type: str = "image/png") -> str:
    bucket = _get_bucket()
    if not bucket:
        raise RuntimeError("GCS not available")
    blob = bucket.blob(destination_name)
    blob.upload_from_string(data, content_type=content_type)
    return blob.public_url


def delete_blob(name: str) -> bool:
    bucket = _get_bucket()
    if not bucket:
        return False
    blob = bucket.blob(name)
    if not blob.exists():
        return False
    blob.delete()
    return True


def blob_exists(name: str) -> bool:
    bucket = _get_bucket()
    if not bucket:
        return False
    return bucket.blob(name).exists()


def download_blob(name: str) -> bytes | None:
    bucket = _get_bucket()
    if not bucket:
        return None
    blob = bucket.blob(name)
    if not blob.exists():
        return None
    return blob.download_as_bytes()


def get_blob_url(name: str) -> str:
    settings = get_settings()
    return f"https://storage.googleapis.com/{settings.GCS_BUCKET_NAME}/{name}"
