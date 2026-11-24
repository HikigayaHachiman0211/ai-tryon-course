"""
Try-on task logger for the main site.
Call when creating/completing/failing a try-on task.

Usage:
    from admin.integration.tryon_task_logger import log_tryon_task, update_tryon_task
    task_id = log_tryon_task(product_id, user_photo_url, product_image_url)
    update_tryon_task(task_id, status="completed", result_image_url="...")
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _get_engine():
    url = os.environ.get("DATABASE_URL", "")
    return create_engine(url) if url else None


def log_tryon_task(
    product_id: int,
    user_photo_url: str,
    product_image_url: str,
) -> int | None:
    engine = _get_engine()
    if not engine:
        return None
    try:
        from admin.backend.app.database import TryonTask
        with Session(engine) as db:
            task = TryonTask(
                product_id=product_id,
                user_photo_url=user_photo_url,
                product_image_url=product_image_url,
                status="queued",
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            return task.id
    except Exception:
        return None


def update_tryon_task(
    task_id: int,
    status: str = "completed",
    result_image_url: str | None = None,
    error_message: str | None = None,
    error_type: str | None = None,
    duration_ms: int | None = None,
) -> bool:
    engine = _get_engine()
    if not engine:
        return False
    try:
        from admin.backend.app.database import TryonTask
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        with Session(engine) as db:
            task = db.get(TryonTask, task_id)
            if not task:
                return False
            task.status = status
            if result_image_url:
                task.result_image_url = result_image_url
            if error_message:
                task.error_message = error_message
            if error_type:
                task.error_type = error_type
            if duration_ms is not None:
                task.duration_ms = duration_ms
            if status in ("completed", "failed"):
                task.completed_at = datetime.now(ZoneInfo("Asia/Shanghai"))
            db.commit()
        return True
    except Exception:
        return False
