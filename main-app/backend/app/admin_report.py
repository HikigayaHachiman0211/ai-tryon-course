"""Admin data reporting — sends analytics to the admin backend via HTTP.

All calls are best-effort: failures are logged but never block the main
request flow.  When ADMIN_API_URL is not set the module silently becomes a
no-op so local development works without the admin backend.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ADMIN_API_URL: str = os.getenv("ADMIN_API_URL", "").rstrip("/")
INGEST_SECRET_KEY: str = os.getenv("INGEST_SECRET_KEY", "ai-tryon-ingest-2026")

_client: httpx.Client | None = None


def _get_client() -> httpx.Client | None:
    global _client
    if not ADMIN_API_URL:
        return None
    if _client is None:
        _client = httpx.Client(
            base_url=ADMIN_API_URL,
            timeout=5.0,
            headers={"X-Ingest-Key": INGEST_SECRET_KEY},
        )
    return _client


def report_request_log(
    *,
    endpoint: str,
    method: str = "POST",
    status_code: int = 200,
    duration_ms: float = 0,
    user_ip: str = "",
    request_params: dict[str, Any] | None = None,
) -> None:
    """Report an API request to the admin backend (best-effort)."""
    client = _get_client()
    if client is None:
        return
    try:
        client.post(
            "/api/ingest/request-log",
            json={
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "user_ip": user_ip,
                "request_params": request_params,
            },
        )
    except Exception as exc:
        logger.debug("Failed to report request log to admin: %s", exc)


def report_user_profile(
    *,
    session_id: str = "",
    gender: str | None = None,
    mbti: str | None = None,
    color_preference: str = "",
    size_input: str | None = None,
    style_input: str | None = None,
    ai_recommended_size: str | None = None,
    ai_body_shape: str | None = None,
    ai_suggested_style: str | None = None,
    ai_reasoning: str | None = None,
    used_fallback: bool = False,
) -> None:
    """Report a user profile to the admin backend (best-effort)."""
    client = _get_client()
    if client is None:
        return
    try:
        client.post(
            "/api/ingest/profile",
            json={
                "session_id": session_id,
                "gender": gender,
                "mbti": mbti,
                "color_preference": color_preference,
                "size_input": size_input,
                "style_input": style_input,
                "ai_recommended_size": ai_recommended_size,
                "ai_body_shape": ai_body_shape,
                "ai_suggested_style": ai_suggested_style,
                "ai_reasoning": ai_reasoning,
                "used_fallback": used_fallback,
            },
        )
    except Exception as exc:
        logger.debug("Failed to report user profile to admin: %s", exc)


def report_page_view(
    *,
    source: str,
    page: str = "/",
    session_id: str = "",
    user_agent: str = "",
    ip: str = "",
) -> None:
    """Report a page view to the admin backend (best-effort)."""
    client = _get_client()
    if client is None:
        return
    try:
        client.post(
            "/api/ingest/page-view",
            json={
                "source": source,
                "page": page,
                "session_id": session_id,
                "user_agent": user_agent,
                "ip": ip,
            },
        )
    except Exception as exc:
        logger.debug("Failed to report page view to admin: %s", exc)
