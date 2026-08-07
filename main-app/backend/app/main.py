from __future__ import annotations

import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette import status
from sqlalchemy import select

from app.catalog_repository import get_catalog_product, get_catalog_products, get_catalog_source_label
from app.catalog_seed import resolve_local_image_path
from app.database import PROJECT_ROOT, Product, SessionLocal, count_products, ensure_database
from app.errors import AppError, app_error_response, build_error_payload, debug_page_response, get_error_catalog, get_recent_errors, get_request_id, record_error_event, unexpected_error_response
from app.history import MAX_HISTORY_ENTRIES, generate_result_id, get_history_detail, get_thumbnail_path, list_history, save_history
from app.history import _read_local_index, _write_local_index, _ensure_local_dirs
from app.recommendation import analyze_selected_product, list_catalog_products, recommend_products
from app import admin_report, gcs_storage
from app.assistant.router import router as assistant_router
from app.assistant.voice.voice_router import router as voice_router

logger = logging.getLogger(__name__)
mimetypes.add_type("image/webp", ".webp")


@asynccontextmanager
async def lifespan(_: FastAPI):
    catalog_products = get_catalog_products()
    if catalog_products:
        logger.info(
            "Catalog read model active with %d products from %s; skipping startup database bootstrap.",
            len(catalog_products),
            get_catalog_source_label() or "seed source",
        )
    else:
        ensure_database(seed_if_empty=True)
    # Preload history index from GCS so cold-start containers have full history
    _ensure_local_dirs()
    local_entries = _read_local_index()
    if not local_entries:
        gcs_entries = gcs_storage.load_history_index()
        if gcs_entries:
            _write_local_index(gcs_entries)
            logger.info("Preloaded %d history entries from GCS", len(gcs_entries))
    yield


app = FastAPI(
    title="AI Try-On Backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(assistant_router)
app.include_router(voice_router)

default_debug_pages = "false" if os.getenv("K_SERVICE") else "true"
debug_pages_enabled = os.getenv("ENABLE_DEBUG_PAGES", default_debug_pages).strip().lower() == "true"

cors_origins = [origin.strip() for origin in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",") if origin.strip()]
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
    record_error_event(
        request=request,
        code="SYS-001",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message="请求参数校验失败",
        details=details,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=build_error_payload(
            code="SYS-001",
            message="请求参数校验失败",
            request_id=get_request_id(request),
            details=details,
        ),
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "HTTP 异常"
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
            checks["cloud_sql"] = {
                "ok": True,
                "product_count": count_products(session),
            }
    except Exception as exc:
        logger.warning("Main deep health Cloud SQL check failed: %s", exc)
        checks["cloud_sql"] = {"ok": False, "error": exc.__class__.__name__}

    try:
        bucket = gcs_storage._ensure_bucket()
        if bucket is None:
            checks["cloud_storage"] = {
                "ok": False,
                "bucket": gcs_storage.GCS_BUCKET_NAME,
                "error": "bucket_unavailable",
            }
        else:
            sample_count = sum(1 for _ in bucket.list_blobs(max_results=1))
            checks["cloud_storage"] = {
                "ok": True,
                "bucket": gcs_storage.GCS_BUCKET_NAME,
                "sample_count": sample_count,
            }
    except Exception as exc:
        logger.warning("Main deep health Cloud Storage check failed: %s", exc)
        checks["cloud_storage"] = {
            "ok": False,
            "bucket": gcs_storage.GCS_BUCKET_NAME,
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
        "error_codes": get_error_catalog(),
        "recent_errors": get_recent_errors(limit=50),
    }


@app.get("/api/debug/errors/recent")
def get_recent_error_events(request: Request, limit: int = 50) -> dict:
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
    query: str | None = None,
    gender: str | None = None,
    platform: str | None = None,
    mode: str = "gender",
    offset: int = 0,
    limit: int = 60,
    price_min: float | None = None,
    price_max: float | None = None,
):
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
    ai_provider: str | None = Form(default=None, description="AI 引擎选择: auto / gemini / deepseek / mimo"),
    vision_provider: str | None = Form(default=None, description="图像分析引擎: mimo / gemini / auto (默认由后台配置决定)"),
):
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
        ai_provider=ai_provider,
        vision_provider=vision_provider,
        price_min=price_min,
        price_max=price_max,
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
        used_fallback=inference.get("rule_fallback_used", not inference.get("gemini_used", False) and not inference.get("mimo_used", False)),
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
    ai_provider: str | None = Form(default=None, description="AI 引擎选择: auto / gemini / deepseek / mimo"),
    vision_provider: str | None = Form(default=None, description="图像分析引擎: mimo / gemini / auto (默认由后台配置决定)"),
):
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
        ai_provider=ai_provider,
        vision_provider=vision_provider,
        price_min=price_min,
        price_max=price_max,
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
def get_history(limit: int = 50):
    limit = max(1, min(limit, MAX_HISTORY_ENTRIES))
    entries = list_history(limit=limit)
    return {"items": entries, "total": len(entries)}


@app.get("/api/history/{result_id}")
def get_history_entry(result_id: str):
    detail = get_history_detail(result_id)
    if detail is None:
        raise AppError(
            code="HIST-001",
            message="历史记录不存在",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"result_id": result_id},
        )
    return detail


@app.get("/api/history/{result_id}/thumbnail")
def get_history_thumbnail(result_id: str):
    thumbnail_path = get_thumbnail_path(result_id)
    if thumbnail_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not found")
    return FileResponse(thumbnail_path, media_type="image/png")


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend_app(full_path: str, request: Request, background_tasks: BackgroundTasks):
    normalized_path = full_path.strip("/")
    if normalized_path.startswith(("api/", "static/", "debug/")) or normalized_path in {"docs", "redoc", "openapi.json", "health"}:
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
