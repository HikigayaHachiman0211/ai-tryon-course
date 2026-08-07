from __future__ import annotations

import struct
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import func

from app.auth import get_current_admin
from app.config import get_settings
from app.database import AdminUser, SampleModel, get_db
from app.routers import to_beijing_str
from app.services import gcs

router = APIRouter(tags=["sample-models"])

ALLOWED_MAGIC = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"RIFF": "image/webp",  # WebP starts with RIFF
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def _check_magic(data: bytes) -> str | None:
    for magic, mime in ALLOWED_MAGIC.items():
        if data[:len(magic)] == magic:
            return mime
    return None


def _resolve_image_url(model: SampleModel) -> str:
    object_name = f"sample_models/{model.gender}/{model.image_filename}"
    if not model.gcs_url or model.gcs_url.startswith("https://storage.googleapis.com/"):
        return gcs.get_blob_url(object_name)
    return model.gcs_url


# ---- Public API (no auth) ----

@router.get("/api/sample-models")
def public_list(gender: str = "", db=Depends(get_db)):
    q = db.query(SampleModel).filter(SampleModel.is_active == True)
    if gender:
        q = q.filter(SampleModel.gender == gender)
    models = q.order_by(SampleModel.display_order, SampleModel.id).all()
    return [
        {
            "id": m.id,
            "name": m.name,
            "gender": m.gender,
            "image_url": _resolve_image_url(m),
        }
        for m in models
    ]


# ---- Admin API ----

admin_router = APIRouter(prefix="/api/admin/sample-models", tags=["sample-models"])


@admin_router.get("")
def list_models(
    page: int = 1,
    size: int = 50,
    gender: str = "",
    active: str = "",
    admin=Depends(get_current_admin),
    db=Depends(get_db),
):
    q = db.query(SampleModel)
    if gender:
        q = q.filter(SampleModel.gender == gender)
    if active == "true":
        q = q.filter(SampleModel.is_active == True)
    elif active == "false":
        q = q.filter(SampleModel.is_active == False)

    total = q.count()
    items = q.order_by(SampleModel.display_order, SampleModel.id).offset((page - 1) * size).limit(size).all()
    return {"total": total, "items": [_serialize(m) for m in items]}


@admin_router.get("/{model_id}")
def get_model(model_id: int, admin=Depends(get_current_admin), db=Depends(get_db)):
    m = db.get(SampleModel, model_id)
    if not m:
        raise HTTPException(404, "模特不存在")
    return _serialize(m)


@admin_router.post("/upload")
async def upload_model(
    image: UploadFile = File(...),
    name: str = Form(...),
    gender: str = Form(...),
    display_order: int = Form(0),
    admin: AdminUser = Depends(get_current_admin),
    db=Depends(get_db),
):
    data = await image.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(400, "文件大小超过 10MB 限制")

    mime = _check_magic(data)
    if not mime:
        raise HTTPException(400, "不支持的文件类型，仅允许 JPG/PNG/WebP")

    filename = image.filename or f"{name}.jpg"
    gcs_path = f"sample_models/{gender}/{filename}"
    url = gcs.upload_blob(gcs_path, data, content_type=mime)

    # Get image dimensions
    width, height = None, None
    try:
        from PIL import Image
        img = Image.open(BytesIO(data))
        width, height = img.size
    except Exception:
        pass

    m = SampleModel(
        name=name,
        gender=gender,
        image_filename=filename,
        gcs_url=url,
        display_order=display_order,
        uploaded_by=admin.username,
        file_size=len(data),
        image_width=width,
        image_height=height,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return _serialize(m)


class ModelUpdate(BaseModel):
    name: str | None = None
    gender: str | None = None
    display_order: int | None = None
    is_active: bool | None = None


@admin_router.put("/{model_id}")
def update_model(
    model_id: int,
    body: ModelUpdate,
    admin=Depends(get_current_admin),
    db=Depends(get_db),
):
    m = db.get(SampleModel, model_id)
    if not m:
        raise HTTPException(404, "模特不存在")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return _serialize(m)


@admin_router.put("/{model_id}/replace-image")
async def replace_image(
    model_id: int,
    image: UploadFile = File(...),
    admin=Depends(get_current_admin),
    db=Depends(get_db),
):
    m = db.get(SampleModel, model_id)
    if not m:
        raise HTTPException(404, "模特不存在")

    data = await image.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(400, "文件大小超过 10MB 限制")
    mime = _check_magic(data)
    if not mime:
        raise HTTPException(400, "不支持的文件类型")

    gcs_path = f"sample_models/{m.gender}/{m.image_filename}"
    url = gcs.upload_blob(gcs_path, data, content_type=mime)
    m.gcs_url = url
    m.file_size = len(data)

    try:
        from PIL import Image
        img = Image.open(BytesIO(data))
        m.image_width, m.image_height = img.size
    except Exception:
        pass

    db.commit()
    return _serialize(m)


@admin_router.delete("/{model_id}")
def delete_model(model_id: int, admin=Depends(get_current_admin), db=Depends(get_db)):
    m = db.get(SampleModel, model_id)
    if not m:
        raise HTTPException(404, "模特不存在")

    gcs_path = f"sample_models/{m.gender}/{m.image_filename}"
    gcs_ok = gcs.delete_blob(gcs_path)
    if not gcs_ok:
        # GCS delete failed — keep record, mark error
        return {"detail": "GCS 删除失败，记录保留", "gcs_error": True}

    db.delete(m)
    db.commit()
    return {"detail": "已删除"}


class BatchDeleteRequest(BaseModel):
    ids: list[int]


@admin_router.delete("/batch")
def batch_delete(body: BatchDeleteRequest, admin=Depends(get_current_admin), db=Depends(get_db)):
    deleted = 0
    for mid in body.ids:
        m = db.get(SampleModel, mid)
        if not m:
            continue
        gcs_path = f"sample_models/{m.gender}/{m.image_filename}"
        gcs.delete_blob(gcs_path)
        db.delete(m)
        deleted += 1
    db.commit()
    return {"deleted": deleted}


class ReorderItem(BaseModel):
    id: int
    display_order: int


class ReorderRequest(BaseModel):
    items: list[ReorderItem]


@admin_router.put("/reorder")
def reorder(body: ReorderRequest, admin=Depends(get_current_admin), db=Depends(get_db)):
    for item in body.items:
        m = db.get(SampleModel, item.id)
        if m:
            m.display_order = item.display_order
    db.commit()
    return {"detail": "排序已更新"}


class BatchStatusRequest(BaseModel):
    ids: list[int]
    is_active: bool


@admin_router.put("/batch-status")
def batch_status(body: BatchStatusRequest, admin=Depends(get_current_admin), db=Depends(get_db)):
    count = 0
    for mid in body.ids:
        m = db.get(SampleModel, mid)
        if m:
            m.is_active = body.is_active
            count += 1
    db.commit()
    return {"updated": count}


def _serialize(m: SampleModel) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "gender": m.gender,
        "image_filename": m.image_filename,
        "gcs_url": _resolve_image_url(m),
        "thumbnail_url": m.thumbnail_url,
        "display_order": m.display_order,
        "is_active": m.is_active,
        "uploaded_by": m.uploaded_by,
        "created_at": to_beijing_str(m.created_at),
        "file_size": m.file_size,
        "image_width": m.image_width,
        "image_height": m.image_height,
    }


# Register both routers
router.include_router(admin_router)
