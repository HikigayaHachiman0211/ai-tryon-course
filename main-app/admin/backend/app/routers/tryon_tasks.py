from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import cast, Date, func

from app.auth import get_current_admin
from app.database import TryonTask, get_db
from app.routers import SHANGHAI, to_beijing_str

router = APIRouter(prefix="/api/admin/tryon-tasks", tags=["tryon-tasks"])


@router.get("")
def list_tasks(
    page: int = 1,
    size: int = 20,
    status: str = "",
    error_type: str = "",
    admin=Depends(get_current_admin),
    db=Depends(get_db),
):
    q = db.query(TryonTask)
    if status:
        q = q.filter(TryonTask.status == status)
    if error_type:
        q = q.filter(TryonTask.error_type == error_type)
    total = q.count()
    items = q.order_by(TryonTask.created_at.desc()).offset((page - 1) * size).limit(size).all()
    return {
        "total": total,
        "page": page,
        "items": [_serialize(t) for t in items],
    }


@router.get("/stats")
def task_stats(admin=Depends(get_current_admin), db=Depends(get_db)):
    total = db.query(func.count(TryonTask.id)).scalar() or 0
    completed = db.query(func.count(TryonTask.id)).filter(TryonTask.status == "completed").scalar() or 0
    failed = db.query(func.count(TryonTask.id)).filter(TryonTask.status == "failed").scalar() or 0
    unknown = db.query(func.count(TryonTask.id)).filter(TryonTask.status == "unknown").scalar() or 0
    processing = db.query(func.count(TryonTask.id)).filter(TryonTask.status == "processing").scalar() or 0
    queued = db.query(func.count(TryonTask.id)).filter(TryonTask.status == "queued").scalar() or 0

    avg_duration = db.query(func.avg(TryonTask.duration_ms)).filter(
        TryonTask.status == "completed"
    ).scalar() or 0

    # Error type distribution
    error_dist = (
        db.query(TryonTask.error_type, func.count(TryonTask.id))
        .filter(TryonTask.status == "failed", TryonTask.error_type.isnot(None))
        .group_by(TryonTask.error_type)
        .all()
    )

    # Success rate trend (last 7 days, using Shanghai day boundaries)
    now = datetime.now(SHANGHAI)
    trend = []
    for i in range(6, -1, -1):
        sh_day = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        sh_next = sh_day + timedelta(days=1)
        utc_start = sh_day.astimezone(timezone.utc).replace(tzinfo=None)
        utc_end = sh_next.astimezone(timezone.utc).replace(tzinfo=None)
        day_total = db.query(func.count(TryonTask.id)).filter(
            TryonTask.created_at >= utc_start,
            TryonTask.created_at < utc_end,
        ).scalar() or 0
        day_success = db.query(func.count(TryonTask.id)).filter(
            TryonTask.created_at >= utc_start,
            TryonTask.created_at < utc_end,
            TryonTask.status == "completed",
        ).scalar() or 0
        trend.append({
            "date": str(sh_day.date()),
            "total": day_total,
            "success": day_success,
            "rate": round(day_success / day_total * 100, 1) if day_total > 0 else 0,
        })

    return {
        "total": total,
        "completed": completed,
        "failed": failed,
        "unknown": unknown,
        "processing": processing,
        "queued": queued,
        "avg_duration_ms": round(avg_duration, 1),
        "error_distribution": [{"type": e[0], "count": e[1]} for e in error_dist],
        "success_trend": trend,
    }


def _normalize_workbench_root(url: str) -> str:
    raw = str(url or "").strip().rstrip("/")
    if raw.endswith("/static/index.html"):
        raw = raw[:-len("/static/index.html")].rstrip("/")
    return raw


@router.get("/{task_id}")
def get_task(task_id: str, admin=Depends(get_current_admin), db=Depends(get_db)):
    t = db.get(TryonTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    return _serialize(t)


@router.post("/{task_id}/retry")
async def retry_task(task_id: str, admin=Depends(get_current_admin), db=Depends(get_db)):
    t = db.get(TryonTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    if t.status not in {"failed", "unknown"}:
        raise HTTPException(400, "只能重试 failed 或 unknown 状态的任务")

    from app.config import get_settings
    settings = get_settings()
    workbench_root = _normalize_workbench_root(settings.TRYON_WORKBENCH_URL)
    if workbench_root:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{workbench_root}/api/retry",
                    headers={"X-Ingest-Key": settings.INGEST_SECRET_KEY},
                    json={"task_id": task_id, "allow_unknown_retry": True},
                )
        except Exception as exc:
            raise HTTPException(502, f"工作台重试请求失败: {type(exc).__name__}")
        if resp.status_code >= 400:
            raise HTTPException(502, f"工作台拒绝重试 ({resp.status_code})")

    # Update local admin index record only after workbench re-enqueue succeeds
    t.status = "queued"
    t.error_type = None
    t.error_detail = None
    t.result_image_url = None
    t.duration_ms = None
    db.commit()

    return {"detail": "已重新排队", "task_id": task_id, "status": "queued"}


def _serialize(t: TryonTask) -> dict:
    return {
        "id": t.id,
        "created_at": to_beijing_str(t.created_at),
        "updated_at": to_beijing_str(t.updated_at),
        "status": t.status,
        "user_photo_url": t.user_photo_url,
        "product_id": t.product_id,
        "result_image_url": t.result_image_url,
        "error_type": t.error_type,
        "error_detail": t.error_detail,
        "duration_ms": t.duration_ms,
        "model_used": t.model_used,
    }
