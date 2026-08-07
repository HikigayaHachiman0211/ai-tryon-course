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
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    prompt_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    default_content: Mapped[str | None] = mapped_column(Text, nullable=True)
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
# AI Config models (Phase 1.5)
# ---------------------------------------------------------------------------

class AIAPIProvider(Base):
    __tablename__ = "ai_api_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'llm'"))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_default: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_type: Mapped[str] = mapped_column(String(30), server_default=text("'api_key_header'"))
    auth_header_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    default_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_options: Mapped[list | None] = mapped_column(JSON, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, server_default=text("30"))
    retry_count: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_quota_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_test_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


class AIFeatureConfig(Base):
    __tablename__ = "ai_feature_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feature_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    default_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    fallback_order: Mapped[list | None] = mapped_column(JSON, nullable=True)
    default_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


class AIAPITestLog(Base):
    __tablename__ = "ai_api_test_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    test_type: Mapped[str] = mapped_column(String(30), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message_sanitized: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


# ---------------------------------------------------------------------------
# VoiceCloneProfile (Phase 2.1A)
# ---------------------------------------------------------------------------

class VoiceCloneProfile(Base):
    __tablename__ = "voice_clone_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    gender: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'female'"))
    language: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'zh'"))
    provider_key: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'mimo_voice_clone'"))
    provider_voice_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_audio_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    sample_audio_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'draft'"))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_published: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    error_message_sanitized: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


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

def _migrate_prompt_configs(engine):
    """Add new columns to prompt_configs if they don't exist (idempotent)."""
    new_columns = [
        ("description", "VARCHAR(500)"),
        ("category", "VARCHAR(50)"),
        ("prompt_type", "VARCHAR(50)"),
        ("default_content", "TEXT"),
    ]
    try:
        with engine.connect() as conn:
            # Get existing columns
            if engine.url.drivername.startswith("sqlite"):
                result = conn.execute(text("PRAGMA table_info(prompt_configs)"))
                existing = {row[1] for row in result}
            else:
                # PostgreSQL
                result = conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'prompt_configs'"
                ))
                existing = {row[0] for row in result}

            for col_name, col_type in new_columns:
                if col_name not in existing:
                    conn.execute(text(f"ALTER TABLE prompt_configs ADD COLUMN {col_name} {col_type}"))
                    print(f"[init_db] Added column prompt_configs.{col_name}")
            conn.commit()
    except Exception as exc:
        # Table might not exist yet (first run) — that's fine
        print(f"[init_db] Prompt config migration skipped: {exc}")


def init_db():
    """Create tables and seed initial admin user (idempotent)."""
    engine = _get_engine()

    # For PostgreSQL with existing products table, use checkfirst
    Base.metadata.create_all(engine, checkfirst=True)

    # Migrate: add new columns to prompt_configs if they don't exist
    _migrate_prompt_configs(engine)

    settings = get_settings()
    factory = get_session_factory()

    with factory() as session:
        # Idempotent admin creation
        from app.auth import hash_password
        from app.config import is_production

        existing = session.query(AdminUser).filter_by(username=settings.ADMIN_INIT_USERNAME).first()
        if not existing:
            if not settings.ADMIN_INIT_PASSWORD:
                print(
                    "[admin-security] ADMIN_INIT_PASSWORD is not configured — "
                    "skipping administrator creation."
                )
            else:
                admin = AdminUser(
                    username=settings.ADMIN_INIT_USERNAME,
                    password_hash=hash_password(settings.ADMIN_INIT_PASSWORD),
                    role="admin",
                )
                session.add(admin)
                session.commit()
        elif not is_production() and settings.ADMIN_INIT_PASSWORD:
            # Local dev only: if the stored hash is stale (e.g. DB left over from a
            # different password), re-sync it so login always works without deleting data.
            from app.auth import verify_password
            if not verify_password(settings.ADMIN_INIT_PASSWORD, existing.password_hash):
                existing.password_hash = hash_password(settings.ADMIN_INIT_PASSWORD)
                session.commit()
                print(f"[admin-dev] Local admin password synced: {settings.ADMIN_INIT_USERNAME}")

        # Seed default prompt configs (skip if name already exists)
        _seed_prompts(session)

        # Seed products from database.json if products table is empty
        if session.query(Product).count() == 0:
            _seed_products(session)

        # Seed sample models if empty
        if session.query(SampleModel).count() == 0:
            _seed_sample_models(session)

        # Seed AI provider and feature configs
        _seed_ai_configs(session)


def _seed_ai_configs(session: Session):
    """Seed default AI provider and feature configurations (idempotent)."""
    from app.services.secret_crypto import encrypt_secret

    providers = [
        {
            "provider_key": "mimo",
            "display_name": "Xiaomi MiMo",
            "category": "multi",
            "enabled": True,
            "is_default": True,
            "base_url": "https://api.xiaomimimo.com/v1",
            "auth_type": "api_key_header",
            "auth_header_name": "api-key",
            "default_model": "mimo-v2.5",
            "model_options": ["mimo-v2.5", "mimo-v2.5-pro", "mimo-v2-omni"],
            "notes": "默认推荐和图像分析 Provider",
        },
        {
            "provider_key": "gemini",
            "display_name": "Google Gemini / AI Studio",
            "category": "multi",
            "enabled": True,
            "is_default": False,
            "base_url": "https://generativelanguage.googleapis.com",
            "auth_type": "query_key",
            "default_model": "gemini-3.1-flash-lite-preview",
            "model_options": [
                "gemini-3.1-flash-lite-preview",
                "gemini-3.1-flash-image-preview",
                "gemini-3-pro-image-preview",
                "gemini-2.5-flash",
            ],
        },
        {
            "provider_key": "deepseek",
            "display_name": "Deepseek",
            "category": "llm",
            "enabled": True,
            "is_default": False,
            "base_url": "https://api.deepseek.com",
            "auth_type": "bearer",
            "auth_header_name": "Authorization",
            "default_model": "deepseek-v4-flash",
            "model_options": ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"],
        },
        {
            "provider_key": "mimo_asr",
            "display_name": "MiMo V2.5 ASR",
            "category": "asr",
            "enabled": False,
            "is_default": False,
            "base_url": "https://api.xiaomimimo.com/v1",
            "auth_type": "api_key_header",
            "auth_header_name": "api-key",
            "default_model": "mimo-v2.5-asr",
            "notes": "第二阶段语音输入使用，本阶段只配置",
        },
        {
            "provider_key": "mimo_tts",
            "display_name": "MiMo V2.5 TTS",
            "category": "tts",
            "enabled": False,
            "is_default": False,
            "base_url": "https://api.xiaomimimo.com/v1",
            "auth_type": "api_key_header",
            "auth_header_name": "api-key",
            "default_model": "mimo-v2.5-tts",
            "notes": "第二阶段语音播报使用，本阶段只配置",
        },
        {
            "provider_key": "mimo_voice_clone",
            "display_name": "MiMo V2.5 TTS VoiceClone",
            "category": "voice_clone",
            "enabled": False,
            "is_default": False,
            "base_url": "https://api.xiaomimimo.com/v1",
            "auth_type": "api_key_header",
            "auth_header_name": "api-key",
            "default_model": "mimo-v2.5-tts-voiceclone",
            "notes": "第二阶段声音克隆使用，本阶段只配置",
        },
    ]

    for pdata in providers:
        existing = session.query(AIAPIProvider).filter_by(provider_key=pdata["provider_key"]).first()
        if not existing:
            session.add(AIAPIProvider(**pdata, updated_by="system"))
    session.commit()

    features = [
        {
            "feature_key": "recommendation",
            "enabled": True,
            "default_provider": "mimo",
            "fallback_order": ["mimo", "gemini", "deepseek", "rule"],
            "default_model": "mimo-v2.5",
        },
        {
            "feature_key": "vision_analysis",
            "enabled": True,
            "default_provider": "mimo",
            "fallback_order": ["mimo", "gemini"],
            "default_model": "mimo-v2.5",
        },
        {
            "feature_key": "assistant_chat",
            "enabled": True,
            "default_provider": "mimo",
            "fallback_order": ["mimo", "deepseek", "rule"],
            "default_model": "mimo-v2.5",
            "config": {"allow_auto_fill": True, "allow_auto_submit": False},
        },
        {
            "feature_key": "tryon",
            "enabled": True,
            "default_provider": "gemini",
            "fallback_order": ["gemini"],
            "default_model": "gemini-3.1-flash-image-preview",
            "config": {
                "flash_model": "gemini-3.1-flash-image-preview",
                "pro_model": "gemini-3-pro-image-preview",
                "allow_request_api_key": False,
                "allow_client_key_management": False,
                "config_cache_seconds": 15,
            },
        },
        {
            "feature_key": "voice_asr",
            "enabled": False,
            "default_provider": "mimo_asr",
            "default_model": "mimo-v2.5-asr",
            "config": {"language": "zh", "max_base64_mb": 10, "allowed_formats": ["wav", "mp3"]},
        },
        {
            "feature_key": "voice_tts",
            "enabled": False,
            "default_provider": "mimo_tts",
            "default_model": "mimo-v2.5-tts",
        },
        {
            "feature_key": "voice_clone",
            "enabled": False,
            "default_provider": "mimo_voice_clone",
            "default_model": "mimo-v2.5-tts-voiceclone",
        },
    ]

    # Migration MUST run before seed insert so old admin config takes priority
    # over system defaults for voice_asr/voice_tts.
    _migrate_voice_feature_keys(session)

    # Migrate existing gemini provider and tryon feature for unified management
    _migrate_tryon_configs(session)

    for fdata in features:
        existing = session.query(AIFeatureConfig).filter_by(feature_key=fdata["feature_key"]).first()
        if not existing:
            session.add(AIFeatureConfig(**fdata, updated_by="system"))
    session.commit()

    print("[init_db] Seeded AI provider and feature configs")


def _migrate_voice_feature_keys(session: Session):
    """Migrate old 'asr'/'tts' feature keys to 'voice_asr'/'voice_tts'.

    Runs BEFORE the seed insert loop so that:
    1. If old 'asr'/'tts' exist but 'voice_asr'/'voice_tts' don't → create from old config.
    2. If old 'asr'/'tts' exist and 'voice_asr'/'voice_tts' were created by a previous
       system seed (updated_by='system') and still have default values → overwrite with old config.
    3. If 'voice_asr'/'voice_tts' were manually edited by an admin (updated_by is a real username,
       not 'system'/'migration') → do NOT overwrite.

    Old keys are preserved (not deleted) to avoid breaking historical data.
    """
    old_to_new = {"asr": "voice_asr", "tts": "voice_tts"}
    for old_key, new_key in old_to_new.items():
        old_cfg = session.query(AIFeatureConfig).filter_by(feature_key=old_key).first()
        if not old_cfg:
            continue

        new_cfg = session.query(AIFeatureConfig).filter_by(feature_key=new_key).first()

        if not new_cfg:
            # Case 1: new key doesn't exist yet → create from old
            new_cfg = AIFeatureConfig(
                feature_key=new_key,
                enabled=old_cfg.enabled,
                default_provider=old_cfg.default_provider,
                fallback_order=old_cfg.fallback_order,
                default_model=old_cfg.default_model,
                config=old_cfg.config,
                updated_by="migration",
            )
            session.add(new_cfg)
        elif new_cfg.updated_by in ("system", None, "migration"):
            # Case 2: new key exists but was only set by system seed or previous migration,
            # and old key has admin-customized values → overwrite with old config.
            # We detect "admin customized" by checking if old config differs from what
            # the system seed would have inserted (i.e., old key was actually changed by admin).
            _apply_old_config_if_admin_customized(old_cfg, new_cfg)

    session.commit()


def _apply_old_config_if_admin_customized(old_cfg: AIFeatureConfig, new_cfg: AIFeatureConfig):
    """Overwrite new_cfg with old_cfg values if old_cfg was admin-customized.

    old_cfg is considered admin-customized if any of its key fields differ from
    the system defaults that would have been inserted for the old key.
    """
    # System defaults for old 'asr' key
    old_defaults = {
        "asr": {
            "enabled": False,
            "default_provider": "mimo_asr",
            "default_model": "mimo-v2.5-asr",
        },
        "tts": {
            "enabled": False,
            "default_provider": "mimo_tts",
            "default_model": "mimo-v2.5-tts",
        },
    }

    old_key = old_cfg.feature_key
    defaults = old_defaults.get(old_key, {})

    # Check if old config was actually customized by admin (differs from defaults)
    was_customized = (
        old_cfg.enabled != defaults.get("enabled", False)
        or old_cfg.default_provider != defaults.get("default_provider", "")
        or old_cfg.default_model != defaults.get("default_model", "")
        or old_cfg.config is not None  # admin set a custom config
    )

    if was_customized:
        new_cfg.enabled = old_cfg.enabled
        new_cfg.default_provider = old_cfg.default_provider
        new_cfg.fallback_order = old_cfg.fallback_order
        new_cfg.default_model = old_cfg.default_model
        new_cfg.config = old_cfg.config
        new_cfg.updated_by = "migration"


def _migrate_tryon_configs(session: Session):
    """Migrate existing gemini provider and tryon feature for unified tryon management.

    - Update gemini provider: display_name, base_url, default_model, model_options
      (only if updated_by is still 'system' or None — don't overwrite admin edits).
    - Update tryon feature: merge new config fields into existing config
      (only if updated_by is still 'system' or None — don't overwrite admin edits).
    """
    # Migrate gemini provider defaults
    gemini = session.query(AIAPIProvider).filter_by(provider_key="gemini").first()
    if gemini and gemini.updated_by in ("system", None):
        gemini.display_name = "Google Gemini / AI Studio"
        gemini.base_url = "https://generativelanguage.googleapis.com"
        # Merge model_options: add new tryon models while preserving existing ones
        existing_opts = list(gemini.model_options or [])
        new_opts = [
            "gemini-3.1-flash-image-preview",
            "gemini-3-pro-image-preview",
            "gemini-3.1-flash-lite-preview",
            "gemini-2.5-flash",
        ]
        merged = list(dict.fromkeys(existing_opts + new_opts))  # dedupe preserving order
        gemini.model_options = merged
        print("[init_db] Migrated gemini provider defaults for tryon")

    # Migrate tryon feature config
    tryon = session.query(AIFeatureConfig).filter_by(feature_key="tryon").first()
    if tryon and tryon.updated_by in ("system", None):
        # Update default model if still old
        if not tryon.default_model or tryon.default_model == "gemini-2.5-flash":
            tryon.default_model = "gemini-3.1-flash-image-preview"
        if not tryon.fallback_order:
            tryon.fallback_order = ["gemini"]
        # Merge new config fields into existing config
        existing_config = dict(tryon.config or {})
        default_tryon_config = {
            "flash_model": "gemini-3.1-flash-image-preview",
            "pro_model": "gemini-3-pro-image-preview",
            "allow_request_api_key": False,
            "allow_client_key_management": False,
            "config_cache_seconds": 15,
        }
        # Only set fields that don't already exist (preserve admin edits)
        for k, v in default_tryon_config.items():
            if k not in existing_config:
                existing_config[k] = v
        tryon.config = existing_config
        print("[init_db] Migrated tryon feature config for unified management")


def _seed_prompts(session: Session):
    """Seed default prompt configs (idempotent backfill).

    - Missing: insert.
    - Exists but default_content empty: backfill default_content.
    - Exists and default_content differs from seed: update default_content only
      (do NOT overwrite admin-edited content).
    """
    prompts = [
        {
            "name": "body_analysis",
            "display_name": "体型分析 Prompt",
            "description": "用于图像分析的体型推断 Prompt",
            "category": "image_analysis",
            "prompt_type": "system",
            "content": (
                "你是服装搭配分析助手。请结合全身照、用户颜色偏好、MBTI 和已知条件，输出一个 JSON 对象。\n"
                "已知条件:\n"
                "- 颜色偏好: {color_preference}\n"
                "- 用户性别: {gender}\n"
                "- MBTI: {mbti}\n"
                "- 尺码: {size}\n"
                "- 款式偏好: {style_preference}\n\n"
                "返回字段:\n"
                "- recommended_size: 推荐尺码 (XS/S/M/L/XL/2XL/3XL/4XL/5XL)\n"
                "- body_shape: 体型描述\n"
                "- suggested_style: 推荐款式\n"
                "- reasoning: 推理说明"
            ),
            "variables": ["color_preference", "gender", "mbti", "size", "style_preference"],
            "model_name": "gemini-2.5-flash-lite",
            "temperature": 0.2,
        },
        {
            "name": "virtual_tryon",
            "display_name": "虚拟试穿 Prompt",
            "description": "虚拟试穿图像生成 Prompt",
            "category": "tryon",
            "prompt_type": "system",
            "content": (
                "You are a virtual try-on assistant. Given a full-body photo and a clothing item, "
                "generate a realistic image of the person wearing the clothing.\n\n"
                "Requirements:\n"
                "1. Identity preservation: face, body shape, skin tone must remain unchanged\n"
                "2. Clothing fidelity: color, texture, pattern, details must match the reference\n"
                "3. Natural fit: clothing should drape naturally on the body\n"
                "4. Lighting consistency: match the lighting of the original photo\n"
                "5. No beautification or body modification"
            ),
            "variables": [],
            "model_name": "gemini-2.5-flash",
            "temperature": 0.1,
        },
        {
            "name": "mimo_image_profile_analysis",
            "display_name": "MiMo 图像分析 Prompt",
            "description": "MiMo 多模态图像分析用于体型推断",
            "category": "image_analysis",
            "prompt_type": "user",
            "content": (
                "请根据照片和以下用户偏好，分析身型特征并推荐羽绒服方案，输出严格 JSON。\n\n"
                "已知条件：\n"
                "- 颜色偏好: {color_preference}\n"
                "- 用户性别: {gender}\n"
                "- MBTI: {mbti}\n"
                "- 用户已提供尺码: {size}\n"
                "- 用户已提供款式偏好: {style_preference}\n\n"
                "返回字段（JSON 格式）：\n"
                '{{\n'
                '  "recommended_size": "XS/S/M/L/XL/2XL/3XL/4XL/5XL/unknown 之一",\n'
                '  "body_shape": "偏瘦/标准/微胖/高壮/H型/梨形/倒三角/沙漏型/O型/未知 之一",\n'
                '  "suggested_style": "常规短外套/短款/轻薄款/绗缝款（排骨款）/面包服/中长款大衣/长款/巴恩风/工装风 之一",\n'
                '  "reasoning": "50字内中文解释"\n'
                '}}\n\n'
                "要求：\n"
                "- 结合照片中的人物身型、穿着风格与已知条件综合分析。\n"
                "- 如果照片或信息不足无法可靠判断，请写 unknown 或 未知。"
            ),
            "variables": ["color_preference", "gender", "mbti", "size", "style_preference"],
            "model_name": "mimo-v2.5",
            "temperature": 0.2,
        },
        {
            "name": "gemini_image_profile_analysis",
            "display_name": "Gemini 图像分析 Prompt",
            "description": "Gemini 多模态图像分析用于体型推断",
            "category": "image_analysis",
            "prompt_type": "user",
            "content": (
                "你是服装搭配分析助手。请结合全身照、用户颜色偏好、MBTI 和已知条件，输出一个 JSON 对象，不要输出 markdown。\n\n"
                "已知条件：\n"
                "- 颜色偏好: {color_preference}\n"
                "- 用户性别: {gender}\n"
                "- MBTI: {mbti}\n"
                "- 用户已提供尺码: {size}\n"
                "- 用户已提供款式偏好: {style_preference}\n\n"
                "返回字段：\n"
                '{{\n'
                '  "recommended_size": "XS/S/M/L/XL/2XL/3XL/4XL/5XL/unknown 之一",\n'
                '  "body_shape": "偏瘦/标准/微胖/高壮/H型/梨形/倒三角/沙漏型/O型/未知 之一",\n'
                '  "suggested_style": "常规短外套/短款/轻薄款/绗缝款（排骨款）/面包服/中长款大衣/长款/巴恩风/工装风 之一",\n'
                '  "reasoning": "50字内中文解释"\n'
                '}}\n\n'
                "要求：\n"
                "- 如果用户已提供尺码或款式偏好，也要结合图像做校验，但仍返回完整 JSON。\n"
                "- 如果无法可靠判断，请写 unknown 或 未知。"
            ),
            "variables": ["color_preference", "gender", "mbti", "size", "style_preference"],
            "model_name": "gemini-3.1-flash-lite-preview",
            "temperature": 0.2,
        },
        {
            "name": "deepseek_text_profile_analysis",
            "display_name": "Deepseek 文本分析 Prompt",
            "description": "Deepseek 文本推断用于体型分析",
            "category": "text_analysis",
            "prompt_type": "user",
            "content": (
                "你是服装搭配分析助手。请根据用户提供的信息，推断体型特征和推荐方案，输出一个 JSON 对象。\n\n"
                "已知条件：\n"
                "- 颜色偏好: {color_preference}\n"
                "- 用户性别: {gender}\n"
                "- MBTI: {mbti}\n"
                "- 用户已提供尺码: {size}\n"
                "- 用户已提供款式偏好: {style_preference}\n\n"
                "返回字段（JSON 格式）：\n"
                '{{\n'
                '  "recommended_size": "XS/S/M/L/XL/2XL/3XL/4XL/5XL/unknown 之一",\n'
                '  "body_shape": "偏瘦/标准/微胖/高壮/H型/梨形/倒三角/沙漏型/O型/未知 之一",\n'
                '  "suggested_style": "常规短外套/短款/轻薄款/绗缝款（排骨款）/面包服/中长款大衣/长款/巴恩风/工装风 之一",\n'
                '  "reasoning": "50字内中文解释"\n'
                '}}\n\n'
                "要求：\n"
                "- 综合所有已知条件进行推断。\n"
                "- 如果信息不足无法可靠判断，请写 unknown 或 未知。"
            ),
            "variables": ["color_preference", "gender", "mbti", "size", "style_preference"],
            "model_name": "deepseek-v4-flash",
            "temperature": 0.2,
        },
        {
            "name": "recommendation_explanation",
            "display_name": "推荐结果解释 Prompt",
            "description": "用于生成推荐结果的自然语言解释",
            "category": "recommendation",
            "prompt_type": "system",
            "content": (
                "你是羽绒服推荐解释助手。根据以下推荐条件和商品信息，用简洁友好的语言解释为什么推荐这件商品。\n\n"
                "推荐条件：\n"
                "- 颜色偏好: {color_preference}\n"
                "- 性别: {gender}\n"
                "- 尺码: {size}\n"
                "- 风格: {style_preference}\n\n"
                "商品信息：\n"
                "- 标题: {product_title}\n"
                "- 颜色: {product_color}\n"
                "- 款式: {product_style}\n"
                "- 品牌: {product_brand}\n\n"
                "要求：50字以内，中文，友好亲切。"
            ),
            "variables": ["color_preference", "gender", "size", "style_preference", "product_title", "product_color", "product_style", "product_brand"],
            "model_name": "mimo-v2.5",
            "temperature": 0.3,
        },
        {
            "name": "assistant_intent_router",
            "display_name": "AI 导购意图路由 Prompt",
            "description": "AI 导购对话意图分类",
            "category": "assistant",
            "prompt_type": "system",
            "content": (
                "你是羽绒服 AI 导购助手的意图分类器。根据用户消息，判断意图类别。\n\n"
                "意图类别：\n"
                "- recommend: 用户想要推荐羽绒服（包含颜色、尺码、品牌、预算等偏好信息）\n"
                "- tryon: 用户想要虚拟试穿\n"
                "- style_lab: 用户想要自己搭配\n"
                "- faq: 用户询问网站功能、使用方法\n"
                "- unknown: 无法判断\n\n"
                "用户消息：{message}\n\n"
                "请只返回意图类别名称，不要返回其他内容。"
            ),
            "variables": ["message"],
            "model_name": "mimo-v2.5",
            "temperature": 0.1,
        },
        {
            "name": "assistant_param_extractor",
            "display_name": "AI 导购参数提取 Prompt",
            "description": "从用户自然语言中提取推荐参数",
            "category": "assistant",
            "prompt_type": "system",
            "content": (
                "你是羽绒服 AI 导购的需求理解与参数提取器。\n\n"
                "用户消息：{message}\n\n"
                "先在内部区分正向需求和排除条件：被“不要、不喜欢、别推荐、排除、避免、不考虑、不接受”等词修饰的值是排除项，绝不能写入 form_patch。"
                "同一句同时出现正向和排除款式时只保留正向款式，例如“像风衣，不要面包服”只能得到“中长款大衣”。"
                "无法由用户原话和下列映射确定的字段必须省略，不得脑补。\n\n"
                "只返回以下 JSON，不要输出其他内容：\n"
                '{{\n'
                '  "intent": "recommend/faq/tryon/style_lab/unknown",\n'
                '  "reply": "30字以内的中文确认回复",\n'
                '  "form_patch": {{\n'
                '    "gender": "male/female 或省略",\n'
                '    "color_preference": "标准颜色或省略",\n'
                '    "brand_preference": "具体品牌列表或省略",\n'
                '    "size": "XS/S/M/L/XL/2XL/3XL/4XL/5XL/6XL/7XL 或省略",\n'
                '    "price_min": 数字或省略,\n'
                '    "price_max": 数字或省略,\n'
                '    "style_preference": "一个标准款式或省略",\n'
                '    "mbti": "标准MBTI或省略"\n'
                '  }},\n'
                '  "confidence": 0.0\n'
                '}}\n\n'
                "严格字段规则：\n"
                "- 只能输出 form_patch 已列字段，不得新增 excluded_style、negative_style、notes。\n"
                "- gender 只能是 male/female；MBTI 只能是标准16型；尺码只能是 XS 到 7XL 的现有格式。\n"
                "- 标准颜色：黑色、白色、米白、灰色、蓝色、雾蓝、藏青、绿色、豆绿、橄榄、红色、棕色、卡其色、米色、橘色、粉色。\n"
                "- brand_preference 必须是商品数据库里存在的具体品牌或品牌候选，不能输出 大品牌、品牌大点、有保障、品质保障、知名品牌 这类泛化词。\n"
                "- 可选品牌：波司登、李宁、安踏、骆驼、阿迪达斯、耐克、优衣库、太平鸟、雪中飞、雅鹿、鸭鸭、鸿星尔克、361°、北面、始祖鸟、哥伦比亚、Under Armour、安德玛、罗蒙、南极人、乔丹、FILA、匹克、海澜之家。\n"
                "- 当用户只说“大品牌/品牌大点/有保障/品质保障/知名品牌”时，要结合预算和风格推断具体候选品牌。预算 350 以内优先：罗蒙、雅鹿、鸭鸭、雪中飞、南极人、骆驼、李宁、安踏；预算更高可考虑：波司登、阿迪达斯、耐克、FILA、优衣库、李宁、安踏、骆驼。\n"
                "- style_preference 只能是数据库款式之一：常规短外套、短款、轻薄款、绗缝款（排骨款）、面包服、中长款大衣、长款、巴恩风/工装风、派克大衣、马甲；一次只输出一个正向款式。\n"
                "- 映射：风衣/大衣感/西服领 → 中长款大衣；工装/巴恩/多口袋/山系 → 巴恩风/工装风；绗缝/排骨/内胆 → 绗缝款（排骨款）；泡芙/蓬松 → 面包服；轻便/轻量 → 轻薄款；通勤/极简/简约/百搭/基础 → 常规短外套；派克 → 派克大衣；背心 → 马甲。\n"
                "- “帅、好看、高级、不土、洋气”等审美词不能单独映射为款式。“不要面包服”“不喜欢泡芙感”“别推荐蓬松款”都禁止输出面包服。\n"
                "- “不要黑色，想要白色”只能输出白色；不要把排除颜色当偏好。\n"
                "- 中文价格要转数字：三百块以内/300以内 → price_max: 300；五百到八百 → price_min: 500, price_max: 800。\n"
                "- 身高体重要联合判断尺码，不要只看身高；180cm 且 80kg/微胖 → size 至少 2XL；180cm 且 90kg以上 → 至少 3XL。\n"
                "- 大码 → size: 2XL, 加大码 → size: 3XL\n"
                "- XXL → 2XL, XXXL → 3XL\n"
                "- 男学生/男生/男士 → male\n"
                "- 女学生/女生/女士 → female\n"
                "- 不要默认填写 ai_provider、vision_provider 或模型字段，使用后台配置。"
            ),
            "variables": ["message"],
            "model_name": "mimo-v2.5",
            "temperature": 0.1,
        },
        {
            "name": "assistant_faq_answer",
            "display_name": "AI 客服 FAQ 回答 Prompt",
            "description": "AI 客服常见问题回答",
            "category": "assistant",
            "prompt_type": "system",
            "content": (
                "你是羽绒服推荐平台的客服助手。请根据以下 FAQ 信息回答用户问题。\n\n"
                "常见问题：\n"
                "1. 如何使用推荐功能？→ 上传全身照，填写颜色、性别等偏好，点击「开始生成 AI 推荐」\n"
                "2. 如何虚拟试穿？→ 在推荐结果中选择商品，点击「尝试这件衣服」\n"
                "3. 如何自己搭配？→ 点击导航栏「自己搭配」进入 Style Lab\n"
                "4. 照片安全吗？→ 照片仅用于分析，不会保存或分享\n"
                "5. 推荐不准怎么办？→ 可以调整偏好参数重新推荐\n\n"
                "用户问题：{question}\n\n"
                "请用简洁友好的中文回答。"
            ),
            "variables": ["question"],
            "model_name": "mimo-v2.5",
            "temperature": 0.3,
        },
        {
            "name": "assistant_recommend_summary",
            "display_name": "AI 导购推荐摘要 Prompt",
            "description": "AI 导购生成推荐条件摘要",
            "category": "assistant",
            "prompt_type": "system",
            "content": (
                "你是羽绒服 AI 导购助手。根据提取到的推荐条件，生成一段友好的确认摘要。\n\n"
                "提取到的条件：\n"
                "- 性别: {gender}\n"
                "- 颜色: {color}\n"
                "- 品牌: {brand}\n"
                "- 尺码: {size}\n"
                "- 价格区间: {price_range}\n"
                "- 风格: {style}\n"
                "- MBTI: {mbti}\n\n"
                "要求：30字以内，中文，友好亲切，引导用户确认。"
            ),
            "variables": ["gender", "color", "brand", "size", "price_range", "style", "mbti"],
            "model_name": "mimo-v2.5",
            "temperature": 0.3,
        },
        {
            "name": "assistant_tryon_guide",
            "display_name": "试穿引导 Prompt",
            "description": "AI 导购引导用户进行虚拟试穿",
            "category": "assistant",
            "prompt_type": "system",
            "content": "要进行虚拟试穿，请先在推荐结果或「自己搭配」页面选择一件羽绒服，然后点击「尝试试穿」按钮。系统会自动打开试穿工作台并同步商品图，你只需在试穿站上传全身照即可。",
            "variables": [],
            "model_name": "mimo-v2.5",
            "temperature": 0.1,
        },
        {
            "name": "assistant_style_lab_guide",
            "display_name": "搭配引导 Prompt",
            "description": "AI 导购引导用户使用 Style Lab",
            "category": "assistant",
            "prompt_type": "system",
            "content": "你可以在页面顶部导航栏点击「自己搭配」进入 Style Lab。在那里你可以从商品库中挑选任意羽绒服，系统会对该单品与你的偏好进行多维评分和穿搭建议。",
            "variables": [],
            "model_name": "mimo-v2.5",
            "temperature": 0.1,
        },
        {
            "name": "assistant_asr_postprocess",
            "display_name": "ASR 后处理 Prompt",
            "description": "语音识别文本后处理：去噪、纠错、规范化",
            "category": "voice",
            "prompt_type": "system",
            "content": "你是一个语音识别后处理助手。请清理以下 ASR 识别文本：1. 去除多余空格和重复词。2. 修正明显的同音错别字（如「羽绒福」->「羽绒服」）。3. 统一中文标点。4. 不改变用户原意，不过度改写。5. 保留口语化表达。",
            "variables": [],
            "model_name": "mimo-v2.5",
            "temperature": 0.1,
        },
        {
            "name": "assistant_tts_style_prompt",
            "display_name": "TTS 风格 Prompt",
            "description": "语音合成播报风格：温和、清晰、自然的导购助手",
            "category": "voice",
            "prompt_type": "system",
            "content": "像一个亲切的羽绒服导购助手在和用户说话。语气温和自然，语速适中，不过度夸张。像在帮朋友挑选适合的冬季外套，耐心、专业、温暖。",
            "variables": [],
            "model_name": "mimo-v2.5",
            "temperature": 0.1,
        },
        {
            "name": "voice_clone_consent_prompt",
            "display_name": "声音克隆授权 Prompt",
            "description": "声音克隆用户授权确认：强调后台授权，不允许普通用户上传",
            "category": "voice",
            "prompt_type": "system",
            "content": "声音克隆功能仅限后台管理员操作。普通主站用户不可上传声音样本进行克隆。所有克隆音色必须经过后台审核和发布后才能在主站使用。如需使用克隆音色，请联系管理员。",
            "variables": [],
            "model_name": "mimo-v2.5",
            "temperature": 0.1,
        },
        {
            "name": "assistant_call_opening_prompt",
            "display_name": "电话导购开场白",
            "description": "AI 电话导购模式开场语音",
            "category": "voice_call",
            "prompt_type": "system",
            "content": "你好，我是你的 AI 羽绒服导购助手。你可以直接告诉我你的需求，比如性别、颜色偏好、预算、尺码和喜欢的风格，我会帮你找到最合适的羽绒服。",
            "variables": [],
            "model_name": "mimo-v2.5",
            "temperature": 0.1,
        },
        {
            "name": "assistant_call_repair_prompt",
            "display_name": "电话导购修复话术",
            "description": "ASR 识别失败或用户表达不清时的引导话术",
            "category": "voice_call",
            "prompt_type": "system",
            "content": "抱歉，我没有听清楚。你可以再说一次吗？或者你可以告诉我：1. 你想要什么颜色？2. 大概预算多少？3. 男款还是女款？4. 什么尺码？",
            "variables": [],
            "model_name": "mimo-v2.5",
            "temperature": 0.1,
        },
        {
            "name": "assistant_call_summary_prompt",
            "display_name": "电话导购通话摘要",
            "description": "通话结束时的推荐条件摘要和下一步动作",
            "category": "voice_call",
            "prompt_type": "system",
            "content": "根据通话内容，整理用户的核心需求：性别、颜色、预算、尺码、品牌、风格。总结后告知用户已整理好推荐条件，建议用户确认后生成推荐。",
            "variables": [],
            "model_name": "mimo-v2.5",
            "temperature": 0.1,
        },
    ]

    for pdata in prompts:
        existing = session.query(PromptConfig).filter_by(name=pdata["name"]).first()
        if not existing:
            session.add(PromptConfig(**pdata, default_content=pdata["content"], updated_by="system"))
        else:
            # Backfill: update default_content if empty or if seed content changed
            # Do NOT overwrite admin-edited content
            if not existing.default_content:
                existing.default_content = pdata["content"]
            elif existing.default_content != pdata["content"]:
                # Seed content changed (e.g. 2.1A update) — update default only
                existing.default_content = pdata["content"]
            if (
                pdata["name"] == "assistant_param_extractor"
                and existing.updated_by in ("system", None, "migration")
                and existing.content != pdata["content"]
            ):
                # Upgrade stale system seed while preserving administrator edits.
                existing.content = pdata["content"]
                existing.version = int(existing.version or 1) + 1
                existing.updated_by = "system"
    session.commit()
    print(f"[init_db] Seeded/backfilled {len(prompts)} prompt configs")


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


_SAMPLE_MODELS = [
    {"name": "通用男模 1", "gender": "男", "filename": "mannequin-male-1.png", "order": 0},
    {"name": "通用男模 2", "gender": "男", "filename": "mannequin-male-2.png", "order": 1},
    {"name": "通用女模 1", "gender": "女", "filename": "mannequin-female-1.png", "order": 0},
    {"name": "通用女模 2", "gender": "女", "filename": "mannequin-female-2.png", "order": 1},
]


def _seed_sample_models(session: Session):
    """Seed sample model records (images already uploaded to GCS)."""
    bucket_name = get_settings().GCS_BUCKET_NAME
    if not bucket_name:
        print("[init_db] GCS_BUCKET_NAME is not configured; skipping sample model seed")
        return
    print("[init_db] Seeding generic sample models")
    for m in _SAMPLE_MODELS:
        gcs_url = f"https://storage.googleapis.com/{bucket_name}/sample_models/{m['gender']}/{m['filename']}"
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
