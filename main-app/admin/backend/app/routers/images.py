from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import func

from app.auth import get_current_admin
from app.database import Product, get_db
from app.services import gcs

router = APIRouter(prefix="/api/admin/images", tags=["images"])

IMAGE_PREFIX = "羽绒服_png/"


@router.get("")
def list_images(page: int = 1, size: int = 50, prefix: str = "", admin=Depends(get_current_admin)):
    search_prefix = f"{IMAGE_PREFIX}{prefix}" if prefix else IMAGE_PREFIX
    items, total = gcs.list_blobs_paged(search_prefix, page=page, size=size)
    return {"total": total, "page": page, "size": size, "items": items}


@router.post("/upload")
async def upload_image(file: UploadFile = File(...), admin=Depends(get_current_admin)):
    data = await file.read()
    filename = file.filename or "upload.png"
    dest = f"{IMAGE_PREFIX}{filename}"
    url = gcs.upload_blob(dest, data, content_type=file.content_type or "image/png")
    return {"url": url, "path": dest}


@router.delete("/{filename:path}")
def delete_image(filename: str, admin=Depends(get_current_admin)):
    name = filename if filename.startswith(IMAGE_PREFIX) else f"{IMAGE_PREFIX}{filename}"
    ok = gcs.delete_blob(name)
    if not ok:
        raise HTTPException(404, "图片不存在")
    return {"detail": "已删除"}


@router.get("/orphans")
def orphan_images(admin=Depends(get_current_admin), db=Depends(get_db)):
    """List images in GCS not referenced by any product."""
    all_images = gcs.list_blobs(IMAGE_PREFIX, max_results=10000)
    image_names = {blob["name"].split("/")[-1] for blob in all_images}

    # Get all referenced filenames from products
    products = db.query(Product.image_path).all()
    referenced = set()
    for (path,) in products:
        if path:
            referenced.add(path.split("/")[-1])

    orphans = image_names - referenced
    return {"total": len(orphans), "orphans": sorted(orphans)[:200]}
