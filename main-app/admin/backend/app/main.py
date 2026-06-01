from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import init_db

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
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI 羽绒服推荐 — 站长管理后台", lifespan=lifespan)

# CORS
settings = get_settings()
origins = [o.strip() for o in settings.CORS_ALLOW_ORIGINS.split(",") if o.strip()]
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


@app.get("/health")
def health():
    return {"status": "ok", "service": "admin"}


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
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
