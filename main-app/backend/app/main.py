from __future__ import annotations

import hmac
import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette import status
from sqlalchemy import select
from pydantic import BaseModel

from app.catalog_repository import get_catalog_product, get_catalog_products, get_catalog_source_label
from app.catalog_seed import resolve_local_image_path
from app.database import PROJECT_ROOT, Product, SessionLocal, count_products, ensure_database
from app.errors import AppError, app_error_response, build_error_payload, debug_page_response, get_error_catalog, get_recent_errors, get_request_id, get_request_locale, record_error_event, unexpected_error_response
from app.history import MAX_HISTORY_ENTRIES, generate_result_id, get_history_detail, get_thumbnail_bytes, get_thumbnail_path, list_history, localize_history_result, save_history
from app.history import _read_local_index, _write_local_index, _ensure_local_dirs
from app.recommendation import analyze_selected_product, list_catalog_products, recommend_products
from app import admin_report, gcs_storage
from app.assistant.router import router as assistant_router
from app.assistant.voice.voice_router import router as voice_router
from app.i18n.locale import resolve_locale
from app.i18n.catalog import localize_product_item, localize_recommendation_result, localize_style_lab_result
from app.i18n.messages import error_message

logger = logging.getLogger(__name__)
mimetypes.add_type("image/webp", ".webp")


@asynccontextmanager
async def lifespan(_: FastAPI):
    catalog_products = get_catalog_products()
    run_startup_db_init = os.getenv("RUN_STARTUP_DB_INIT", "true").strip().lower() not in {"0", "false", "no"}
    if catalog_products:
        logger.info(
            "Catalog read model active with %d products from %s; skipping startup database bootstrap.",
            len(catalog_products),
            get_catalog_source_label() or "seed source",
        )
    elif run_startup_db_init:
        ensure_database(seed_if_empty=True)
    else:
        logger.info("RUN_STARTUP_DB_INIT=false; skipping startup database bootstrap.")
    # Preload the configured object-storage history index so cold-start
    # containers have full history without selecting a cloud provider here.
    _ensure_local_dirs()
    local_entries = _read_local_index()
    if not local_entries:
        gcs_entries = gcs_storage.load_history_index()
        if gcs_entries:
            _write_local_index(gcs_entries)
            logger.info("Preloaded %d history entries from object storage", len(gcs_entries))
    yield


app = FastAPI(
    title="AI Try-On Backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(assistant_router)
app.include_router(voice_router)


class LocalizeResultRequest(BaseModel):
    kind: Literal["recommend", "style-lab", "product"]
    result: dict[str, Any]
    locale: str | None = None


@app.post("/api/localize-result")
def localize_current_result(request: Request, payload: LocalizeResultRequest):
    locale = resolve_locale(payload.locale, request.headers.get("accept-language"))
    if payload.kind == "recommend":
        return localize_recommendation_result(payload.result, locale)
    if payload.kind == "style-lab":
        return localize_style_lab_result(payload.result, locale)
    return localize_product_item(payload.result, locale)

default_debug_pages = (
    "false"
    if (
        os.getenv("K_SERVICE")
        or os.getenv("CONTAINER_APP_NAME")
        or os.getenv("APP_ENV", "").strip().lower() in {"production", "prod"}
    )
    else "true"
)
debug_pages_enabled = os.getenv("ENABLE_DEBUG_PAGES", default_debug_pages).strip().lower() == "true"

cors_origins = [origin.strip() for origin in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",") if origin.strip()]
production_mode = os.getenv("APP_ENV", "").strip().lower() in {"production", "prod"}
if production_mode and (not cors_origins or cors_origins == ["*"]):
    raise RuntimeError("CORS_ALLOW_ORIGINS must contain exact origins in production")
allow_all_origins = not cors_origins or cors_origins == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all_origins else cors_origins,
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

public_image_base_url = os.getenv("PUBLIC_IMAGE_BASE_URL", "").strip()
if public_image_base_url:
    logger.info("Product images will be served from PUBLIC_IMAGE_BASE_URL=%s", public_image_base_url)
else:
    logger.info("Product images will be served from local dataset directories.")

frontend_dist_dir = PROJECT_ROOT / "frontend" / "dist"
frontend_index_file = frontend_dist_dir / "index.html"
if frontend_index_file.exists():
    logger.info("Serving built frontend from %s", frontend_dist_dir)


def filter_products_by_price(
    products: list[Product],
    price_min: float | None,
    price_max: float | None,
) -> list[Product]:
    filtered_products = products
    if price_min is not None:
        filtered_products = [product for product in filtered_products if product.price >= price_min]
    if price_max is not None:
        filtered_products = [product for product in filtered_products if product.price <= price_max]
    return filtered_products


def load_database_products(
    price_min: float | None,
    price_max: float | None,
) -> tuple[list[Product], int]:
    with SessionLocal() as session:
        stmt = select(Product)
        if price_min is not None:
            stmt = stmt.where(Product.price >= price_min)
        if price_max is not None:
            stmt = stmt.where(Product.price <= price_max)
        products = list(session.scalars(stmt))
        return products, count_products(session)


def load_database_product(product_id: int) -> Product | None:
    with SessionLocal() as session:
        return session.get(Product, product_id)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = get_request_id(request)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError):
    return app_error_response(request, exc)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    details = exc.errors()
    locale = get_request_locale(request)
    message = error_message("SYS-001", locale)
    record_error_event(
        request=request,
        code="SYS-001",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message=message,
        details=details,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=build_error_payload(
            code="SYS-001",
            message=message,
            request_id=get_request_id(request),
            details=details,
            locale=locale,
        ),
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException):
    locale = get_request_locale(request)
    message = error_message("SYS-002", locale)
    record_error_event(
        request=request,
        code="SYS-002",
        status_code=exc.status_code,
        message=message,
        details=exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=build_error_payload(
            code="SYS-002",
            message=message,
            request_id=get_request_id(request),
            details=exc.detail,
            locale=locale,
        ),
    )


@app.exception_handler(Exception)
async def handle_unexpected_exception(request: Request, exc: Exception):
    return unexpected_error_response(request, exc)


def ensure_debug_pages_enabled() -> None:
    if not debug_pages_enabled:
        raise AppError(
            code="DBG-001",
            message="调试页面已禁用",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"hint": "Set ENABLE_DEBUG_PAGES=true to enable debug pages."},
        )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/deep")
def health_deep() -> dict:
    checks: dict[str, dict] = {}

    try:
        with SessionLocal() as session:
            checks["database"] = {
                "ok": True,
                "product_count": count_products(session),
            }
    except Exception as exc:
        logger.warning("Main deep health database check failed: %s", type(exc).__name__)
        checks["database"] = {"ok": False, "error": exc.__class__.__name__}

    try:
        checks["object_storage"] = gcs_storage.health_check()
    except Exception as exc:
        logger.warning("Main deep health object storage check failed: %s", type(exc).__name__)
        checks["object_storage"] = {
            "ok": False,
            "error": exc.__class__.__name__,
        }

    try:
        from app.ai_runtime_config import get_diagnostics

        diagnostics = get_diagnostics()
        checks["ai_runtime"] = {
            "ok": bool(diagnostics.get("db_available")),
            "db_url_source": diagnostics.get("db_url_source"),
            "tables": diagnostics.get("tables", {}),
            "providers": diagnostics.get("providers", {}),
            "features": diagnostics.get("features", {}),
        }
    except Exception as exc:
        logger.warning("Main deep health AI runtime check failed: %s", exc)
        checks["ai_runtime"] = {"ok": False, "error": exc.__class__.__name__}

    ok = all(check.get("ok") for check in checks.values())
    return {
        "status": "ok" if ok else "degraded",
        "service": "main",
        "checks": checks,
    }


@app.get("/")
def root():
    if frontend_index_file.exists():
        return serve_frontend_asset("")
    return {
        "service": "ai-tryon-backend",
        "status": "ok",
        "health": "/health",
        "docs": "/docs",
    }


@app.get("/api/debug/error-codes")
def get_error_codes(request: Request) -> dict:
    ensure_debug_pages_enabled()
    return {
        "request_id": get_request_id(request),
        "error_codes": get_error_catalog(get_request_locale(request)),
        "recent_errors": get_recent_errors(limit=50),
    }


@app.get("/api/debug/errors/recent")
def get_recent_error_events(request: Request, limit: int = 50) -> dict:
    provided_key = request.headers.get("X-Ingest-Key", "")
    expected_key = admin_report.INGEST_SECRET_KEY
    authorized_internal = bool(provided_key and expected_key and hmac.compare_digest(provided_key, expected_key))
    if not authorized_internal:
        ensure_debug_pages_enabled()
    limit = max(1, min(limit, 200))
    return {
        "request_id": get_request_id(request),
        "count": limit,
        "items": get_recent_errors(limit=limit),
    }


@app.get("/api/debug/ai-runtime")
def get_ai_runtime_debug(request: Request) -> dict:
    """Return non-sensitive AI runtime diagnostics.

    Shows DB source, provider status, feature config — without exposing API keys.
    Only available when debug pages are enabled.
    """
    ensure_debug_pages_enabled()
    from app.ai_runtime_config import get_diagnostics
    return {
        "request_id": get_request_id(request),
        **get_diagnostics(),
    }


@app.get("/debug/error-codes")
def debug_error_codes_page(request: Request):
    ensure_debug_pages_enabled()
    return debug_page_response(str(request.base_url))


@app.get("/api/products")
def get_products(
    request: Request,
    query: str | None = None,
    locale: str | None = Query(default=None),
    gender: str | None = None,
    platform: str | None = None,
    mode: str = "gender",
    offset: int = 0,
    limit: int = 60,
    price_min: float | None = None,
    price_max: float | None = None,
):
    resolved_locale = resolve_locale(locale, request.headers.get("accept-language"))
    catalog_products = get_catalog_products()
    if catalog_products:
        products = filter_products_by_price(catalog_products, price_min, price_max)
    else:
        products, _ = load_database_products(price_min, price_max)
    return list_catalog_products(
        products=products,
        query=query,
        gender=gender,
        platform=platform,
        mode=mode,
        offset=offset,
        limit=limit,
        locale=resolved_locale,
    )


@app.post("/api/recommend")
def recommend(
    request: Request,
    background_tasks: BackgroundTasks,
    photo: UploadFile | None = File(default=None, description="用户全身照"),
    color_preference: str = Form(..., description="颜色喜好"),
    brand_preference: str | None = Form(default=None, description="品牌偏好，可选"),
    gender: str | None = Form(default=None, description="用户性别，可选但建议填写"),
    price_min: float | None = Form(default=None, description="价格下限"),
    price_max: float | None = Form(default=None, description="价格上限"),
    mbti: str | None = Form(default=None, description="MBTI，可选"),
    size: str | None = Form(default=None, description="尺码，可选"),
    style_preference: str | None = Form(default=None, description="款式偏好，可选"),
    gemini_api_key: str | None = Form(default=None, description="前端传入的 Gemini API Key"),
    gemini_model: str | None = Form(default=None, description="可覆盖默认模型名"),
    deepseek_api_key: str | None = Form(default=None, description="前端传入的 Deepseek API Key"),
    deepseek_model: str | None = Form(default=None, description="可覆盖默认 Deepseek 模型名"),
    mimo_api_key: str | None = Form(default=None, description="前端传入的 MiMo API Key"),
    mimo_model: str | None = Form(default=None, description="可覆盖默认 MiMo 模型名"),
    opencode_go_api_key: str | None = Form(default=None, description="前端传入的 OpenCode Go API Key"),
    opencode_go_model: str | None = Form(default=None, description="可覆盖默认 OpenCode Go 模型名"),
    ai_provider: str | None = Form(default=None, description="AI 引擎选择: auto / gemini / deepseek / mimo / opencode_go"),
    vision_provider: str | None = Form(default=None, description="图像分析引擎: mimo / gemini / deepseek / opencode_go / auto (默认由后台配置决定)"),
    locale: str | None = Form(default=None, description="界面语言，可选"),
):
    resolved_locale = resolve_locale(locale, request.headers.get("accept-language"))
    if price_min is not None and price_max is not None and price_min > price_max:
        raise AppError(
            code="REC-001",
            message="price_min 不能大于 price_max",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"price_min": price_min, "price_max": price_max},
        )

    image_bytes = photo.file.read() if photo else None
    mime_type = photo.content_type if photo else None

    catalog_products = get_catalog_products()
    if catalog_products:
        total_catalog_count = len(catalog_products)
        products = filter_products_by_price(catalog_products, price_min, price_max)
    else:
        products, total_catalog_count = load_database_products(price_min, price_max)
    result = recommend_products(
        products=products,
        total_catalog_count=total_catalog_count,
        image_bytes=image_bytes,
        mime_type=mime_type,
        color_preference=color_preference,
        brand_preference=brand_preference,
        gender=gender,
        mbti=mbti,
        size=size,
        style_preference=style_preference,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        deepseek_api_key=deepseek_api_key,
        deepseek_model=deepseek_model,
        mimo_api_key=mimo_api_key,
        mimo_model=mimo_model,
        opencode_go_api_key=opencode_go_api_key,
        opencode_go_model=opencode_go_model,
        ai_provider=ai_provider,
        vision_provider=vision_provider,
        price_min=price_min,
        price_max=price_max,
        locale=resolved_locale,
    )

    # Upload user photo to GCS (best-effort) and inject URL into result
    if image_bytes:
        photo_url = gcs_storage.save_user_photo(
            generate_result_id(),
            image_bytes,
            content_type=mime_type or "image/jpeg",
        )
        if photo_url:
            result["user_photo_url"] = photo_url

    base_url = str(request.base_url).rstrip("/")
    background_tasks.add_task(save_history, result, "recommend", base_url)

    # Report to admin backend (best-effort, background)
    user_ip = request.client.host if request.client else ""
    inference = result.get("inference", {})
    background_tasks.add_task(
        admin_report.report_request_log,
        endpoint="recommend",
        method="POST",
        status_code=200,
        user_ip=user_ip,
        request_params={"color": color_preference, "gender": gender, "brand": brand_preference},
    )
    background_tasks.add_task(
        admin_report.report_user_profile,
        gender=gender,
        mbti=mbti,
        color_preference=color_preference,
        size_input=size,
        style_input=style_preference,
        ai_recommended_size=inference.get("resolved_size"),
        ai_body_shape=inference.get("body_shape"),
        ai_suggested_style=inference.get("resolved_style"),
        ai_reasoning=inference.get("reasoning"),
        used_fallback=inference.get("rule_fallback_used", inference.get("ai_provider", "none") == "none"),
    )

    return result


@app.post("/api/style-lab/analyze")
def analyze_style_lab(
    request: Request,
    background_tasks: BackgroundTasks,
    product_id: int = Form(..., description="所选商品 ID"),
    photo: UploadFile | None = File(default=None, description="用户全身照"),
    color_preference: str = Form(..., description="颜色喜好"),
    brand_preference: str | None = Form(default=None, description="品牌偏好，可选"),
    gender: str | None = Form(default=None, description="用户性别"),
    price_min: float | None = Form(default=None, description="价格下限"),
    price_max: float | None = Form(default=None, description="价格上限"),
    mbti: str | None = Form(default=None, description="MBTI，可选"),
    size: str | None = Form(default=None, description="尺码，可选"),
    style_preference: str | None = Form(default=None, description="款式偏好，可选"),
    gemini_api_key: str | None = Form(default=None, description="前端传入的 Gemini API Key"),
    gemini_model: str | None = Form(default=None, description="可覆盖默认模型名"),
    deepseek_api_key: str | None = Form(default=None, description="前端传入的 Deepseek API Key"),
    deepseek_model: str | None = Form(default=None, description="可覆盖默认 Deepseek 模型名"),
    mimo_api_key: str | None = Form(default=None, description="前端传入的 MiMo API Key"),
    mimo_model: str | None = Form(default=None, description="可覆盖默认 MiMo 模型名"),
    opencode_go_api_key: str | None = Form(default=None, description="前端传入的 OpenCode Go API Key"),
    opencode_go_model: str | None = Form(default=None, description="可覆盖默认 OpenCode Go 模型名"),
    ai_provider: str | None = Form(default=None, description="AI 引擎选择: auto / gemini / deepseek / mimo / opencode_go"),
    vision_provider: str | None = Form(default=None, description="图像分析引擎: mimo / gemini / deepseek / opencode_go / auto (默认由后台配置决定)"),
    locale: str | None = Form(default=None, description="界面语言，可选"),
):
    resolved_locale = resolve_locale(locale, request.headers.get("accept-language"))
    product = get_catalog_product(product_id)
    if product is None:
        product = load_database_product(product_id)
    if not product:
        raise AppError(
            code="LAB-001",
            message="所选商品不存在",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"product_id": product_id},
        )

    if price_min is not None and price_max is not None and price_min > price_max:
        raise AppError(
            code="REC-001",
            message="price_min 不能大于 price_max",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"price_min": price_min, "price_max": price_max},
        )

    image_bytes = photo.file.read() if photo else None
    mime_type = photo.content_type if photo else None
    result = analyze_selected_product(
        product=product,
        image_bytes=image_bytes,
        mime_type=mime_type,
        color_preference=color_preference,
        brand_preference=brand_preference,
        gender=gender,
        mbti=mbti,
        size=size,
        style_preference=style_preference,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        deepseek_api_key=deepseek_api_key,
        deepseek_model=deepseek_model,
        mimo_api_key=mimo_api_key,
        mimo_model=mimo_model,
        opencode_go_api_key=opencode_go_api_key,
        opencode_go_model=opencode_go_model,
        ai_provider=ai_provider,
        vision_provider=vision_provider,
        price_min=price_min,
        price_max=price_max,
        locale=resolved_locale,
    )

    # Upload user photo to GCS (best-effort) and inject URL into result
    if image_bytes:
        photo_url = gcs_storage.save_user_photo(
            generate_result_id(),
            image_bytes,
            content_type=mime_type or "image/jpeg",
        )
        if photo_url:
            result["user_photo_url"] = photo_url

    base_url = str(request.base_url).rstrip("/")
    background_tasks.add_task(save_history, result, "style-lab", base_url)

    # Report to admin backend (best-effort, background)
    user_ip = request.client.host if request.client else ""
    background_tasks.add_task(
        admin_report.report_request_log,
        endpoint="style-lab",
        method="POST",
        status_code=200,
        user_ip=user_ip,
        request_params={"product_id": product_id, "color": color_preference, "gender": gender},
    )

    return result


@app.get("/static/products/{image_path:path}")
def get_product_image(image_path: str):
    resolved_path = resolve_local_image_path(unquote(image_path))
    if resolved_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product image not found")
    media_type = mimetypes.guess_type(resolved_path.name)[0] or "application/octet-stream"
    return FileResponse(resolved_path, media_type=media_type)


@app.get("/api/history")
def get_history(request: Request, locale: str | None = Query(default=None), limit: int = 50):
    resolved_locale = resolve_locale(locale, request.headers.get("accept-language"))
    limit = max(1, min(limit, MAX_HISTORY_ENTRIES))
    entries = list_history(limit=limit, locale=resolved_locale)
    return {"items": entries, "total": len(entries), "locale": resolved_locale}


@app.get("/api/history/{result_id}")
def get_history_entry(request: Request, result_id: str, locale: str | None = Query(default=None)):
    resolved_locale = resolve_locale(locale, request.headers.get("accept-language"))
    detail = get_history_detail(result_id)
    if detail is None:
        raise AppError(
            code="HIST-001",
            message="历史记录不存在",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"result_id": result_id},
        )
    return localize_history_result(detail, resolved_locale)


@app.get("/api/history/{result_id}/thumbnail")
def get_history_thumbnail(result_id: str):
    thumb_bytes = get_thumbnail_bytes(result_id)
    if not thumb_bytes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not found")
    return Response(content=thumb_bytes, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@app.get("/api/media/user-photos/{photo_name}")
def get_private_user_photo(request: Request, photo_name: str, st: str | None = Query(default=None)):
    provided_key = request.headers.get("X-Ingest-Key", "")
    expected_key = admin_report.INGEST_SECRET_KEY
    internal_ok = bool(provided_key and expected_key and hmac.compare_digest(provided_key, expected_key))
    if not internal_ok and not gcs_storage.verify_signed_user_photo_token(photo_name, st):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    loaded = gcs_storage.get_user_photo(photo_name)
    if loaded is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User photo not found")
    data, content_type = loaded
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=300"})


@app.get("/sample-models/{gender}/{filename}")
def get_sample_model_image(gender: str, filename: str):
    if gender not in {"male", "female"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid gender")
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

    candidate_roots = [
        frontend_dist_dir / "sample-models" / gender,
        PROJECT_ROOT / "frontend" / "public" / "sample-models" / gender,
    ]
    for root in candidate_roots:
        resolved_root = root.resolve()
        candidate = (root / safe_name).resolve()
        try:
            candidate.relative_to(resolved_root)
        except ValueError:
            continue
        if candidate.is_file():
            media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            return FileResponse(candidate, media_type=media_type)

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sample model not found")


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend_app(full_path: str, request: Request, background_tasks: BackgroundTasks):
    normalized_path = full_path.strip("/")
    if normalized_path == "sample-models" or normalized_path.startswith(("api/", "static/", "debug/", "sample-models/")) or normalized_path in {"docs", "redoc", "openapi.json", "health"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    background_tasks.add_task(
        admin_report.report_page_view,
        source="main_site",
        page=f"/{normalized_path}" if normalized_path else "/",
        user_agent=request.headers.get("user-agent", ""),
        ip=request.client.host if request.client else "",
    )
    return serve_frontend_asset(normalized_path)


def serve_frontend_asset(path: str):
    if not frontend_index_file.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    normalized_path = path.strip("/")
    if not normalized_path:
        return FileResponse(frontend_index_file)

    requested_file = (frontend_dist_dir / normalized_path).resolve()
    try:
        requested_file.relative_to(frontend_dist_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found") from exc

    if requested_file.is_file():
        return FileResponse(requested_file)

    return FileResponse(frontend_index_file)
