"""Compatibility facade for Admin object storage routes."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from app.services.object_storage import create_object_storage, load_object_storage_settings

_PRODUCT_IMAGE_PREFIX = "羽绒服_png/"
VOICE_CLONES_GCS_PREFIX = os.getenv("VOICE_CLONES_GCS_PREFIX", "voice-clones").strip("/") or "voice-clones"


def _container_for_name(name: str) -> str:
    settings = load_object_storage_settings()
    media_prefixes = (
        os.getenv("GCS_RESULT_PREFIX", "ai-tryon-results"),
        os.getenv("RESULTS_GCS_PREFIX", "tryon-results"),
        os.getenv("UPLOADS_GCS_PREFIX", "tryon-uploads"),
        os.getenv("VOICE_CLONES_GCS_PREFIX", "voice-clones"),
    )
    normalized = str(name).lstrip("/")
    if any(normalized == prefix.strip("/") or normalized.startswith(prefix.strip("/") + "/")
           for prefix in media_prefixes if prefix.strip("/")):
        return settings.media_container
    return settings.product_container


def _physical_name(name: str, settings) -> str:
    normalized = str(name).lstrip("/")
    if settings.provider in {"azure", "oss"} and normalized.startswith(_PRODUCT_IMAGE_PREFIX):
        return normalized[len(_PRODUCT_IMAGE_PREFIX):]
    return normalized


def _get_storage():
    return create_object_storage(load_object_storage_settings())


def list_blobs(prefix: str, max_results: int = 500) -> list[dict[str, Any]]:
    settings = load_object_storage_settings()
    storage = _get_storage()
    container = _container_for_name(prefix)
    physical_prefix = _physical_name(prefix, settings)
    if physical_prefix == prefix:
        return storage.list(prefix, max_results=max_results, container=container)
    # Product catalogs use flat filenames on Azure/OSS; retain the legacy API
    # prefix and include older objects that were uploaded under that prefix.
    rows = storage.list(physical_prefix, max_results=100000, container=container)
    legacy = storage.list(prefix, max_results=100000, container=container)
    combined = {}
    for item in rows:
        if "/" not in item["name"].lstrip("/"):
            logical = _PRODUCT_IMAGE_PREFIX + item["name"]
            combined[logical] = {**item, "name": logical}
    for item in legacy:
        combined.setdefault(item["name"], item)
    return [combined[name] for name in sorted(combined)][:max_results]


def list_blobs_paged(prefix: str, page: int = 1, size: int = 50) -> tuple[list[dict[str, Any]], int]:
    all_items = list_blobs(prefix, max_results=100000)
    start = max(0, (page - 1) * size)
    return all_items[start:start + size], len(all_items)


def upload_blob(destination_name: str, data: bytes, content_type: str = "image/png") -> str:
    settings = load_object_storage_settings()
    return _get_storage().upload(
        _physical_name(destination_name, settings),
        data,
        content_type=content_type,
        cache_control="public, max-age=31536000, immutable" if _container_for_name(destination_name) == settings.product_container else "no-store, max-age=0",
        container=_container_for_name(destination_name),
    )


def delete_blob(name: str) -> bool:
    settings = load_object_storage_settings()
    storage = _get_storage()
    container = _container_for_name(name)
    physical = _physical_name(name, settings)
    if physical != name and not storage.exists(physical, container=container):
        physical = name
    return storage.delete(physical, container=container)


def blob_exists(name: str) -> bool:
    settings = load_object_storage_settings()
    storage = _get_storage()
    container = _container_for_name(name)
    physical = _physical_name(name, settings)
    return storage.exists(physical, container=container) or (
        physical != name and storage.exists(name, container=container)
    )


def download_blob(name: str) -> bytes | None:
    settings = load_object_storage_settings()
    storage = _get_storage()
    container = _container_for_name(name)
    physical = _physical_name(name, settings)
    data = storage.download(physical, container=container)
    if data is None and physical != name:
        return storage.download(name, container=container)
    return data


def get_blob_url(name: str) -> str:
    settings = load_object_storage_settings()
    from app.services.object_storage import build_public_blob_url
    return build_public_blob_url(settings, _physical_name(name, settings), container=_container_for_name(name))
