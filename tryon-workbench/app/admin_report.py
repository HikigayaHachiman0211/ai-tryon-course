"""Report try-on task lifecycle events to the admin dashboard."""

import os
import logging
import httpx

logger = logging.getLogger(__name__)

ADMIN_API_URL = os.getenv("ADMIN_API_URL", "").rstrip("/")
INGEST_SECRET_KEY = os.getenv("INGEST_SECRET_KEY", "").strip()

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient | None:
    global _client
    if not ADMIN_API_URL or not INGEST_SECRET_KEY:
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
) -> None:
    """Best-effort report of a try-on task to admin dashboard."""
    client = _get_client()
    if client is None:
        return
    payload = {
        "task_id": task_id,
        "status": status,
        "user_photo_url": user_photo_url,
        "model_used": model_used,
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
) -> None:
    """Best-effort report of a page view to admin dashboard."""
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
        })
        if resp.status_code != 200:
            logger.warning("Admin ingest page-view returned %s: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("Failed to report page view to admin: %s", exc)
