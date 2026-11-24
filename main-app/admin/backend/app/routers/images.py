from __future__ import annotations

import time
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.auth import get_current_admin
from app.database import Product, get_db
from app.services import gcs

router = APIRouter(prefix="/api/admin/images", tags=["images"])

IMAGE_PREFIX = "羽绒服_png/"
SAMPLE_PREFIX = "sample_models/"
BlobScope = Literal["products", "samples", "media"]

_CACHE_TTL_SECONDS = 60.0
_CACHE_LOCK = Lock()
_BLOB_CACHE: dict[tuple[str, str, str, str], tuple[float, list[dict[str, Any]]]] = {}


def invalidate_blob_cache() -> None:
    """Clear the short-lived blob listing cache after mutations."""
    with _CACHE_LOCK:
        _BLOB_CACHE.clear()


def _scope_container(settings: Any, scope: BlobScope) -> str:
    return settings.media_container if scope == "media" else settings.product_container


def _serialize_item(item: dict[str, Any], *, scope: BlobScope, container: str) -> dict[str, Any]:
    raw_name = str(item.get("name") or "")
    if scope == "products" and raw_name.startswith(IMAGE_PREFIX):
        display_name = raw_name[len(IMAGE_PREFIX):]
    else:
        display_name = raw_name
    return {
        "name": raw_name,
        "display_name": display_name,
        "url": item.get("url") or "",
        "size": item.get("size") or 0,
        "updated": item.get("updated"),
        "content_type": item.get("content_type"),
        "container": container,
    }


def _storage_metadata(settings: Any, container: str) -> dict[str, str]:
    return {
        "provider": settings.provider,
        "account_name": settings.account_name,
        "container": container,
        "product_container": settings.product_container,
        "media_container": settings.media_container,
        "public_base_url": settings.base_url(container),
    }


def _load_scope_blobs(scope: BlobScope, *, refresh: bool = False) -> tuple[list[dict[str, Any]], dict[str, str]]:
    settings = gcs.load_object_storage_settings()
    container = _scope_container(settings, scope)
    cache_key = (settings.provider, settings.account_name, container, scope)
    now = time.monotonic()

    if not refresh:
        with _CACHE_LOCK:
            cached = _BLOB_CACHE.get(cache_key)
            if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
                return cached[1], _storage_metadata(settings, container)

    if scope == "products":
        raw_items = gcs.list_blobs(IMAGE_PREFIX, max_results=100000)
    elif scope == "samples":
        raw_items = gcs.list_blobs(SAMPLE_PREFIX, max_results=10000)
    else:
        raw_items = gcs._get_storage().list("", max_results=5000, container=container)

    items = [_serialize_item(item, scope=scope, container=container) for item in raw_items]
    with _CACHE_LOCK:
        _BLOB_CACHE[cache_key] = (now, items)

    return items, _storage_metadata(settings, container)


@router.get("")
def list_images(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    prefix: str = "",
    scope: BlobScope = "products",
    refresh: bool = False,
    admin=Depends(get_current_admin),
):
    del admin
    all_items, storage_info = _load_scope_blobs(scope, refresh=refresh)
    query = prefix.strip().lower()
    if query:
        filtered = [
            item
            for item in all_items
            if query in item["name"].lower() or query in item["display_name"].lower()
        ]
    else:
        filtered = all_items

    total = len(filtered)
    start = max(0, (page - 1) * size)
    return {
        "total": total,
        "page": page,
        "size": size,
        "scope": scope,
        "storage": storage_info,
        "items": filtered[start : start + size],
    }


@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    scope: BlobScope = "products",
    admin=Depends(get_current_admin),
):
    del admin
    data = await file.read()
    filename = Path(file.filename or "upload.png").name or "upload.png"
    content_type = file.content_type or "image/png"

    if scope == "media":
        settings = gcs.load_object_storage_settings()
        url = gcs._get_storage().upload(
            filename,
            data,
            content_type=content_type,
            cache_control="no-store, max-age=0",
            container=settings.media_container,
        )
        dest = filename
    elif scope == "samples":
        dest = f"{SAMPLE_PREFIX}{filename}"
        url = gcs.upload_blob(dest, data, content_type=content_type)
    else:
        dest = f"{IMAGE_PREFIX}{filename}"
        url = gcs.upload_blob(dest, data, content_type=content_type)

    invalidate_blob_cache()
    return {"url": url, "path": dest}


def _delete_target(name_or_path: str, scope: BlobScope) -> dict[str, str]:
    cleaned = str(name_or_path or "").strip().lstrip("/")
    if not cleaned:
        raise HTTPException(400, "缺少图片名称")

    if scope == "media":
        settings = gcs.load_object_storage_settings()
        ok = gcs._get_storage().delete(cleaned, container=settings.media_container)
    elif cleaned.startswith((SAMPLE_PREFIX, IMAGE_PREFIX)):
        ok = gcs.delete_blob(cleaned)
    elif scope == "samples":
        ok = gcs.delete_blob(f"{SAMPLE_PREFIX}{cleaned}")
    else:
        ok = gcs.delete_blob(f"{IMAGE_PREFIX}{cleaned}")

    if not ok:
        raise HTTPException(404, "图片不存在")
    invalidate_blob_cache()
    return {"detail": "已删除"}


@router.delete("")
def delete_image_by_query(
    name: str = Query(..., min_length=1),
    scope: BlobScope = "products",
    admin=Depends(get_current_admin),
):
    del admin
    return _delete_target(name, scope)


@router.delete("/{filename:path}")
def delete_image(
    filename: str,
    scope: BlobScope = "products",
    admin=Depends(get_current_admin),
):
    del admin
    return _delete_target(filename, scope)


@router.get("/orphans")
def orphan_images(
    refresh: bool = False,
    admin=Depends(get_current_admin),
    db=Depends(get_db),
):
    """List product-container blobs not referenced by any product."""
    del admin
    all_images, storage_info = _load_scope_blobs("products", refresh=refresh)
    image_names = {item["name"].split("/")[-1] for item in all_images if item.get("name")}

    products = db.query(Product.image_path).all()
    referenced = {path.split("/")[-1] for (path,) in products if path}

    orphans = image_names - referenced
    return {
        "total": len(orphans),
        "scanned": len(all_images),
        "storage": storage_info,
        "orphans": sorted(orphans)[:200],
    }
