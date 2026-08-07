from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings, is_production, validate_production_settings
from app.database import AIAPIProvider, Product, get_db, init_db
from app.services import gcs

_log = logging.getLogger(__name__)

from app.routers import (
    auth,
    dashboard,
    products,
    history,
    system,
    images,
    tryon_tasks,
    prompts,
    annotations,
    profiles,
    sample_models,
    ingest,
    ai_config,
    voice_clone,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    issues = validate_production_settings(settings)
    for issue in issues:
        if any(name in issue for name in (
            "JWT_SECRET_KEY",
            "ADMIN_INIT_PASSWORD",
            "INGEST_SECRET_KEY",
            "FERNET_SECRET_KEY",
        )):
            raise RuntimeError(f"[admin-security] {issue}")
        _log.critical("[admin-security] %s", issue)
    init_db()
    yield


app = FastAPI(title="AI 羽绒服推荐 — 站长管理后台", lifespan=lifespan)

# CORS
settings = get_settings()
origins = [o.strip() for o in settings.CORS_ALLOW_ORIGINS.split(",") if o.strip()]
if is_production() and origins == ["*"]:
    _log.critical(
        "[admin-security] CORS_ALLOW_ORIGINS='*' in production — "
        "restricting to same-origin. Set CORS_ALLOW_ORIGINS to the real admin URL."
    )
    origins = []
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(products.router)
app.include_router(history.router)
app.include_router(system.router)
app.include_router(images.router)
app.include_router(tryon_tasks.router)
app.include_router(prompts.router)
app.include_router(annotations.router)
app.include_router(profiles.router)
app.include_router(sample_models.router)
app.include_router(ingest.router)
app.include_router(ai_config.router)
app.include_router(voice_clone.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "admin"}


@app.get("/health/deep")
def deep_health():
    settings = get_settings()
    checks = {
        "cloud_sql": {"ok": False},
        "cloud_storage": {"ok": False, "bucket": settings.GCS_BUCKET_NAME},
        "fernet": {"ok": bool(settings.FERNET_SECRET_KEY), "configured": bool(settings.FERNET_SECRET_KEY)},
    }

    try:
        db_iter = get_db()
        session = next(db_iter)
        try:
            checks["cloud_sql"] = {
                "ok": True,
                "product_count": session.query(Product.id).count(),
                "provider_count": session.query(AIAPIProvider.id).count(),
            }
        finally:
            db_iter.close()
    except Exception as exc:
        checks["cloud_sql"] = {"ok": False, "error": type(exc).__name__}

    try:
        items = gcs.list_blobs("", max_results=1)
        checks["cloud_storage"] = {
            "ok": True,
            "bucket": settings.GCS_BUCKET_NAME,
            "sample_count": len(items),
        }
    except Exception as exc:
        checks["cloud_storage"] = {
            "ok": False,
            "bucket": settings.GCS_BUCKET_NAME,
            "error": type(exc).__name__,
        }

    ok = all(check["ok"] for check in checks.values())
    return {"status": "ok" if ok else "degraded", "service": "admin", "checks": checks}


# Serve frontend dist if available
# Docker: /app/frontend/dist (PYTHONPATH=/app so __file__ is /app/app/main.py)
# Local:  admin/backend/../frontend/dist
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if not FRONTEND_DIST.is_dir():
    FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        resolved = (FRONTEND_DIST / full_path).resolve()
        if resolved.is_relative_to(FRONTEND_DIST) and resolved.is_file():
            return FileResponse(resolved)
        return FileResponse(FRONTEND_DIST / "index.html")
