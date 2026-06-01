from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    func,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy.types import JSON

from app.config import get_settings

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass

# ---------------------------------------------------------------------------
# Product  (mirrors main-site schema; extend_existing allows column additions)
# ---------------------------------------------------------------------------

class Product(Base):
    __tablename__ = "products"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    image_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    style_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    color_family: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    body_fit: Mapped[str] = mapped_column(String(255), nullable=False)
    style_features: Mapped[list] = mapped_column(JSON, nullable=False)
    function_features: Mapped[list] = mapped_column(JSON, nullable=False)
    size_tags: Mapped[list] = mapped_column(JSON, nullable=False)
    size_notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Annotation extension columns (server_default so main-site SELECTs are unaffected)
    annotation_status: Mapped[str | None] = mapped_column(
        String(20), server_default=text("'unreviewed'"), index=True, nullable=True
    )
    annotation_confidence: Mapped[float | None] = mapped_column(
        Float, server_default=text("0.5"), nullable=True
    )
    last_annotated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_annotated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


# ---------------------------------------------------------------------------
# AdminUser
# ---------------------------------------------------------------------------

class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), server_default=text("'admin'"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# RequestLog
# ---------------------------------------------------------------------------

class RequestLog(Base):
    __tablename__ = "request_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    endpoint: Mapped[str] = mapped_column(String(100), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    user_ip: Mapped[str] = mapped_column(String(50), nullable=False)
    request_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)


# ---------------------------------------------------------------------------
# PageView
# ---------------------------------------------------------------------------

class PageView(Base):
    __tablename__ = "page_views"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # main_site / tryon_workbench
    page: Mapped[str] = mapped_column(String(512), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    user_agent: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    ip: Mapped[str] = mapped_column(String(50), nullable=False, default="")


# ---------------------------------------------------------------------------
# TryonTask
# ---------------------------------------------------------------------------

class TryonTask(Base):
    __tablename__ = "tryon_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    status: Mapped[str] = mapped_column(String(20), server_default=text("'queued'"), index=True)
    user_photo_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)


# ---------------------------------------------------------------------------
# PromptConfig
# ---------------------------------------------------------------------------

class PromptConfig(Base):
    __tablename__ = "prompt_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[list] = mapped_column(JSON, nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, server_default=text("0.2"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_by: Mapped[str] = mapped_column(String(100), nullable=True)


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prompt_config_id: Mapped[int] = mapped_column(Integer, ForeignKey("prompt_configs.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[list | None] = mapped_column(JSON, nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


# ---------------------------------------------------------------------------
# UserProfile
# ---------------------------------------------------------------------------

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    photo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    mbti: Mapped[str | None] = mapped_column(String(10), nullable=True)
    color_preference: Mapped[str] = mapped_column(String(100), nullable=False)
    size_input: Mapped[str | None] = mapped_column(String(20), nullable=True)
    style_input: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_recommended_size: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ai_body_shape: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ai_suggested_style: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    used_fallback: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    recommendation_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))


# ---------------------------------------------------------------------------
# AnnotationTask
# ---------------------------------------------------------------------------

class AnnotationTask(Base):
    __tablename__ = "annotation_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'pending'"), index=True)
    priority: Mapped[int] = mapped_column(Integer, server_default=text("0"), index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    product = relationship("Product", lazy="joined")


# ---------------------------------------------------------------------------
# AnnotationRecord
# ---------------------------------------------------------------------------

class AnnotationRecord(Base):
    __tablename__ = "annotation_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), index=True, nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[str] = mapped_column(Text, nullable=False)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    annotator: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    confidence_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_after: Mapped[float] = mapped_column(Float, server_default=text("1.0"))


# ---------------------------------------------------------------------------
# SampleModel
# ---------------------------------------------------------------------------

class SampleModel(Base):
    __tablename__ = "sample_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    gender: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    image_filename: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    gcs_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, server_default=text("0"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), index=True)
    uploaded_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_height: Mapped[int | None] = mapped_column(Integer, nullable=True)


# ---------------------------------------------------------------------------
# Engine / Session factory
# ---------------------------------------------------------------------------

_engine = None
_SessionLocal = None


def _get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.DATABASE_URL
        connect_args = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=_get_engine(), expire_on_commit=False)
    return _SessionLocal


def get_db():
    """FastAPI dependency that yields a DB session."""
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def init_db():
    """Create tables and seed initial admin user (idempotent)."""
    engine = _get_engine()

    # For PostgreSQL with existing products table, use checkfirst
    Base.metadata.create_all(engine, checkfirst=True)

    settings = get_settings()
    factory = get_session_factory()

    with factory() as session:
        # Idempotent admin creation
        from app.auth import hash_password

        existing = session.query(AdminUser).filter_by(username=settings.ADMIN_INIT_USERNAME).first()
        if not existing:
            admin = AdminUser(
                username=settings.ADMIN_INIT_USERNAME,
                password_hash=hash_password(settings.ADMIN_INIT_PASSWORD),
                role="admin",
            )
            session.add(admin)
            session.commit()

        # Seed default prompt configs if empty
        if session.query(PromptConfig).count() == 0:
            body_prompt = PromptConfig(
                name="body_analysis",
                display_name="体型分析 Prompt",
                content=(
                    "你是服装搭配分析助手。请结合全身照、用户颜色偏好、MBTI 和已知条件，输出一个 JSON 对象。\n"
                    "已知条件:\n"
                    "- 颜色偏好: {color_preference}\n"
                    "- 用户性别: {gender}\n"
                    "- MBTI: {mbti}\n"
                    "- 尺码: {size}\n"
                    "- 款式偏好: {style_preference}\n\n"
                    "返回字段:\n"
                    "- recommended_size: 推荐尺码 (XS/S/M/L/XL/2XL/3XL/4XL/5XL)\n"
                    "- body_shape: 体型描述 (如「标准身材」「偏瘦」「偏壮」等)\n"
                    "- suggested_style: 推荐款式 (如「修身短款」「宽松中长款」等)\n"
                    "- reasoning: 推理说明"
                ),
                variables=["color_preference", "gender", "mbti", "size", "style_preference"],
                model_name="gemini-2.5-flash-lite",
                temperature=0.2,
                updated_by="system",
            )
            tryon_prompt = PromptConfig(
                name="virtual_tryon",
                display_name="虚拟试穿 Prompt",
                content=(
                    "You are a virtual try-on assistant. Given a full-body photo and a clothing item, "
                    "generate a realistic image of the person wearing the clothing.\n\n"
                    "Requirements:\n"
                    "1. Identity preservation: face, body shape, skin tone must remain unchanged\n"
                    "2. Clothing fidelity: color, texture, pattern, details must match the reference\n"
                    "3. Natural fit: clothing should drape naturally on the body\n"
                    "4. Lighting consistency: match the lighting of the original photo\n"
                    "5. No beautification or body modification"
                ),
                variables=[],
                model_name="gemini-2.5-flash",
                temperature=0.1,
                updated_by="system",
            )
            session.add_all([body_prompt, tryon_prompt])
            session.commit()

        # Seed products from database.json if products table is empty
        if session.query(Product).count() == 0:
            _seed_products(session)

        # Seed sample models if empty
        if session.query(SampleModel).count() == 0:
            _seed_sample_models(session)


# Chinese→English key mapping for database.json
_KEY_MAP = {
    "商品标题": "title",
    "价格": "price",
    "图片路径": "image_path",
    "款式类型": "style_type",
    "精准颜色色系": "color_family",
    "版型与身材适配度": "body_fit",
    "风格特征": "style_features",
    "功能属性": "function_features",
}


def _seed_products(session: Session):
    """Load products from database.json into the products table."""
    # Try several possible locations for database.json
    candidates = [
        Path("/app/database.json"),
        Path(__file__).resolve().parent.parent.parent / "database.json",
        Path(__file__).resolve().parent.parent.parent.parent / "database.json",
    ]
    db_json_path = None
    for p in candidates:
        if p.is_file():
            db_json_path = p
            break

    if db_json_path is None:
        print("[init_db] database.json not found, skipping product seed")
        return

    print(f"[init_db] Seeding products from {db_json_path}")
    with open(db_json_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    count = 0
    for item in items:
        mapped = {}
        for cn_key, en_key in _KEY_MAP.items():
            if cn_key in item:
                mapped[en_key] = item[cn_key]

        if "title" not in mapped or "price" not in mapped:
            continue

        # Ensure list fields default to empty list
        mapped.setdefault("style_features", [])
        mapped.setdefault("function_features", [])
        mapped.setdefault("size_tags", [])

        product = Product(**mapped)
        session.add(product)
        count += 1

        # Batch commit every 500 rows
        if count % 500 == 0:
            session.commit()

    session.commit()
    print(f"[init_db] Seeded {count} products")

    # Compute real annotation confidence and create AnnotationTask records
    from app.services.annotation_engine import compute_annotation_confidence, derive_priority

    products = session.query(Product).all()
    task_count = 0
    for p in products:
        conf = compute_annotation_confidence(p)
        p.annotation_confidence = conf
        task = AnnotationTask(product_id=p.id, priority=derive_priority(conf))
        session.add(task)
        task_count += 1
        if task_count % 500 == 0:
            session.commit()
    session.commit()
    print(f"[init_db] Computed confidence and created {task_count} annotation tasks")


_GCS_BUCKET = ""
_SAMPLE_MODELS = [
    {"name": "Donk", "gender": "男", "filename": "Donk.webp", "order": 0},
    {"name": "Monesy", "gender": "男", "filename": "Monesy.webp", "order": 1},
    {"name": "Niko", "gender": "男", "filename": "Niko.webp", "order": 2},
    {"name": "OA-Leave7", "gender": "男", "filename": "OA-Leave7.jpg", "order": 3},
    {"name": "ZywOo", "gender": "男", "filename": "ZywOo.webp", "order": 4},
    {"name": "Liyuu_1", "gender": "女", "filename": "Liyuu_1.jpg", "order": 0},
    {"name": "Liyuu_2", "gender": "女", "filename": "Liyuu_2.jpg", "order": 1},
    {"name": "Liyuu_3", "gender": "女", "filename": "Liyuu_3.jpg", "order": 2},
]


def _seed_sample_models(session: Session):
    """Seed sample model records (images already uploaded to GCS)."""
    print("[init_db] Seeding sample models")
    for m in _SAMPLE_MODELS:
        gcs_url = f"https://storage.googleapis.com/{_GCS_BUCKET}/sample_models/{m['gender']}/{m['filename']}"
        model = SampleModel(
            name=m["name"],
            gender=m["gender"],
            image_filename=m["filename"],
            gcs_url=gcs_url,
            display_order=m["order"],
            uploaded_by="system",
        )
        session.add(model)
    session.commit()
    print(f"[init_db] Seeded {len(_SAMPLE_MODELS)} sample models")
