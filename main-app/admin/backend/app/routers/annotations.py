from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import cast, Date, func, or_

from app.auth import get_current_admin
from app.database import (
    AdminUser, AnnotationRecord, AnnotationTask, Product, get_db,
)
from app.routers import SHANGHAI, to_beijing_str
from app.services.annotation_engine import compute_annotation_confidence, derive_priority

router = APIRouter(prefix="/api/admin/annotations", tags=["annotations"])


class AnnotationUpdate(BaseModel):
    color_family: str | None = None
    style_type: str | None = None
    style_features: list[str] | None = None
    function_features: list[str] | None = None
    body_fit: str | None = None
    size_tags: list[str] | None = None
    notes: str | None = None


class BatchApproveRequest(BaseModel):
    product_ids: list[int]


class BatchAssignRequest(BaseModel):
    product_ids: list[int]
    assignee: str


class BatchBrandFixRequest(BaseModel):
    old_brand: str
    new_brand: str
    product_ids: list[int]


@router.get("")
def list_annotations(
    page: int = 1,
    size: int = 20,
    status: str = "",
    priority: str = "",
    confidence_max: float = 1.0,
    field_issue: str = "",
    admin=Depends(get_current_admin),
    db=Depends(get_db),
):
    q = db.query(Product)
    if status:
        q = q.filter(Product.annotation_status == status)
    if priority != "":
        # Join with annotation_tasks for priority
        q = q.join(AnnotationTask, AnnotationTask.product_id == Product.id)
        if priority == "2":
            q = q.filter(AnnotationTask.priority == 2)
        elif priority == "1":
            q = q.filter(AnnotationTask.priority == 1)
        elif priority == "0":
            q = q.filter(AnnotationTask.priority == 0)
    if confidence_max < 1.0:
        q = q.filter(Product.annotation_confidence <= confidence_max)

    total = q.count()
    items = q.order_by(Product.annotation_confidence.asc().nullslast(), Product.id).offset((page - 1) * size).limit(size).all()

    result = []
    for p in items:
        task = db.query(AnnotationTask).filter_by(product_id=p.id).first()
        result.append(_serialize_product_with_task(p, task))

    return {"total": total, "page": page, "items": result}


@router.get("/stats")
def annotation_stats(admin=Depends(get_current_admin), db=Depends(get_db)):
    total = db.query(func.count(Product.id)).scalar() or 0
    unreviewed = db.query(func.count(Product.id)).filter(
        or_(Product.annotation_status == "unreviewed", Product.annotation_status.is_(None))
    ).scalar() or 0
    verified = db.query(func.count(Product.id)).filter(Product.annotation_status == "verified").scalar() or 0
    partial = db.query(func.count(Product.id)).filter(Product.annotation_status == "partial").scalar() or 0

    # Confidence distribution (histogram)
    conf_dist = []
    for lo in [i / 10 for i in range(0, 10)]:
        hi = lo + 0.1
        cnt = db.query(func.count(Product.id)).filter(
            Product.annotation_confidence >= lo,
            Product.annotation_confidence < hi,
        ).scalar() or 0
        conf_dist.append({"range": f"{lo:.1f}-{hi:.1f}", "count": cnt})

    # Today's annotations (Shanghai timezone)
    _sh_midnight = datetime.now(SHANGHAI).replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = _sh_midnight.astimezone(timezone.utc).replace(tzinfo=None)
    today_count = db.query(func.count(AnnotationRecord.id)).filter(
        AnnotationRecord.created_at >= today_start
    ).scalar() or 0

    return {
        "total": total,
        "unreviewed": unreviewed,
        "verified": verified,
        "partial": partial,
        "confidence_distribution": conf_dist,
        "today_annotations": today_count,
    }


@router.get("/quality-report")
def quality_report(admin=Depends(get_current_admin), db=Depends(get_db)):
    # Top corrected fields
    field_corrections = (
        db.query(AnnotationRecord.field_name, func.count(AnnotationRecord.id).label("cnt"))
        .group_by(AnnotationRecord.field_name)
        .order_by(func.count(AnnotationRecord.id).desc())
        .limit(10)
        .all()
    )
    return {
        "field_corrections": [{"field": f[0], "count": f[1]} for f in field_corrections],
    }


@router.get("/{product_id}")
def get_annotation(product_id: int, admin=Depends(get_current_admin), db=Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "商品不存在")

    task = db.query(AnnotationTask).filter_by(product_id=product_id).first()
    records = (
        db.query(AnnotationRecord)
        .filter_by(product_id=product_id)
        .order_by(AnnotationRecord.created_at.desc())
        .all()
    )

    return {
        "product": _serialize_product_with_task(p, task),
        "history": [
            {
                "id": r.id,
                "field_name": r.field_name,
                "old_value": r.old_value,
                "new_value": r.new_value,
                "source": r.source,
                "annotator": r.annotator,
                "created_at": to_beijing_str(r.created_at),
                "confidence_before": r.confidence_before,
                "confidence_after": r.confidence_after,
            }
            for r in records
        ],
    }


@router.put("/{product_id}")
def update_annotation(
    product_id: int,
    body: AnnotationUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db=Depends(get_db),
):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "商品不存在")

    data = body.model_dump(exclude_unset=True)
    notes = data.pop("notes", None)
    now = datetime.now(SHANGHAI)

    for field, new_val in data.items():
        old_val = getattr(p, field, None)
        old_str = json.dumps(old_val, ensure_ascii=False) if isinstance(old_val, (list, dict)) else str(old_val or "")
        new_str = json.dumps(new_val, ensure_ascii=False) if isinstance(new_val, (list, dict)) else str(new_val or "")

        # Idempotency: only record if value actually changed
        if old_str == new_str:
            continue

        record = AnnotationRecord(
            product_id=product_id,
            field_name=field,
            old_value=old_str,
            new_value=new_str,
            source="manual",
            annotator=admin.username,
            confidence_before=p.annotation_confidence,
            confidence_after=1.0,
        )
        db.add(record)
        setattr(p, field, new_val)

    p.annotation_status = "partial"
    p.last_annotated_at = now
    p.last_annotated_by = admin.username

    # Update task if exists
    task = db.query(AnnotationTask).filter_by(product_id=product_id).first()
    if not task:
        task = AnnotationTask(product_id=product_id, status="in_progress", assigned_to=admin.username)
        db.add(task)
    else:
        task.status = "in_progress"
    if notes:
        task.notes = notes

    db.commit()
    return {"detail": "标注已保存"}


@router.post("/{product_id}/approve")
def approve(product_id: int, admin: AdminUser = Depends(get_current_admin), db=Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "商品不存在")

    p.annotation_status = "verified"
    p.annotation_confidence = 1.0
    p.last_annotated_at = datetime.now(SHANGHAI)
    p.last_annotated_by = admin.username

    task = db.query(AnnotationTask).filter_by(product_id=product_id).first()
    if not task:
        task = AnnotationTask(product_id=product_id)
        db.add(task)
    task.status = "approved"
    task.completed_at = datetime.now(SHANGHAI)

    db.commit()
    return {"detail": "已确认"}


@router.post("/{product_id}/reject")
def reject(product_id: int, reason: str = "", admin: AdminUser = Depends(get_current_admin), db=Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "商品不存在")

    task = db.query(AnnotationTask).filter_by(product_id=product_id).first()
    if not task:
        task = AnnotationTask(product_id=product_id)
        db.add(task)
    task.status = "rejected"
    task.notes = reason

    db.commit()
    return {"detail": "已驳回"}


@router.post("/batch-approve")
def batch_approve(body: BatchApproveRequest, admin: AdminUser = Depends(get_current_admin), db=Depends(get_db)):
    now = datetime.now(SHANGHAI)
    count = 0
    for pid in body.product_ids:
        p = db.get(Product, pid)
        if not p:
            continue
        p.annotation_status = "verified"
        p.annotation_confidence = 1.0
        p.last_annotated_at = now
        p.last_annotated_by = admin.username

        task = db.query(AnnotationTask).filter_by(product_id=pid).first()
        if not task:
            task = AnnotationTask(product_id=pid)
            db.add(task)
        task.status = "approved"
        task.completed_at = now
        count += 1
    db.commit()
    return {"approved": count}


@router.post("/batch-assign")
def batch_assign(body: BatchAssignRequest, admin=Depends(get_current_admin), db=Depends(get_db)):
    count = 0
    for pid in body.product_ids:
        task = db.query(AnnotationTask).filter_by(product_id=pid).first()
        if not task:
            task = AnnotationTask(product_id=pid)
            db.add(task)
        task.assigned_to = body.assignee
        count += 1
    db.commit()
    return {"assigned": count}


@router.post("/batch-brand-fix")
def batch_brand_fix(
    body: BatchBrandFixRequest,
    admin: AdminUser = Depends(get_current_admin),
    db=Depends(get_db),
):
    now = datetime.now(SHANGHAI)
    count = 0
    for pid in body.product_ids:
        p = db.get(Product, pid)
        if not p:
            continue
        features = list(p.style_features or [])
        old_tag = f"品牌:{body.old_brand}"
        new_tag = f"品牌:{body.new_brand}"
        if old_tag in features:
            old_features = json.dumps(features, ensure_ascii=False)
            features = [new_tag if f == old_tag else f for f in features]
            p.style_features = features
            record = AnnotationRecord(
                product_id=pid,
                field_name="style_features",
                old_value=old_features,
                new_value=json.dumps(features, ensure_ascii=False),
                source="manual",
                annotator=admin.username,
                confidence_before=p.annotation_confidence,
                confidence_after=1.0,
            )
            db.add(record)
            p.last_annotated_at = now
            p.last_annotated_by = admin.username
            count += 1
    db.commit()
    return {"fixed": count}


@router.post("/recompute-confidence")
def recompute_confidence(admin=Depends(get_current_admin), db=Depends(get_db)):
    products = db.query(Product).all()
    for p in products:
        conf = compute_annotation_confidence(p)
        p.annotation_confidence = conf
        # Update or create task with priority
        task = db.query(AnnotationTask).filter_by(product_id=p.id).first()
        if not task:
            task = AnnotationTask(product_id=p.id, priority=derive_priority(conf))
            db.add(task)
        else:
            task.priority = derive_priority(conf)
    db.commit()
    return {"recomputed": len(products)}


@router.post("/export")
def export_annotations(format: str = "json", admin=Depends(get_current_admin), db=Depends(get_db)):
    records = db.query(AnnotationRecord).order_by(AnnotationRecord.created_at.desc()).all()
    data = [
        {
            "product_id": r.product_id,
            "field_name": r.field_name,
            "old_value": r.old_value,
            "new_value": r.new_value,
            "source": r.source,
            "annotator": r.annotator,
            "created_at": to_beijing_str(r.created_at),
        }
        for r in records
    ]
    return {"format": format, "total": len(data), "records": data}


@router.post("/sync-database-json")
def sync_database_json(admin=Depends(get_current_admin), db=Depends(get_db)):
    products = db.query(Product).filter(Product.annotation_status == "verified").all()
    data = []
    for p in products:
        data.append({
            "商品标题": p.title,
            "价格": p.price,
            "图片路径": p.image_path,
            "款式类型": p.style_type,
            "精准颜色色系": p.color_family,
            "版型与身材适配度": p.body_fit,
            "风格特征": p.style_features,
            "功能属性": p.function_features,
        })
    return {"total": len(data), "data": data}


def _serialize_product_with_task(p: Product, task: AnnotationTask | None) -> dict:
    from app.config import get_settings
    settings = get_settings()
    return {
        "id": p.id,
        "title": p.title,
        "price": p.price,
        "image_path": p.image_path,
        "image_url": f"{settings.PUBLIC_IMAGE_BASE_URL}/{p.image_path.split('/')[-1]}" if p.image_path else None,
        "style_type": p.style_type,
        "color_family": p.color_family,
        "body_fit": p.body_fit,
        "style_features": p.style_features,
        "function_features": p.function_features,
        "size_tags": p.size_tags,
        "size_notes": p.size_notes,
        "product_url": p.product_url,
        "annotation_status": p.annotation_status,
        "annotation_confidence": p.annotation_confidence,
        "last_annotated_at": to_beijing_str(p.last_annotated_at),
        "last_annotated_by": p.last_annotated_by,
        "task": {
            "status": task.status,
            "priority": task.priority,
            "assigned_to": task.assigned_to,
            "notes": task.notes,
            "completed_at": to_beijing_str(task.completed_at) if task else None,
        } if task else None,
    }
