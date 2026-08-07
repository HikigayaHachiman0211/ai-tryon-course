"""Data ingestion API — called by the main site to report analytics data.

These endpoints do NOT require JWT auth. They use a shared secret key
(X-Ingest-Key header) for lightweight authentication between services.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import PageView, RequestLog, TryonTask, UserProfile, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


def _verify_ingest_key(x_ingest_key: str = Header(...)):
    settings = get_settings()
    if not settings.INGEST_SECRET_KEY:
        raise HTTPException(503, "Ingest API is not configured")
    if x_ingest_key != settings.INGEST_SECRET_KEY:
        raise HTTPException(403, "Invalid ingest key")


# ---------------------------------------------------------------------------
# Request log ingestion
# ---------------------------------------------------------------------------

class RequestLogPayload(BaseModel):
    endpoint: str
    method: str = "POST"
    status_code: int = 200
    duration_ms: float = 0
    user_ip: str = ""
    request_params: dict | None = None


@router.post("/request-log")
def ingest_request_log(
    payload: RequestLogPayload,
    db: Session = Depends(get_db),
    _key=Depends(_verify_ingest_key),
):
    log = RequestLog(
        endpoint=payload.endpoint,
        method=payload.method,
        status_code=payload.status_code,
        duration_ms=payload.duration_ms,
        user_ip=payload.user_ip,
        request_params=payload.request_params,
    )
    db.add(log)
    db.commit()
    return {"ok": True, "id": log.id}


# ---------------------------------------------------------------------------
# User profile ingestion
# ---------------------------------------------------------------------------

_VALID_MBTI = {
    "INTJ", "INTP", "ENTJ", "ENTP",
    "INFJ", "INFP", "ENFJ", "ENFP",
    "ISTJ", "ISTP", "ESTJ", "ESTP",
    "ISFJ", "ISFP", "ESFJ", "ESFP",
}


class UserProfilePayload(BaseModel):
    session_id: str = ""
    gender: str | None = None
    mbti: str | None = None
    color_preference: str = ""
    size_input: str | None = None
    style_input: str | None = None
    ai_recommended_size: str | None = None
    ai_body_shape: str | None = None
    ai_suggested_style: str | None = None
    ai_reasoning: str | None = None
    used_fallback: bool = False


@router.post("/profile")
def ingest_profile(
    payload: UserProfilePayload,
    db: Session = Depends(get_db),
    _key=Depends(_verify_ingest_key),
):
    if not payload.session_id:
        payload.session_id = uuid.uuid4().hex[:16]

    # Reject non-standard MBTI values (e.g. size "M" written into the wrong field)
    validated_mbti = payload.mbti
    if validated_mbti and validated_mbti.upper() not in _VALID_MBTI:
        validated_mbti = None

    profile = UserProfile(
        session_id=payload.session_id,
        gender=payload.gender,
        mbti=validated_mbti,
        color_preference=payload.color_preference,
        size_input=payload.size_input,
        style_input=payload.style_input,
        ai_recommended_size=payload.ai_recommended_size,
        ai_body_shape=payload.ai_body_shape,
        ai_suggested_style=payload.ai_suggested_style,
        ai_reasoning=payload.ai_reasoning,
        used_fallback=payload.used_fallback,
        recommendation_count=1,
    )
    db.add(profile)
    db.commit()
    return {"ok": True, "id": profile.id}


# ---------------------------------------------------------------------------
# Batch request log ingestion (for buffered sends)
# ---------------------------------------------------------------------------

class BatchRequestLogPayload(BaseModel):
    logs: list[RequestLogPayload]


@router.post("/request-logs-batch")
def ingest_request_logs_batch(
    payload: BatchRequestLogPayload,
    db: Session = Depends(get_db),
    _key=Depends(_verify_ingest_key),
):
    count = 0
    for item in payload.logs:
        log = RequestLog(
            endpoint=item.endpoint,
            method=item.method,
            status_code=item.status_code,
            duration_ms=item.duration_ms,
            user_ip=item.user_ip,
            request_params=item.request_params,
        )
        db.add(log)
        count += 1
    db.commit()
    return {"ok": True, "count": count}


# ---------------------------------------------------------------------------
# Page view ingestion
# ---------------------------------------------------------------------------

class PageViewPayload(BaseModel):
    source: str  # "main_site" or "tryon_workbench"
    page: str = "/"
    session_id: str = ""
    user_agent: str = ""
    ip: str = ""


@router.post("/page-view")
def ingest_page_view(
    payload: PageViewPayload,
    db: Session = Depends(get_db),
    _key=Depends(_verify_ingest_key),
):
    pv = PageView(
        source=payload.source,
        page=payload.page,
        session_id=payload.session_id,
        user_agent=payload.user_agent,
        ip=payload.ip,
    )
    db.add(pv)
    db.commit()
    return {"ok": True, "id": pv.id}


# ---------------------------------------------------------------------------
# Try-on task ingestion (called by the workbench)
# ---------------------------------------------------------------------------

class TryonTaskPayload(BaseModel):
    task_id: str
    status: str = "queued"
    user_photo_url: str = ""
    product_id: int | None = None
    result_image_url: str | None = None
    error_type: str | None = None
    error_detail: str | None = None
    duration_ms: float | None = None
    model_used: str = ""


@router.post("/tryon-task")
def ingest_tryon_task(
    payload: TryonTaskPayload,
    db: Session = Depends(get_db),
    _key=Depends(_verify_ingest_key),
):
    """Upsert a try-on task record (create or update by task_id)."""
    existing = db.query(TryonTask).filter_by(id=payload.task_id).first()
    if existing:
        existing.status = payload.status
        if payload.result_image_url:
            existing.result_image_url = payload.result_image_url
        if payload.error_type:
            existing.error_type = payload.error_type
        if payload.error_detail:
            existing.error_detail = payload.error_detail
        if payload.duration_ms is not None:
            existing.duration_ms = payload.duration_ms
        if payload.model_used:
            existing.model_used = payload.model_used
        db.commit()
        return {"ok": True, "id": existing.id, "action": "updated"}
    else:
        task = TryonTask(
            id=payload.task_id,
            status=payload.status,
            user_photo_url=payload.user_photo_url,
            product_id=payload.product_id or 0,
            result_image_url=payload.result_image_url,
            error_type=payload.error_type,
            error_detail=payload.error_detail,
            duration_ms=payload.duration_ms,
            model_used=payload.model_used or "unknown",
        )
        db.add(task)
        db.commit()
        return {"ok": True, "id": task.id, "action": "created"}
