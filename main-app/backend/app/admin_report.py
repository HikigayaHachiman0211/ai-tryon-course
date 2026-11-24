"""Admin data reporting — writes to shared DB or sends analytics via HTTP.

In ACA scale-to-zero deployments (ADMIN_REPORT_MODE=db), analytics are written
directly to PostgreSQL so normal main-site traffic never wakes tryon-admin.
All calls are best-effort and never block the main request flow.
"""
from __future__ import annotations

from datetime import datetime
import logging
import os
from typing import Any

import httpx
from sqlalchemy import text

logger = logging.getLogger(__name__)

ADMIN_API_URL: str = os.getenv("ADMIN_API_URL", "").rstrip("/")
INGEST_SECRET_KEY: str = os.getenv("INGEST_SECRET_KEY", "")
ADMIN_REPORT_MODE: str = os.getenv("ADMIN_REPORT_MODE", "auto").strip().lower()

_client: httpx.Client | None = None


def _use_direct_db() -> bool:
    if ADMIN_REPORT_MODE == "off":
        return False
    if ADMIN_REPORT_MODE == "db":
        return True
    if ADMIN_REPORT_MODE == "http":
        return False
    if not ADMIN_API_URL and os.getenv("ADMIN_REPORT_DB_FALLBACK", "").strip().lower() in ("1", "true", "yes"):
        return True
    return False


def _exec_direct_sql(stmt: str, params: dict[str, Any]) -> None:
    from app.database import ENGINE

    dialect_stmt = stmt
    if ENGINE.dialect.name == "postgresql":
        dialect_stmt = dialect_stmt.replace(":request_params", "CAST(:request_params AS json)")
    with ENGINE.begin() as conn:
        conn.execute(text(dialect_stmt), params)


def _get_client() -> httpx.Client | None:
    global _client
    if ADMIN_REPORT_MODE == "off" or _use_direct_db() or not ADMIN_API_URL:
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
    """Report an API request to the shared DB or admin backend (best-effort)."""
    if _use_direct_db():
        try:
            import json
            _exec_direct_sql(
                "INSERT INTO request_logs (timestamp, endpoint, method, status_code, duration_ms, user_ip, request_params) "
                "VALUES (:timestamp, :endpoint, :method, :status_code, :duration_ms, :user_ip, :request_params)",
                {
                    "timestamp": datetime.utcnow(),
                    "endpoint": endpoint,
                    "method": method,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "user_ip": user_ip,
                    "request_params": json.dumps(request_params, ensure_ascii=False) if request_params is not None else None,
                },
            )
        except Exception as exc:
            logger.debug("Failed to write request log to DB: %s", exc)
        return
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
    """Report a user profile to the shared DB or admin backend (best-effort)."""
    if _use_direct_db():
        try:
            _exec_direct_sql(
                "INSERT INTO user_profiles (created_at, session_id, gender, mbti, color_preference, size_input, style_input, "
                "ai_recommended_size, ai_body_shape, ai_suggested_style, ai_reasoning, used_fallback, recommendation_count) "
                "VALUES (:created_at, :session_id, :gender, :mbti, :color_preference, :size_input, :style_input, "
                ":ai_recommended_size, :ai_body_shape, :ai_suggested_style, :ai_reasoning, :used_fallback, :recommendation_count)",
                {
                    "created_at": datetime.utcnow(),
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
                    "recommendation_count": 0,
                },
            )
        except Exception as exc:
            logger.debug("Failed to write user profile to DB: %s", exc)
        return
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
    """Report a page view to the shared DB or admin backend (best-effort)."""
    if _use_direct_db():
        try:
            _exec_direct_sql(
                "INSERT INTO page_views (timestamp, source, page, session_id, user_agent, ip) "
                "VALUES (:timestamp, :source, :page, :session_id, :user_agent, :ip)",
                {
                    "timestamp": datetime.utcnow(),
                    "source": source,
                    "page": page,
                    "session_id": session_id,
                    "user_agent": user_agent,
                    "ip": ip,
                },
            )
        except Exception as exc:
            logger.debug("Failed to write page view to DB: %s", exc)
        return
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
