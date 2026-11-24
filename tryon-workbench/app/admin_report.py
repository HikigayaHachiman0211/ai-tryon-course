"""Report try-on task lifecycle events to the admin dashboard."""

import asyncio
from datetime import datetime
import logging
import os
import httpx
from sqlalchemy import text

logger = logging.getLogger(__name__)

ADMIN_API_URL = os.getenv("ADMIN_API_URL", "").rstrip("/")
INGEST_SECRET_KEY = os.getenv("INGEST_SECRET_KEY", "")

_client: httpx.AsyncClient | None = None


def _use_direct_db() -> bool:
    return os.getenv("ADMIN_REPORT_MODE", "").strip().lower() == "db"


def _upsert_tryon_task_db(
    *,
    task_id: str,
    status: str,
    user_photo_url: str,
    product_id: int | None,
    result_image_url: str | None,
    error_type: str | None,
    error_detail: str | None,
    duration_ms: float | None,
    model_used: str,
) -> None:
    from app.task_db import get_session_factory

    db_url = os.getenv("ADMIN_DATABASE_URL") or os.getenv("DATABASE_URL") or None
    now = datetime.utcnow()
    session_factory, _ = get_session_factory(db_url)
    with session_factory() as session:
        existing = session.execute(
            text("SELECT id FROM tryon_tasks WHERE id = :id"),
            {"id": task_id},
        ).first()
        if existing is not None:
            assignments = ["status = :status", "updated_at = :updated_at"]
            params: dict = {"id": task_id, "status": status, "updated_at": now}
            if result_image_url:
                assignments.append("result_image_url = :result_image_url")
                params["result_image_url"] = result_image_url
            if error_type:
                assignments.append("error_type = :error_type")
                params["error_type"] = error_type
            if error_detail:
                assignments.append("error_detail = :error_detail")
                params["error_detail"] = error_detail
            if duration_ms is not None:
                assignments.append("duration_ms = :duration_ms")
                params["duration_ms"] = duration_ms
            if model_used:
                assignments.append("model_used = :model_used")
                params["model_used"] = model_used
            session.execute(
                text(f"UPDATE tryon_tasks SET {', '.join(assignments)} WHERE id = :id"),
                params,
            )
        else:
            session.execute(
                text(
                    "INSERT INTO tryon_tasks "
                    "(id, created_at, updated_at, status, user_photo_url, product_id, result_image_url, error_type, error_detail, duration_ms, model_used) "
                    "VALUES (:id, :created_at, :updated_at, :status, :user_photo_url, :product_id, :result_image_url, :error_type, :error_detail, :duration_ms, :model_used)"
                ),
                {
                    "id": task_id,
                    "created_at": now,
                    "updated_at": now,
                    "status": status,
                    "user_photo_url": user_photo_url or "",
                    "product_id": product_id if product_id is not None else 0,
                    "result_image_url": result_image_url,
                    "error_type": error_type,
                    "error_detail": error_detail,
                    "duration_ms": duration_ms,
                    "model_used": model_used or "unknown",
                },
            )
        session.commit()


def _insert_page_view_db(
    *,
    source: str,
    page: str,
    session_id: str,
    user_agent: str,
    ip: str,
) -> None:
    from app.task_db import get_session_factory

    db_url = os.getenv("ADMIN_DATABASE_URL") or os.getenv("DATABASE_URL") or None
    session_factory, _ = get_session_factory(db_url)
    with session_factory() as session:
        session.execute(
            text(
                "INSERT INTO page_views (timestamp, source, page, session_id, user_agent, ip) "
                "VALUES (:timestamp, :source, :page, :session_id, :user_agent, :ip)"
            ),
            {
                "timestamp": datetime.utcnow(),
                "source": source,
                "page": page,
                "session_id": session_id,
                "user_agent": user_agent,
                "ip": ip,
            },
        )
        session.commit()


def _get_client() -> httpx.AsyncClient | None:
    global _client
    if not ADMIN_API_URL:
        return None
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=ADMIN_API_URL,
            timeout=httpx.Timeout(10.0, connect=5.0),
            headers={"X-Ingest-Key": INGEST_SECRET_KEY},
        )
    return _client


async def report_tryon_task(
    task_id: str,
    status: str,
    *,
    user_photo_url: str = "",
    product_id: int | None = None,
    result_image_url: str | None = None,
    error_type: str | None = None,
    error_detail: str | None = None,
    duration_ms: float | None = None,
    model_used: str = "",
    locale: str = "zh-CN",
) -> None:
    """Best-effort report of a try-on task to shared DB or admin dashboard."""
    if _use_direct_db():
        try:
            await asyncio.to_thread(
                _upsert_tryon_task_db,
                task_id=task_id,
                status=status,
                user_photo_url=user_photo_url,
                product_id=product_id,
                result_image_url=result_image_url,
                error_type=error_type,
                error_detail=error_detail,
                duration_ms=duration_ms,
                model_used=model_used,
            )
        except Exception as exc:
            logger.debug("Failed to write tryon task %s directly to DB: %s", task_id, exc)
        return

    client = _get_client()
    if client is None:
        return
    payload = {
        "task_id": task_id,
        "status": status,
        "user_photo_url": user_photo_url,
        "model_used": model_used,
        "locale": locale,
    }
    if product_id is not None:
        payload["product_id"] = product_id
    if result_image_url:
        payload["result_image_url"] = result_image_url
    if error_type:
        payload["error_type"] = error_type
    if error_detail:
        payload["error_detail"] = error_detail
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms

    try:
        resp = await client.post("/api/ingest/tryon-task", json=payload)
        if resp.status_code != 200:
            logger.warning("Admin ingest tryon-task returned %s: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("Failed to report tryon task %s to admin: %s", task_id, exc)


async def report_page_view(
    *,
    source: str,
    page: str = "/",
    session_id: str = "",
    user_agent: str = "",
    ip: str = "",
    locale: str = "zh-CN",
) -> None:
    """Best-effort report of a page view to shared DB or admin dashboard."""
    if _use_direct_db():
        try:
            await asyncio.to_thread(
                _insert_page_view_db,
                source=source,
                page=page,
                session_id=session_id,
                user_agent=user_agent,
                ip=ip,
            )
        except Exception as exc:
            logger.debug("Failed to write page view directly to DB: %s", exc)
        return

    client = _get_client()
    if client is None:
        return
    try:
        resp = await client.post("/api/ingest/page-view", json={
            "source": source,
            "page": page,
            "session_id": session_id,
            "user_agent": user_agent,
            "ip": ip,
            "locale": locale,
        })
        if resp.status_code != 200:
            logger.warning("Admin ingest page-view returned %s: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("Failed to report page view to admin: %s", exc)
