from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from uuid import uuid4

from app.config import get_settings, is_production, validate_production_settings
from app.database import AIAPIProvider, Product, get_db, init_db
from app.services import gcs
from app.i18n.locale import request_locale
from app.i18n.messages import error_message

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
    video_config,
    realtime_tryon,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    issues = validate_production_settings(settings)
    for issue in issues:
        if "JWT_SECRET_KEY" in issue:
            raise RuntimeError(f"[admin-security] {issue}")
        _log.critical("[admin-security] %s", issue)
    run_startup_db_init = os.getenv("RUN_STARTUP_DB_INIT", "true").strip().lower() not in {"0", "false", "no"}
    init_db(seed=run_startup_db_init)
    yield


app = FastAPI(title="AI 羽绒服推荐 — 站长管理后台", lifespan=lifespan)


@app.middleware("http")
async def locale_context(request: Request, call_next):
    request.state.locale = request_locale(request)
    request.state.request_id = request.headers.get("x-request-id") or str(uuid4())
    response = await call_next(request)
    response.headers["Content-Language"] = request.state.locale
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def _error_payload(request: Request, code: str, status_code: int, *, params: dict | None = None) -> dict:
    locale = getattr(request.state, "locale", request_locale(request))
    request_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id") or str(uuid4())
    message = error_message(code, locale, **(params or {}))
    return {"code": code, "message": message, "detail": message, "locale": locale, "request_id": request_id}


@app.exception_handler(HTTPException)
async def localized_http_exception(request: Request, exc: HTTPException):
    status_to_code = {401: "AUTH_INVALID_TOKEN", 403: "AUTH_INVALID_TOKEN", 404: "RESOURCE_NOT_FOUND", 422: "VALIDATION_ERROR"}
    detail_code = exc.detail.get("code") if isinstance(exc.detail, dict) else None
    code = detail_code or status_to_code.get(exc.status_code, "UNKNOWN_ERROR")
    payload = _error_payload(request, code, exc.status_code)
    if not detail_code and exc.status_code not in status_to_code and isinstance(exc.detail, str) and exc.detail.strip():
        detail_text = exc.detail.strip()
        payload["detail"] = detail_text
        payload["message"] = detail_text
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.exception_handler(RequestValidationError)
async def localized_validation_exception(request: Request, exc: RequestValidationError):
    del exc
    return JSONResponse(status_code=422, content=_error_payload(request, "VALIDATION_ERROR", 422))


@app.exception_handler(Exception)
async def localized_unexpected_exception(request: Request, exc: Exception):
    _log.exception("Unhandled admin request error: %s", type(exc).__name__)
    del exc
    return JSONResponse(status_code=500, content=_error_payload(request, "UNKNOWN_ERROR", 500))

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
app.include_router(video_config.router)
app.include_router(realtime_tryon.config_router)
app.include_router(realtime_tryon.admin_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "admin"}


@app.get("/health/deep")
def deep_health():
    settings = get_settings()
    checks = {
        "database": {"ok": False},
        "object_storage": {"ok": False, "provider": settings.OBJECT_STORAGE_PROVIDER},
        "fernet": {"ok": bool(settings.FERNET_SECRET_KEY), "configured": bool(settings.FERNET_SECRET_KEY)},
    }

    try:
        db_iter = get_db()
        session = next(db_iter)
        try:
            checks["database"] = {
                "ok": True,
                "product_count": session.query(Product.id).count(),
                "provider_count": session.query(AIAPIProvider.id).count(),
            }
        finally:
            db_iter.close()
    except Exception as exc:
        checks["database"] = {"ok": False, "error": type(exc).__name__}

    try:
        checks["object_storage"] = gcs._get_storage().health_check()
    except Exception as exc:
        checks["object_storage"] = {
            "ok": False,
            "provider": settings.OBJECT_STORAGE_PROVIDER,
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
