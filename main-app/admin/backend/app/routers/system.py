from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import func, text

from app.auth import get_current_admin
from app.config import get_settings
from app.database import (
    Product, AdminUser, RequestLog, TryonTask, PromptConfig,
    UserProfile, AnnotationTask, AnnotationRecord, SampleModel,
    AIAPIProvider, AIFeatureConfig, AIAPITestLog,
    get_db,
)

router = APIRouter(prefix="/api/admin/system", tags=["system"])


@router.get("/health")
async def health_check(admin=Depends(get_current_admin)):
    settings = get_settings()
    main_status = {"url": settings.MAIN_SITE_URL, "status": "unknown", "latency_ms": 0}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            import time
            start = time.time()
            resp = await client.get(f"{settings.MAIN_SITE_URL}/health")
            latency = (time.time() - start) * 1000
            main_status = {
                "url": settings.MAIN_SITE_URL,
                "status": "online" if resp.status_code == 200 else "error",
                "status_code": resp.status_code,
                "latency_ms": round(latency, 1),
            }
    except Exception as e:
        main_status["status"] = "offline"
        main_status["error"] = str(e)

    return {
        "status": "ok" if main_status["status"] == "online" else "degraded",
        "main_site": main_status,
    }


@router.get("/errors")
async def proxy_errors(limit: int = 50, admin=Depends(get_current_admin)):
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.MAIN_SITE_URL}/api/debug/errors/recent", params={"limit": limit})
            if resp.status_code == 200:
                return resp.json()
            return {"errors": [], "detail": f"主站返回 {resp.status_code}"}
    except Exception as e:
        return {"errors": [], "detail": str(e)}


@router.get("/config")
def get_config(admin=Depends(get_current_admin)):
    settings = get_settings()
    return {
        "DATABASE_URL": _mask(settings.DATABASE_URL),
        "GCS_BUCKET_NAME": settings.GCS_BUCKET_NAME,
        "PUBLIC_IMAGE_BASE_URL": settings.PUBLIC_IMAGE_BASE_URL,
        "MAIN_SITE_URL": settings.MAIN_SITE_URL,
        "TRYON_WORKBENCH_URL": settings.TRYON_WORKBENCH_URL or "(未配置)",
        "JWT_SECRET_KEY": "***",
        "GEMINI_API_KEY": "***" if settings.GEMINI_API_KEY else "(未配置)",
    }


@router.get("/db-stats")
def db_stats(admin=Depends(get_current_admin), db=Depends(get_db)):
    tables = {
        "products": db.query(func.count(Product.id)).scalar() or 0,
        "admin_users": db.query(func.count(AdminUser.id)).scalar() or 0,
        "request_logs": db.query(func.count(RequestLog.id)).scalar() or 0,
        "tryon_tasks": db.query(func.count(TryonTask.id)).scalar() or 0,
        "prompt_configs": db.query(func.count(PromptConfig.id)).scalar() or 0,
        "user_profiles": db.query(func.count(UserProfile.id)).scalar() or 0,
        "annotation_tasks": db.query(func.count(AnnotationTask.id)).scalar() or 0,
        "annotation_records": db.query(func.count(AnnotationRecord.id)).scalar() or 0,
        "sample_models": db.query(func.count(SampleModel.id)).scalar() or 0,
        "ai_api_providers": db.query(func.count(AIAPIProvider.id)).scalar() or 0,
        "ai_feature_configs": db.query(func.count(AIFeatureConfig.id)).scalar() or 0,
        "ai_api_test_logs": db.query(func.count(AIAPITestLog.id)).scalar() or 0,
    }
    return tables


def _mask(value: str) -> str:
    if "://" in value:
        parts = value.split("://", 1)
        scheme = parts[0]
        rest = parts[1]
        if "@" in rest:
            creds, host = rest.rsplit("@", 1)
            return f"{scheme}://***@{host}"
        return f"{scheme}://***"
    return "***"
