"""Realtime try-on configuration, health testing, and billing ledger APIs (Decart, Xmax X2.1, & Reactor)."""
from __future__ import annotations

import json
import math
import secrets
import time
from collections import defaultdict
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Literal
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.config import get_settings, is_production
from app.database import (
    AIAPIProvider,
    AIAPITestLog,
    AIFeatureConfig,
    AdminUser,
    WorkbenchRealtimeSession,
    get_db,
)
from app.services.secret_crypto import decrypt_secret, encrypt_secret, sanitize_error_message

MODEL = "lucy-vton-3.6"
MIN_SECONDS = 10
DECART_BASE_URL = "https://api.decart.ai"
DECART_DEFAULT_PROMPT = (
    "Replace the person's outfit with the garment shown in the reference image, "
    "keeping natural body motion, lighting, and face identity."
)

XMAX_DEFAULT_URLS: dict[str, str] = {
    "global": "https://api.xmax.ai/open/api/v1",
    "china": "https://cloud.xmax.22duck.cn/open/api/v1",
}
XMAX_MODELS: tuple[str, ...] = ("x2.1", "x2.1-flash")
XMAX_CAMERA_PRESETS: dict[str, tuple[str, ...]] = {
    "x2.1": ("1080x1920", "1920x1080", "1152x1536", "1536x1152", "1408x1408"),
    "x2.1-flash": ("704x1280", "1280x704", "768x1024", "1024x768", "960x960"),
}
XMAX_DEFAULT_PROMPT = "将参考图的服装穿戴到视频角色身上，跟随角色原有动作。"

REACTOR_PROVIDER_KEY = "reactor"
REACTOR_FEATURE_KEY = "tryon_realtime_reactor"
REACTOR_DEFAULT_BASE_URL = "https://api.reactor.inc"
REACTOR_DEFAULT_MODEL = "reactor/xmax-x2-1"
REACTOR_MODELS: tuple[str, ...] = ("reactor/xmax-x2-1", "xmax/x2")
REACTOR_MODEL_ALIASES: dict[str, str] = {
    "reactor/xmax-x2-1": "reactor/xmax-x2-1",
    "xmax-x2-1": "reactor/xmax-x2-1",
    "x2.1": "reactor/xmax-x2-1",
    "x21": "reactor/xmax-x2-1",
    "xmax/x2": "xmax/x2",
    "x2": "xmax/x2",
    "x2.0": "xmax/x2",
    "x20": "xmax/x2",
}
REACTOR_DEFAULT_CREDITS_PER_SECOND = 17
REACTOR_DEFAULT_CENTS_PER_MINUTE = 11
REACTOR_DEFAULT_PROMPT = "将参考图的服装穿戴到视频角色身上，保持人物面部、姿态和自然光影，服装贴合身体动作。"

BUDGET_ZONE = ZoneInfo("Asia/Hong_Kong")

config_router = APIRouter(prefix="/api/ai-config/realtime", tags=["ai-realtime-config"])
admin_router = APIRouter(prefix="/api/admin/realtime-tryon", tags=["realtime-tryon-admin"])


class RealtimeConfigUpdate(BaseModel):
    enabled: bool | None = None
    api_key: str | None = Field(default=None, max_length=1024)
    clear_api_key: bool = False
    require_access_code: bool | None = None
    access_code: str | None = Field(default=None, max_length=256)
    clear_access_code: bool = False
    origin: str | None = Field(default=None, max_length=512)
    max_seconds: int | None = Field(default=None, ge=10, le=60)
    default_seconds: int | None = Field(default=None, ge=10, le=60)
    cents_per_second: int | None = Field(default=None, ge=2, le=1000)
    daily_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    monthly_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    visitor_daily_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    max_active: int | None = Field(default=None, ge=1, le=5)
    starts_per_minute: int | None = Field(default=None, ge=1, le=30)
    default_prompt: str | None = Field(default=None, max_length=280)


class XmaxRealtimeConfigUpdate(BaseModel):
    enabled: bool | None = None
    api_key: str | None = Field(default=None, max_length=1024)
    clear_api_key: bool = False
    environment: Literal["global", "china"] | None = None
    base_url: str | None = Field(default=None, max_length=512)
    default_model: Literal["x2.1", "x2.1-flash"] | None = None
    allowed_models: list[Literal["x2.1", "x2.1-flash"]] | None = None
    camera_preset: str | None = Field(default=None, max_length=32)
    face_restoration: bool | None = None
    require_access_code: bool | None = None
    access_code: str | None = Field(default=None, max_length=256)
    clear_access_code: bool = False
    origin: str | None = Field(default=None, max_length=512)
    min_seconds: int | None = Field(default=None, ge=10, le=60)
    max_seconds: int | None = Field(default=None, ge=10, le=120)
    default_seconds: int | None = Field(default=None, ge=10, le=120)
    credits_per_second: int | None = Field(default=None, ge=1, le=100)
    cents_per_minute: int | None = Field(default=None, ge=1, le=10_000)
    daily_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    monthly_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    visitor_daily_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    min_account_credits: int | None = Field(default=None, ge=0, le=10_000_000)
    max_active: int | None = Field(default=None, ge=1, le=5)
    starts_per_minute: int | None = Field(default=None, ge=1, le=30)
    default_prompt: str | None = Field(default=None, max_length=280)


class ReactorRealtimeConfigUpdate(BaseModel):
    enabled: bool | None = None
    api_key: str | None = Field(default=None, max_length=1024)
    clear_api_key: bool = False
    base_url: str | None = Field(default=None, max_length=512)
    default_model: str | None = Field(default=None, max_length=64)
    allowed_models: list[str] | None = None
    require_access_code: bool | None = None
    access_code: str | None = Field(default=None, max_length=256)
    clear_access_code: bool = False
    origin: str | None = Field(default=None, max_length=512)
    min_seconds: int | None = Field(default=None, ge=10, le=60)
    max_seconds: int | None = Field(default=None, ge=10, le=120)
    default_seconds: int | None = Field(default=None, ge=10, le=120)
    credits_per_second: int | None = Field(default=None, ge=1, le=10000)
    cents_per_minute: int | None = Field(default=None, ge=1, le=10_000)
    daily_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    monthly_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    visitor_daily_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    min_account_credits: int | None = Field(default=None, ge=0, le=10_000_000)
    max_active: int | None = Field(default=None, ge=1, le=5)
    starts_per_minute: int | None = Field(default=None, ge=1, le=30)
    default_prompt: str | None = Field(default=None, max_length=280)


class FetchOfficialRequest(BaseModel):
    base_url: str | None = Field(default=None, max_length=300)
    environment: str | None = None
    api_key: str | None = Field(default=None, max_length=512)


class ReconcileRequest(BaseModel):
    confirmed_seconds: float | None = Field(default=None, ge=0, le=3600)
    confirmed_credits: float | None = Field(default=None, ge=0, le=360000)
    provider_session_id: str | None = Field(default=None, max_length=128)


def _clamp_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _bool_value(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_origin(raw: str | None) -> str:
    value = str(raw or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise HTTPException(400, "Origin 必须是干净的 http(s)://域名[:端口]（不能包含路径或参数）")
    return value


def _normalize_xmax_base_url(raw: str | None, environment: str) -> str:
    value = str(raw or "").strip().rstrip("/")
    if not value:
        return XMAX_DEFAULT_URLS.get(environment, XMAX_DEFAULT_URLS["global"])
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(400, "Xmax Base URL 必须是合法的 http(s) 地址")
    return value


def _normalize_reactor_model(raw: str | None, *, default: str = REACTOR_DEFAULT_MODEL) -> str:
    candidate = str(raw or "").strip().lower()
    if candidate in REACTOR_MODEL_ALIASES:
        return REACTOR_MODEL_ALIASES[candidate]
    fallback = str(default or REACTOR_DEFAULT_MODEL).strip().lower()
    return REACTOR_MODEL_ALIASES.get(fallback, REACTOR_DEFAULT_MODEL)


def _normalize_reactor_base_url(raw: str | None) -> str:
    value = str(raw or "").strip().rstrip("/")
    if not value:
        return REACTOR_DEFAULT_BASE_URL
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(400, "Reactor Base URL 必须是合法的 http(s) 地址")
    return value


def _derive_effective_origin(configured_origin: str) -> str:
    if configured_origin:
        return configured_origin
    workbench_url = str(get_settings().TRYON_WORKBENCH_URL or "").strip()
    if not workbench_url:
        return ""
    parsed = urlsplit(workbench_url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return ""


def _parse_feature_config(feature: AIFeatureConfig | None) -> dict:
    raw = (feature.config if feature else None) or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    return dict(raw) if isinstance(raw, dict) else {}


def _rows(db: Session) -> tuple[AIAPIProvider | None, AIFeatureConfig | None]:
    return (
        db.query(AIAPIProvider).filter_by(provider_key="decart").first(),
        db.query(AIFeatureConfig).filter_by(feature_key="tryon_realtime").first(),
    )


def _xmax_rows(db: Session) -> tuple[AIAPIProvider | None, AIFeatureConfig | None]:
    return (
        db.query(AIAPIProvider).filter_by(provider_key="xmax").first(),
        db.query(AIFeatureConfig).filter_by(feature_key="tryon_realtime_xmax").first(),
    )


def _reactor_rows(db: Session) -> tuple[AIAPIProvider | None, AIFeatureConfig | None]:
    return (
        db.query(AIAPIProvider).filter_by(provider_key=REACTOR_PROVIDER_KEY).first(),
        db.query(AIFeatureConfig).filter_by(feature_key=REACTOR_FEATURE_KEY).first(),
    )


def _ensure_rows(db: Session) -> tuple[AIAPIProvider, AIFeatureConfig]:
    provider, feature = _rows(db)
    if provider is None:
        provider = AIAPIProvider(
            provider_key="decart",
            display_name="Decart Lucy VTON",
            category="realtime",
            enabled=False,
            is_default=False,
            base_url=DECART_BASE_URL,
            auth_type="api_key_header",
            auth_header_name="X-API-KEY",
            default_model=MODEL,
            model_options=[MODEL],
            timeout_seconds=15,
            retry_count=0,
            cost_note="Lucy VTON 3.6 720p $0.02/s",
        )
        db.add(provider)
    if feature is None:
        feature = AIFeatureConfig(
            feature_key="tryon_realtime",
            enabled=False,
            default_provider="decart",
            fallback_order=["decart"],
            default_model=MODEL,
            config={},
        )
        db.add(feature)
    return provider, feature


def _ensure_xmax_rows(db: Session) -> tuple[AIAPIProvider, AIFeatureConfig]:
    provider, feature = _xmax_rows(db)
    if provider is None:
        provider = AIAPIProvider(
            provider_key="xmax",
            display_name="Xmax X2.1 Realtime",
            category="realtime",
            enabled=False,
            is_default=False,
            base_url=XMAX_DEFAULT_URLS["global"],
            auth_type="api_key_header",
            auth_header_name="X-Api-Key",
            default_model="x2.1",
            model_options=list(XMAX_MODELS),
            timeout_seconds=15,
            retry_count=0,
            cost_note="Xmax X2.1 1080p 1 credit/s (~$0.10/min, $6/h)",
        )
        db.add(provider)
    if feature is None:
        feature = AIFeatureConfig(
            feature_key="tryon_realtime_xmax",
            enabled=False,
            default_provider="xmax",
            fallback_order=["xmax"],
            default_model="x2.1",
            config={
                "environment": "global",
                "allowed_models": list(XMAX_MODELS),
                "camera_preset": "1080x1920",
                "face_restoration": True,
                "require_access_code": True,
                "origin": "",
                "min_seconds": 10,
                "max_seconds": 60,
                "default_seconds": 30,
                "credits_per_second": 1,
                "cents_per_minute": 10,
                "daily_cents": 200,
                "monthly_cents": 1000,
                "visitor_daily_cents": 50,
                "min_account_credits": 60,
                "max_active": 1,
                "starts_per_minute": 3,
                "default_prompt": XMAX_DEFAULT_PROMPT,
            },
        )
        db.add(feature)
    return provider, feature


def _ensure_reactor_rows(db: Session) -> tuple[AIAPIProvider, AIFeatureConfig]:
    provider, feature = _reactor_rows(db)
    if provider is None:
        provider = AIAPIProvider(
            provider_key=REACTOR_PROVIDER_KEY,
            display_name="Reactor Xmax Relay (X2.1 / X2.0)",
            category="realtime",
            enabled=False,
            is_default=False,
            base_url=REACTOR_DEFAULT_BASE_URL,
            auth_type="bearer",
            auth_header_name="Authorization",
            default_model=REACTOR_DEFAULT_MODEL,
            model_options=list(REACTOR_MODELS),
            timeout_seconds=15,
            retry_count=0,
            cost_note="Reactor Xmax X2.1 / X2.0 (17 credits/s, $0.0017/s, ~$0.102/min)",
        )
        db.add(provider)
    if feature is None:
        feature = AIFeatureConfig(
            feature_key=REACTOR_FEATURE_KEY,
            enabled=False,
            default_provider=REACTOR_PROVIDER_KEY,
            fallback_order=[REACTOR_PROVIDER_KEY],
            default_model=REACTOR_DEFAULT_MODEL,
            config={
                "allowed_models": list(REACTOR_MODELS),
                "require_access_code": True,
                "origin": "",
                "min_seconds": 10,
                "max_seconds": 60,
                "default_seconds": 30,
                "credits_per_second": REACTOR_DEFAULT_CREDITS_PER_SECOND,
                "cents_per_minute": REACTOR_DEFAULT_CENTS_PER_MINUTE,
                "daily_cents": 200,
                "monthly_cents": 1000,
                "visitor_daily_cents": 50,
                "min_account_credits": 1000,
                "max_active": 1,
                "starts_per_minute": 3,
                "default_prompt": REACTOR_DEFAULT_PROMPT,
            },
        )
        db.add(feature)
    return provider, feature


def _access_code_meta(cfg: dict) -> tuple[bool, bool, bool, int]:
    require_access_code = _bool_value(cfg.get("require_access_code"), True)
    enc_code = str(cfg.get("access_code_encrypted") or "")
    has_access_code = bool(enc_code)
    access_code_decrypt_ok = False
    access_code_length = int(cfg.get("access_code_length") or 0)
    if has_access_code:
        try:
            plain_code = decrypt_secret(enc_code).strip()
            access_code_decrypt_ok = 16 <= len(plain_code) <= 256
            if plain_code:
                access_code_length = len(plain_code)
        except Exception:
            access_code_decrypt_ok = False
    return require_access_code, has_access_code, access_code_decrypt_ok, access_code_length


def _credential_meta(
    provider: AIAPIProvider | None,
    feature: AIFeatureConfig | None,
    cfg: dict,
    effective_origin: str,
) -> dict:
    enabled = bool(provider and provider.enabled and feature and feature.enabled)
    has_api_key = bool(provider and provider.api_key_encrypted)
    key_decrypt_ok = False
    if has_api_key and provider and provider.api_key_encrypted:
        try:
            key_decrypt_ok = bool(decrypt_secret(provider.api_key_encrypted).strip())
        except Exception:
            key_decrypt_ok = False
    require_access_code, has_access_code, access_code_decrypt_ok, access_code_length = _access_code_meta(cfg)

    blocking_reasons: list[str] = []
    if not enabled:
        blocking_reasons.append("feature_disabled")
    if not has_api_key:
        blocking_reasons.append("missing_api_key")
    elif not key_decrypt_ok:
        blocking_reasons.append("key_decrypt_failed")
    if require_access_code:
        if not has_access_code or access_code_length < 16:
            blocking_reasons.append("missing_access_code")
        elif not access_code_decrypt_ok:
            blocking_reasons.append("access_code_decrypt_failed")
    if is_production() and not effective_origin.startswith("https://"):
        blocking_reasons.append("origin_not_https")

    return {
        "enabled": enabled,
        "has_api_key": has_api_key,
        "key_decrypt_ok": key_decrypt_ok,
        "require_access_code": require_access_code,
        "has_access_code": has_access_code,
        "access_code_decrypt_ok": access_code_decrypt_ok,
        "access_code_length": access_code_length,
        "blocking_reasons": blocking_reasons,
        "ready_to_serve": enabled and not blocking_reasons,
        "last_test_status": provider.last_test_status if provider else None,
        "last_test_message": provider.last_test_message if provider else None,
        "last_test_at": provider.last_test_at.isoformat() if provider and provider.last_test_at else None,
        "updated_at": feature.updated_at.isoformat() if feature and feature.updated_at else None,
        "updated_by": feature.updated_by if feature else None,
    }


def _resolve_prompt_default(cfg: dict, fallback: str) -> str:
    if "default_prompt" in cfg and cfg.get("default_prompt") is not None:
        return str(cfg.get("default_prompt") or "")[:280]
    return fallback[:280]


def _serialize_config(provider: AIAPIProvider | None, feature: AIFeatureConfig | None) -> dict:
    cfg = _parse_feature_config(feature)
    configured_origin = str(cfg.get("origin") or "").strip().rstrip("/")
    effective_origin = _derive_effective_origin(configured_origin)
    max_seconds = _clamp_int(cfg.get("max_seconds"), 20, MIN_SECONDS, 60)
    default_seconds = _clamp_int(cfg.get("default_seconds"), min(15, max_seconds), MIN_SECONDS, max_seconds)
    meta = _credential_meta(provider, feature, cfg, effective_origin)

    return {
        "provider_key": "decart",
        **meta,
        "model": MODEL,
        "base_url": (provider.base_url if provider else None) or DECART_BASE_URL,
        "origin": configured_origin,
        "effective_origin": effective_origin,
        "max_seconds": max_seconds,
        "default_seconds": default_seconds,
        "cents_per_second": _clamp_int(cfg.get("cents_per_second"), 2, 2, 1000),
        "daily_cents": _clamp_int(cfg.get("daily_cents"), 200, 0, 10_000_000),
        "monthly_cents": _clamp_int(cfg.get("monthly_cents"), 1000, 0, 10_000_000),
        "visitor_daily_cents": _clamp_int(cfg.get("visitor_daily_cents"), 80, 0, 10_000_000),
        "max_active": _clamp_int(cfg.get("max_active"), 1, 1, 5),
        "starts_per_minute": _clamp_int(cfg.get("starts_per_minute"), 3, 1, 30),
        "default_prompt": _resolve_prompt_default(cfg, DECART_DEFAULT_PROMPT),
    }


def _normalize_xmax_camera_preset(model: str, raw_preset: str | None) -> str:
    allowed = XMAX_CAMERA_PRESETS.get(model, XMAX_CAMERA_PRESETS["x2.1"])
    clean = str(raw_preset or "").strip()
    return clean if clean in allowed else allowed[0]


def _serialize_xmax_config(provider: AIAPIProvider | None, feature: AIFeatureConfig | None) -> dict:
    cfg = _parse_feature_config(feature)
    environment = "china" if str(cfg.get("environment") or "").strip().lower() == "china" else "global"
    default_model_raw = str((feature.default_model if feature else None) or (provider.default_model if provider else None) or "x2.1")
    default_model = default_model_raw if default_model_raw in XMAX_MODELS else "x2.1"

    raw_allowed = cfg.get("allowed_models")
    allowed_models: list[str] = []
    if isinstance(raw_allowed, list):
        for item in raw_allowed:
            clean = str(item or "").strip().lower()
            if clean in XMAX_MODELS and clean not in allowed_models:
                allowed_models.append(clean)
    if default_model not in allowed_models:
        allowed_models.insert(0, default_model)

    camera_preset = _normalize_xmax_camera_preset(default_model, str(cfg.get("camera_preset") or ""))
    configured_origin = str(cfg.get("origin") or "").strip().rstrip("/")
    effective_origin = _derive_effective_origin(configured_origin)

    min_seconds = _clamp_int(cfg.get("min_seconds"), 10, 10, 60)
    max_seconds = _clamp_int(cfg.get("max_seconds"), 60, min_seconds, 120)
    default_seconds = _clamp_int(cfg.get("default_seconds"), min(30, max_seconds), min_seconds, max_seconds)
    meta = _credential_meta(provider, feature, cfg, effective_origin)

    return {
        "provider_key": "xmax",
        **meta,
        "environment": environment,
        "base_url": (provider.base_url if provider else None) or XMAX_DEFAULT_URLS[environment],
        "default_model": default_model,
        "allowed_models": allowed_models,
        "camera_preset": camera_preset,
        "face_restoration": _bool_value(cfg.get("face_restoration"), True),
        "origin": configured_origin,
        "effective_origin": effective_origin,
        "min_seconds": min_seconds,
        "max_seconds": max_seconds,
        "default_seconds": default_seconds,
        "credits_per_second": _clamp_int(cfg.get("credits_per_second"), 1, 1, 100),
        "cents_per_minute": _clamp_int(cfg.get("cents_per_minute"), 10, 1, 10_000),
        "daily_cents": _clamp_int(cfg.get("daily_cents"), 200, 0, 10_000_000),
        "monthly_cents": _clamp_int(cfg.get("monthly_cents"), 1000, 0, 10_000_000),
        "visitor_daily_cents": _clamp_int(cfg.get("visitor_daily_cents"), 50, 0, 10_000_000),
        "min_account_credits": _clamp_int(cfg.get("min_account_credits"), 60, 0, 10_000_000),
        "max_active": _clamp_int(cfg.get("max_active"), 1, 1, 5),
        "starts_per_minute": _clamp_int(cfg.get("starts_per_minute"), 3, 1, 30),
        "default_prompt": _resolve_prompt_default(cfg, XMAX_DEFAULT_PROMPT),
    }


def _serialize_reactor_config(provider: AIAPIProvider | None, feature: AIFeatureConfig | None) -> dict:
    cfg = _parse_feature_config(feature)
    default_model = _normalize_reactor_model(
        str((feature.default_model if feature else None) or (provider.default_model if provider else None) or REACTOR_DEFAULT_MODEL)
    )
    raw_allowed = cfg.get("allowed_models")
    allowed_models: list[str] = []
    if isinstance(raw_allowed, list):
        for item in raw_allowed:
            raw_text = str(item or "").strip().lower()
            if raw_text in REACTOR_MODEL_ALIASES:
                normalized = _normalize_reactor_model(raw_text, default=default_model)
                if normalized not in allowed_models:
                    allowed_models.append(normalized)
    if default_model not in allowed_models:
        allowed_models.insert(0, default_model)

    configured_origin = str(cfg.get("origin") or "").strip().rstrip("/")
    effective_origin = _derive_effective_origin(configured_origin)
    min_seconds = _clamp_int(cfg.get("min_seconds"), 10, 10, 60)
    max_seconds = _clamp_int(cfg.get("max_seconds"), 60, min_seconds, 120)
    default_seconds = _clamp_int(cfg.get("default_seconds"), min(30, max_seconds), min_seconds, max_seconds)
    meta = _credential_meta(provider, feature, cfg, effective_origin)

    return {
        "provider_key": REACTOR_PROVIDER_KEY,
        **meta,
        "base_url": _normalize_reactor_base_url((provider.base_url if provider else None) or ""),
        "default_model": default_model,
        "allowed_models": allowed_models,
        "origin": configured_origin,
        "effective_origin": effective_origin,
        "min_seconds": min_seconds,
        "max_seconds": max_seconds,
        "default_seconds": default_seconds,
        "credits_per_second": _clamp_int(cfg.get("credits_per_second"), REACTOR_DEFAULT_CREDITS_PER_SECOND, 1, 10000),
        "cents_per_minute": _clamp_int(cfg.get("cents_per_minute"), REACTOR_DEFAULT_CENTS_PER_MINUTE, 1, 10_000),
        "daily_cents": _clamp_int(cfg.get("daily_cents"), 200, 0, 10_000_000),
        "monthly_cents": _clamp_int(cfg.get("monthly_cents"), 1000, 0, 10_000_000),
        "visitor_daily_cents": _clamp_int(cfg.get("visitor_daily_cents"), 50, 0, 10_000_000),
        "min_account_credits": _clamp_int(cfg.get("min_account_credits"), 1000, 0, 10_000_000),
        "max_active": _clamp_int(cfg.get("max_active"), 1, 1, 5),
        "starts_per_minute": _clamp_int(cfg.get("starts_per_minute"), 3, 1, 30),
        "default_prompt": _resolve_prompt_default(cfg, REACTOR_DEFAULT_PROMPT),
    }


def _xmax_session_cents(seconds: int, cents_per_minute: int) -> int:
    if seconds <= 0:
        return 0
    return max(1, math.ceil(int(seconds) * max(1, int(cents_per_minute)) / 60))


def _xmax_credits_to_cents(credits: float, credits_per_second: float, cents_per_minute: int) -> int:
    if credits <= 0:
        return 0
    cps = max(0.001, float(credits_per_second or 1.0))
    return max(1, math.ceil((float(credits) / cps) * max(1, int(cents_per_minute)) / 60))


def _reactor_headers(api_key: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key.strip()}",
        "Reactor-API-Version": "1",
        "Reactor-API-Accept-Version": "1",
    }


def _reactor_parse_json(resp: httpx.Response) -> dict:
    try:
        payload = resp.json()
    except Exception as exc:
        if 200 <= resp.status_code < 300:
            return {}
        raise ValueError(f"HTTP {resp.status_code}: non-JSON response") from exc
    if not isinstance(payload, dict):
        if 200 <= resp.status_code < 300:
            return {"items": payload}
        raise ValueError(f"HTTP {resp.status_code}: invalid payload")
    if not (200 <= resp.status_code < 300):
        err_obj = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        msg = str(err_obj.get("message") or payload.get("message") or payload.get("detail") or "").strip() or f"HTTP {resp.status_code}"
        raise ValueError(f"HTTP {resp.status_code}: {msg}")
    return payload


def _reactor_extract_account_id(me_payload: dict) -> str:
    if not isinstance(me_payload, dict):
        return ""
    for key in ("account_id", "default_account_id", "active_account_id"):
        val = me_payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    account_obj = me_payload.get("account")
    if isinstance(account_obj, dict):
        aid = account_obj.get("id") or account_obj.get("account_id")
        if isinstance(aid, str) and aid.strip():
            return aid.strip()
    accounts = me_payload.get("accounts")
    if isinstance(accounts, list) and accounts:
        first = accounts[0]
        if isinstance(first, dict):
            aid = first.get("id") or first.get("account_id")
            if isinstance(aid, str) and aid.strip():
                return aid.strip()
        elif isinstance(first, str) and first.strip():
            return first.strip()
    return ""


def _reactor_extract_billed_seconds(session_payload: dict) -> tuple[float | None, bool]:
    if not isinstance(session_payload, dict):
        return None, False
    raw_state = str(session_payload.get("state") or session_payload.get("status") or "").strip().upper()
    is_terminal = raw_state in {"CLOSED", "ENDED", "TERMINATED", "FAILED", "COMPLETED", "EXPIRED"}
    if session_payload.get("ended_at"):
        is_terminal = True
    for key in ("billed_seconds", "duration_seconds", "active_seconds", "runtime_seconds", "seconds"):
        val = session_payload.get(key)
        if isinstance(val, (int, float)) and not isinstance(val, bool) and val >= 0:
            return float(val), is_terminal
    return None, is_terminal


def _xmax_headers(api_key: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Api-Key": api_key.strip(),
    }


def _parse_xmax_envelope(resp: httpx.Response) -> dict:
    try:
        payload = resp.json()
    except Exception as exc:
        raise ValueError(f"HTTP {resp.status_code}: non-JSON response") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"HTTP {resp.status_code}: invalid payload")
    ok = (200 <= resp.status_code < 300) and (
        payload.get("success") is True or (payload.get("success") is None and payload.get("code") == 200)
    )
    if not ok:
        msg = str(payload.get("message") or "").strip() or f"code={payload.get('code')}"
        raise ValueError(f"HTTP {resp.status_code}: {msg}")
    data = payload.get("data")
    if data is None:
        raise ValueError("Missing data in response")
    return data if isinstance(data, dict) else {"value": data}


def _decrypt_temp_key(row: WorkbenchRealtimeSession) -> str:
    if not row.provider_temp_key_encrypted:
        return ""
    try:
        return decrypt_secret(row.provider_temp_key_encrypted).strip()
    except Exception:
        return ""


@config_router.get("")
def get_config(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    del admin
    provider, feature = _rows(db)
    return _serialize_config(provider, feature)


@config_router.put("")
def update_config(
    body: RealtimeConfigUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    provider, feature = _ensure_rows(db)
    cfg = _parse_feature_config(feature)

    next_max_seconds = body.max_seconds if body.max_seconds is not None else _clamp_int(cfg.get("max_seconds"), 20, MIN_SECONDS, 60)
    next_default_seconds = body.default_seconds if body.default_seconds is not None else _clamp_int(cfg.get("default_seconds"), min(15, next_max_seconds), MIN_SECONDS, next_max_seconds)
    if next_default_seconds > next_max_seconds:
        if body.default_seconds is not None:
            raise HTTPException(400, "默认时长不能大于单次最长时长上限")
        next_default_seconds = next_max_seconds

    cfg["max_seconds"] = next_max_seconds
    cfg["default_seconds"] = next_default_seconds

    for field in (
        "cents_per_second",
        "daily_cents",
        "monthly_cents",
        "visitor_daily_cents",
        "max_active",
        "starts_per_minute",
    ):
        val = getattr(body, field)
        if val is not None:
            cfg[field] = val

    if body.require_access_code is not None:
        cfg["require_access_code"] = bool(body.require_access_code)

    if body.origin is not None:
        cfg["origin"] = _normalize_origin(body.origin)

    if body.default_prompt is not None:
        cfg["default_prompt"] = body.default_prompt.strip()[:280]

    if body.enabled is not None:
        provider.enabled = feature.enabled = body.enabled

    if body.clear_api_key:
        provider.api_key_encrypted = None
        provider.enabled = feature.enabled = False
    elif body.api_key and body.api_key.strip():
        provider.api_key_encrypted = encrypt_secret(body.api_key.strip())

    if body.clear_access_code:
        cfg.pop("access_code_encrypted", None)
        cfg.pop("access_code_length", None)
        if bool(cfg.get("require_access_code", True)):
            provider.enabled = feature.enabled = False
    elif body.access_code is not None and body.access_code.strip():
        clean_code = body.access_code.strip()
        if not (16 <= len(clean_code) <= 256):
            raise HTTPException(400, "体验码长度必须在 16 到 256 个字符之间")
        cfg["access_code_encrypted"] = encrypt_secret(clean_code)
        cfg["access_code_length"] = len(clean_code)

    feature.config = cfg
    provider.default_model = feature.default_model = MODEL
    provider.updated_by = feature.updated_by = admin.username
    db.commit()
    db.refresh(provider)
    db.refresh(feature)
    return _serialize_config(provider, feature)


@config_router.post("/generate-code")
def generate_access_code(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    provider, feature = _ensure_rows(db)
    cfg = _parse_feature_config(feature)
    raw_code = secrets.token_urlsafe(18)
    cfg["access_code_encrypted"] = encrypt_secret(raw_code)
    cfg["access_code_length"] = len(raw_code)
    cfg["require_access_code"] = True
    feature.config = cfg
    provider.updated_by = feature.updated_by = admin.username
    db.commit()
    db.refresh(provider)
    db.refresh(feature)
    return {
        "access_code": raw_code,
        "access_code_length": len(raw_code),
        "config": _serialize_config(provider, feature),
    }


@config_router.post("/test")
async def test_config(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    provider, _ = _rows(db)
    if not provider or not provider.api_key_encrypted:
        raise HTTPException(400, "请先保存 Decart API Key")
    try:
        api_key = decrypt_secret(provider.api_key_encrypted).strip()
    except Exception:
        raise HTTPException(400, "已保存的 Decart API Key 无法解密，请重新保存")
    if not api_key:
        raise HTTPException(400, "Decart API Key 为空")

    start = time.monotonic()
    status_code = 0
    success = False
    message = ""
    try:
        async with httpx.AsyncClient(timeout=provider.timeout_seconds or 15, follow_redirects=False) as client:
            resp = await client.post(
                f"{DECART_BASE_URL}/v1/client/tokens",
                headers={"X-API-KEY": api_key},
                json={
                    "expiresIn": 10,
                    "allowedModels": [MODEL],
                    "constraints": {"realtime": {"maxSessionDuration": MIN_SECONDS}},
                },
            )
        status_code = resp.status_code
        if status_code in (200, 201):
            body = resp.json()
            returned_limit = ((body.get("constraints") or {}).get("realtime") or {}).get("maxSessionDuration")
            if isinstance(body.get("apiKey"), str) and body["apiKey"] and returned_limit == MIN_SECONDS:
                success = True
                message = "OK (scoped token issued, 0 stream cost)"
            else:
                message = "Decart returned token without expected maxSessionDuration constraint"
        else:
            message = sanitize_error_message(f"HTTP {status_code}: {resp.text[:200]}")
    except Exception as exc:
        message = sanitize_error_message(f"{type(exc).__name__}: {exc}")

    latency_ms = round((time.monotonic() - start) * 1000, 1)
    now_dt = datetime.now(tz=ZoneInfo("UTC")).replace(tzinfo=None)
    provider.last_test_status = "success" if success else "failed"
    provider.last_test_message = message
    provider.last_test_at = now_dt
    db.add(
        AIAPITestLog(
            provider_key="decart",
            test_type="realtime_client_token",
            success=success,
            latency_ms=latency_ms,
            status_code=status_code or None,
            error_code=None if success else "decart_token_check_failed",
            error_message_sanitized=None if success else message,
            created_by=admin.username,
        )
    )
    db.commit()
    return {
        "success": success,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "message": message,
    }


@config_router.get("/xmax")
def get_xmax_config(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    del admin
    provider, feature = _xmax_rows(db)
    return _serialize_xmax_config(provider, feature)


@config_router.put("/xmax")
def update_xmax_config(
    body: XmaxRealtimeConfigUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    provider, feature = _ensure_xmax_rows(db)
    cfg = _parse_feature_config(feature)

    next_env = body.environment or ("china" if str(cfg.get("environment") or "").lower() == "china" else "global")
    cfg["environment"] = next_env
    if body.base_url is not None or body.environment is not None:
        raw_url = body.base_url if body.base_url is not None else ""
        provider.base_url = _normalize_xmax_base_url(raw_url, next_env)
    elif not provider.base_url:
        provider.base_url = XMAX_DEFAULT_URLS[next_env]

    next_model = body.default_model or str(feature.default_model or provider.default_model or "x2.1")
    if next_model not in XMAX_MODELS:
        next_model = "x2.1"

    next_allowed = body.allowed_models if body.allowed_models is not None else cfg.get("allowed_models") or list(XMAX_MODELS)
    clean_allowed = [m for m in next_allowed if m in XMAX_MODELS]
    if next_model not in clean_allowed:
        clean_allowed.insert(0, next_model)
    cfg["allowed_models"] = clean_allowed

    if body.camera_preset is not None or body.default_model is not None:
        raw_preset = body.camera_preset if body.camera_preset is not None else cfg.get("camera_preset")
        cfg["camera_preset"] = _normalize_xmax_camera_preset(next_model, str(raw_preset or ""))
    if body.face_restoration is not None:
        cfg["face_restoration"] = bool(body.face_restoration)

    next_min_s = body.min_seconds if body.min_seconds is not None else _clamp_int(cfg.get("min_seconds"), 10, 10, 60)
    next_max_s = body.max_seconds if body.max_seconds is not None else _clamp_int(cfg.get("max_seconds"), 60, next_min_s, 120)
    if next_min_s > next_max_s:
        raise HTTPException(400, "最小时长不能大于单场最长时长上限")
    next_def_s = body.default_seconds if body.default_seconds is not None else _clamp_int(cfg.get("default_seconds"), min(30, next_max_s), next_min_s, next_max_s)
    if not (next_min_s <= next_def_s <= next_max_s):
        if body.default_seconds is not None:
            raise HTTPException(400, "默认时长必须介于最小时长与最长上限之间")
        next_def_s = max(next_min_s, min(next_max_s, next_def_s))

    cfg["min_seconds"] = next_min_s
    cfg["max_seconds"] = next_max_s
    cfg["default_seconds"] = next_def_s

    for field in (
        "credits_per_second",
        "cents_per_minute",
        "daily_cents",
        "monthly_cents",
        "visitor_daily_cents",
        "min_account_credits",
        "max_active",
        "starts_per_minute",
    ):
        val = getattr(body, field)
        if val is not None:
            cfg[field] = val

    if body.require_access_code is not None:
        cfg["require_access_code"] = bool(body.require_access_code)

    if body.origin is not None:
        cfg["origin"] = _normalize_origin(body.origin)

    if body.default_prompt is not None:
        cfg["default_prompt"] = body.default_prompt.strip()[:280]

    if body.enabled is not None:
        provider.enabled = feature.enabled = body.enabled

    if body.clear_api_key:
        provider.api_key_encrypted = None
        provider.enabled = feature.enabled = False
    elif body.api_key and body.api_key.strip():
        provider.api_key_encrypted = encrypt_secret(body.api_key.strip())

    if body.clear_access_code:
        cfg.pop("access_code_encrypted", None)
        cfg.pop("access_code_length", None)
        if bool(cfg.get("require_access_code", True)):
            provider.enabled = feature.enabled = False
    elif body.access_code is not None and body.access_code.strip():
        clean_code = body.access_code.strip()
        if not (16 <= len(clean_code) <= 256):
            raise HTTPException(400, "体验码长度必须在 16 到 256 个字符之间")
        cfg["access_code_encrypted"] = encrypt_secret(clean_code)
        cfg["access_code_length"] = len(clean_code)

    feature.config = cfg
    provider.default_model = feature.default_model = next_model
    provider.model_options = clean_allowed
    provider.updated_by = feature.updated_by = admin.username
    db.commit()
    db.refresh(provider)
    db.refresh(feature)
    return _serialize_xmax_config(provider, feature)


@config_router.post("/xmax/generate-code")
def generate_xmax_access_code(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    provider, feature = _ensure_xmax_rows(db)
    cfg = _parse_feature_config(feature)
    raw_code = secrets.token_urlsafe(18)
    cfg["access_code_encrypted"] = encrypt_secret(raw_code)
    cfg["access_code_length"] = len(raw_code)
    cfg["require_access_code"] = True
    feature.config = cfg
    provider.updated_by = feature.updated_by = admin.username
    db.commit()
    db.refresh(provider)
    db.refresh(feature)
    return {
        "access_code": raw_code,
        "access_code_length": len(raw_code),
        "config": _serialize_xmax_config(provider, feature),
    }


@config_router.post("/xmax/test")
async def test_xmax_config(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    provider, feature = _xmax_rows(db)
    if not provider or not provider.api_key_encrypted:
        raise HTTPException(400, "请先保存 Xmax API Key")
    try:
        api_key = decrypt_secret(provider.api_key_encrypted).strip()
    except Exception:
        raise HTTPException(400, "已保存的 Xmax API Key 无法解密，请重新保存")
    if not api_key:
        raise HTTPException(400, "Xmax API Key 为空")

    xmax_cfg = _serialize_xmax_config(provider, feature)
    base_url = xmax_cfg["base_url"].rstrip("/")
    start = time.monotonic()
    status_code = 0
    success = False
    message = ""
    current_balance: float | None = None

    try:
        async with httpx.AsyncClient(timeout=provider.timeout_seconds or 15, follow_redirects=False) as client:
            resp = await client.get(f"{base_url}/balance", headers=_xmax_headers(api_key))
        status_code = resp.status_code
        data = _parse_xmax_envelope(resp)
        bal = data.get("currentBalance")
        if isinstance(bal, (int, float)) and not isinstance(bal, bool) and bal >= 0:
            current_balance = float(bal)
            success = True
            message = f"OK (balance={current_balance}, 0 credit consumed)"
        else:
            message = "Xmax /balance returned invalid currentBalance"
    except Exception as exc:
        message = sanitize_error_message(str(exc))

    latency_ms = round((time.monotonic() - start) * 1000, 1)
    now_dt = datetime.now(tz=ZoneInfo("UTC")).replace(tzinfo=None)
    provider.last_test_status = "success" if success else "failed"
    provider.last_test_message = message
    provider.last_test_at = now_dt
    db.add(
        AIAPITestLog(
            provider_key="xmax",
            test_type="realtime_balance_check",
            success=success,
            latency_ms=latency_ms,
            status_code=status_code or None,
            error_code=None if success else "xmax_balance_check_failed",
            error_message_sanitized=None if success else message,
            created_by=admin.username,
        )
    )
    db.commit()
    return {
        "success": success,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "message": message,
        "current_balance": current_balance,
    }


def _apply_duration_and_common_config(
    body,
    provider: AIAPIProvider,
    feature: AIFeatureConfig,
    cfg: dict,
    admin: AdminUser,
    numeric_fields: tuple[str, ...],
) -> None:
    next_min_s = body.min_seconds if body.min_seconds is not None else _clamp_int(cfg.get("min_seconds"), 10, 10, 60)
    next_max_s = body.max_seconds if body.max_seconds is not None else _clamp_int(cfg.get("max_seconds"), 60, next_min_s, 120)
    if next_min_s > next_max_s:
        raise HTTPException(400, "最小时长不能大于单场最长时长上限")
    next_def_s = body.default_seconds if body.default_seconds is not None else _clamp_int(cfg.get("default_seconds"), min(30, next_max_s), next_min_s, next_max_s)
    if not (next_min_s <= next_def_s <= next_max_s):
        if body.default_seconds is not None:
            raise HTTPException(400, "默认时长必须介于最小时长与最长上限之间")
        next_def_s = max(next_min_s, min(next_max_s, next_def_s))

    cfg["min_seconds"] = next_min_s
    cfg["max_seconds"] = next_max_s
    cfg["default_seconds"] = next_def_s

    for field in numeric_fields:
        val = getattr(body, field)
        if val is not None:
            cfg[field] = val

    if body.require_access_code is not None:
        cfg["require_access_code"] = bool(body.require_access_code)
    if body.origin is not None:
        cfg["origin"] = _normalize_origin(body.origin)
    if body.default_prompt is not None:
        cfg["default_prompt"] = body.default_prompt.strip()[:280]
    if body.enabled is not None:
        provider.enabled = feature.enabled = body.enabled

    if body.clear_api_key:
        provider.api_key_encrypted = None
        provider.enabled = feature.enabled = False
    elif body.api_key and body.api_key.strip():
        provider.api_key_encrypted = encrypt_secret(body.api_key.strip())

    if body.clear_access_code:
        cfg.pop("access_code_encrypted", None)
        cfg.pop("access_code_length", None)
        if bool(cfg.get("require_access_code", True)):
            provider.enabled = feature.enabled = False
    elif body.access_code is not None and body.access_code.strip():
        clean_code = body.access_code.strip()
        if not (16 <= len(clean_code) <= 256):
            raise HTTPException(400, "体验码长度必须在 16 到 256 个字符之间")
        cfg["access_code_encrypted"] = encrypt_secret(clean_code)
        cfg["access_code_length"] = len(clean_code)

    provider.updated_by = feature.updated_by = admin.username


@config_router.get("/reactor")
def get_reactor_config(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    del admin
    provider, feature = _reactor_rows(db)
    return _serialize_reactor_config(provider, feature)


@config_router.put("/reactor")
def update_reactor_config(
    body: ReactorRealtimeConfigUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    provider, feature = _ensure_reactor_rows(db)
    cfg = _parse_feature_config(feature)

    if body.base_url is not None:
        provider.base_url = _normalize_reactor_base_url(body.base_url)
    elif not provider.base_url:
        provider.base_url = REACTOR_DEFAULT_BASE_URL

    next_model = _normalize_reactor_model(
        body.default_model or str(feature.default_model or provider.default_model or REACTOR_DEFAULT_MODEL)
    )
    raw_allowed = body.allowed_models if body.allowed_models is not None else cfg.get("allowed_models") or list(REACTOR_MODELS)
    clean_allowed: list[str] = []
    for item in raw_allowed:
        raw_text = str(item or "").strip().lower()
        if raw_text in REACTOR_MODEL_ALIASES:
            normalized = _normalize_reactor_model(raw_text, default=next_model)
            if normalized not in clean_allowed:
                clean_allowed.append(normalized)
    if next_model not in clean_allowed:
        clean_allowed.insert(0, next_model)
    cfg["allowed_models"] = clean_allowed

    _apply_duration_and_common_config(
        body,
        provider,
        feature,
        cfg,
        admin,
        (
            "credits_per_second",
            "cents_per_minute",
            "daily_cents",
            "monthly_cents",
            "visitor_daily_cents",
            "min_account_credits",
            "max_active",
            "starts_per_minute",
        ),
    )

    feature.config = cfg
    provider.default_model = feature.default_model = next_model
    provider.model_options = clean_allowed
    db.commit()
    db.refresh(provider)
    db.refresh(feature)
    return _serialize_reactor_config(provider, feature)


@config_router.post("/reactor/generate-code")
def generate_reactor_access_code(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    provider, feature = _ensure_reactor_rows(db)
    cfg = _parse_feature_config(feature)
    raw_code = secrets.token_urlsafe(18)
    cfg["access_code_encrypted"] = encrypt_secret(raw_code)
    cfg["access_code_length"] = len(raw_code)
    cfg["require_access_code"] = True
    feature.config = cfg
    provider.updated_by = feature.updated_by = admin.username
    db.commit()
    db.refresh(provider)
    db.refresh(feature)
    return {
        "access_code": raw_code,
        "access_code_length": len(raw_code),
        "config": _serialize_reactor_config(provider, feature),
    }


@config_router.post("/reactor/test")
async def test_reactor_config(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    provider, feature = _reactor_rows(db)
    if not provider or not provider.api_key_encrypted:
        raise HTTPException(400, "请先保存 Reactor API Key")
    try:
        api_key = decrypt_secret(provider.api_key_encrypted).strip()
    except Exception:
        raise HTTPException(400, "已保存的 Reactor API Key 无法解密，请重新保存")
    if not api_key:
        raise HTTPException(400, "Reactor API Key 为空")

    reactor_cfg = _serialize_reactor_config(provider, feature)
    base_url = reactor_cfg["base_url"].rstrip("/")
    start = time.monotonic()
    status_code = 0
    success = False
    message = ""
    account_id = ""
    current_balance: float | None = None
    balance_usd: float | None = None

    try:
        headers = _reactor_headers(api_key)
        async with httpx.AsyncClient(timeout=provider.timeout_seconds or 15, follow_redirects=False) as client:
            r_me = await client.get(f"{base_url}/me", headers=headers)
            status_code = r_me.status_code
            me_data = _reactor_parse_json(r_me)
            account_id = _reactor_extract_account_id(me_data)
            if not account_id:
                raise ValueError("Reactor /me did not return account_id")

            r_credits = await client.get(f"{base_url}/accounts/{quote(account_id, safe='')}/credits", headers=headers)
            status_code = r_credits.status_code
            credits_data = _reactor_parse_json(r_credits)
            raw_bal = credits_data.get("balance")
            if raw_bal is None and isinstance(credits_data.get("credits"), (int, float)):
                raw_bal = credits_data.get("credits")
            if isinstance(raw_bal, (int, float)) and not isinstance(raw_bal, bool) and raw_bal >= 0:
                current_balance = float(raw_bal)
                raw_usd = credits_data.get("balance_usd")
                balance_usd = (
                    round(float(raw_usd), 4)
                    if isinstance(raw_usd, (int, float)) and not isinstance(raw_usd, bool)
                    else round(current_balance / 10000.0, 4)
                )
                success = True
                message = f"OK (balance={int(current_balance) if current_balance.is_integer() else current_balance} credits / ${balance_usd:.4f}, 0 credit consumed)"
            else:
                message = "Reactor /credits returned invalid balance"
    except Exception as exc:
        message = sanitize_error_message(str(exc))

    latency_ms = round((time.monotonic() - start) * 1000, 1)
    now_dt = datetime.now(tz=ZoneInfo("UTC")).replace(tzinfo=None)
    provider.last_test_status = "success" if success else "failed"
    provider.last_test_message = message
    provider.last_test_at = now_dt
    db.add(
        AIAPITestLog(
            provider_key=REACTOR_PROVIDER_KEY,
            test_type="realtime_balance_check",
            success=success,
            latency_ms=latency_ms,
            status_code=status_code or None,
            error_code=None if success else "reactor_balance_check_failed",
            error_message_sanitized=None if success else message,
            created_by=admin.username,
        )
    )
    db.commit()
    return {
        "success": success,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "message": message,
        "account_id": account_id or None,
        "current_balance": current_balance,
        "balance_usd": balance_usd,
    }


def _extract_pricing_models(pricing_payload: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    if not isinstance(pricing_payload, dict):
        return result
    candidates = pricing_payload.get("models")
    if isinstance(candidates, dict):
        for name, item in candidates.items():
            if isinstance(item, dict):
                result[str(name).strip().lower()] = item
    elif isinstance(candidates, list):
        for item in candidates:
            if not isinstance(item, dict):
                continue
            name = str(item.get("model") or item.get("name") or item.get("id") or "").strip().lower()
            if name:
                result[name] = item
    items = pricing_payload.get("items") or pricing_payload.get("data")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("model") or item.get("name") or item.get("id") or "").strip().lower()
            if name:
                result[name] = item
    for known in REACTOR_MODELS:
        if known not in result and isinstance(pricing_payload.get(known), dict):
            result[known] = pricing_payload[known]
    return result


def _optional_api_key(body: FetchOfficialRequest | None, provider: AIAPIProvider | None) -> str:
    if body and body.api_key and body.api_key.strip():
        return body.api_key.strip()
    if provider and provider.api_key_encrypted:
        with suppress(Exception):
            return decrypt_secret(provider.api_key_encrypted).strip()
    return ""


@config_router.post("/{provider}/fetch-official")
async def fetch_official_realtime_data(
    provider: str,
    body: FetchOfficialRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    del admin
    p_key = provider.strip().lower()
    if p_key not in {"decart", "xmax", "reactor"}:
        raise HTTPException(400, f"不支持的实时试穿引擎: {provider}")

    fetched_at = datetime.now(tz=ZoneInfo("UTC")).isoformat()

    if p_key == "reactor":
        prov, feat = _reactor_rows(db)
        base_url = _normalize_reactor_base_url((body.base_url if body and body.base_url else None) or (prov.base_url if prov else "") or REACTOR_DEFAULT_BASE_URL)
        credits_per_dollar = 10000
        x21_aps = float(REACTOR_DEFAULT_CREDITS_PER_SECOND)
        x21_usd = 0.0017
        x20_aps = float(REACTOR_DEFAULT_CREDITS_PER_SECOND)
        x20_usd = 0.0017
        source = "catalog_fallback"
        warning = ""
        account_info: dict = {}

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            try:
                r_price = await client.get(f"{base_url}/pricing", headers={"Accept": "application/json"})
                p_data = _reactor_parse_json(r_price)
                if isinstance(p_data.get("credits_per_dollar"), (int, float)) and p_data["credits_per_dollar"] > 0:
                    credits_per_dollar = int(round(float(p_data["credits_per_dollar"])))
                models_map = _extract_pricing_models(p_data)
                if "reactor/xmax-x2-1" in models_map:
                    m21 = models_map["reactor/xmax-x2-1"]
                    if isinstance(m21.get("amount_per_sec"), (int, float)):
                        x21_aps = float(m21["amount_per_sec"])
                    with suppress(TypeError, ValueError):
                        x21_usd = float(m21.get("amount_per_sec_usd") or (x21_aps / max(1, credits_per_dollar)))
                if "xmax/x2" in models_map:
                    m20 = models_map["xmax/x2"]
                    if isinstance(m20.get("amount_per_sec"), (int, float)):
                        x20_aps = float(m20["amount_per_sec"])
                    with suppress(TypeError, ValueError):
                        x20_usd = float(m20.get("amount_per_sec_usd") or (x20_aps / max(1, credits_per_dollar)))
                source = "live_api"
            except Exception as exc:
                warning = sanitize_error_message(str(exc))

            api_key = _optional_api_key(body, prov)
            if api_key:
                try:
                    headers = _reactor_headers(api_key)
                    r_me = await client.get(f"{base_url}/me", headers=headers)
                    aid = _reactor_extract_account_id(_reactor_parse_json(r_me))
                    if aid:
                        r_cr = await client.get(f"{base_url}/accounts/{quote(aid, safe='')}/credits", headers=headers)
                        cr_data = _reactor_parse_json(r_cr)
                        raw_bal = cr_data.get("balance")
                        if raw_bal is None and isinstance(cr_data.get("credits"), (int, float)):
                            raw_bal = cr_data.get("credits")
                        bal = float(raw_bal or 0.0)
                        bal_usd = round(float(cr_data.get("balance_usd") or (bal / max(1, credits_per_dollar))), 4)
                        account_info = {
                            "account_id": aid,
                            "balance": bal,
                            "balance_usd": bal_usd,
                            "currency_code": str(cr_data.get("currency_code") or "USD"),
                        }
                        with suppress(Exception):
                            r_q = await client.get(f"{base_url}/accounts/{quote(aid, safe='')}/quotas", headers=headers)
                            account_info["quotas"] = _reactor_parse_json(r_q)
                        if source == "live_api":
                            source = "live_api"
                except Exception as exc:
                    key_warn = sanitize_error_message(str(exc))
                    warning = f"{warning}; {key_warn}".strip("; ") if warning else key_warn

        cps = max(1, int(round(x21_aps)))
        cpm = max(1, math.ceil(x21_usd * 60.0 * 100.0))
        suggested = {
            "base_url": base_url,
            "default_model": REACTOR_DEFAULT_MODEL,
            "allowed_models": list(REACTOR_MODELS),
            "min_seconds": 10,
            "max_seconds": 60,
            "default_seconds": 30,
            "credits_per_second": cps,
            "cents_per_minute": cpm,
            "daily_cents": 200,
            "monthly_cents": 1000,
            "visitor_daily_cents": 50,
            "min_account_credits": 1000,
            "max_active": 1,
            "starts_per_minute": 3,
            "default_prompt": REACTOR_DEFAULT_PROMPT,
        }
        bal_note = f" · 账户余额 {account_info['balance']:.0f} credits (${account_info['balance_usd']:.4f})" if "balance" in account_info else ""
        return {
            "ok": True,
            "provider": "reactor",
            "source": source,
            "fetched_at": fetched_at,
            "summary": f"X2.1={cps} credits/s (${x21_usd:.4f}/s, ~${x21_usd * 60:.3f}/min → 预算折算 {cpm}¢/min){bal_note}",
            "warning": warning or None,
            "official_rates": {
                "credits_per_dollar": credits_per_dollar,
                "models": {
                    "reactor/xmax-x2-1": {"amount_per_sec": x21_aps, "amount_per_sec_usd": f"{x21_usd:.4f}"},
                    "xmax/x2": {"amount_per_sec": x20_aps, "amount_per_sec_usd": f"{x20_usd:.4f}"},
                },
            },
            "account_info": account_info,
            "suggested_fields": suggested,
        }

    if p_key == "xmax":
        prov, feat = _xmax_rows(db)
        cfg = _parse_feature_config(feat)
        env = "china" if ((body and body.environment) or cfg.get("environment") or "global").strip().lower() == "china" else "global"
        raw_url = (body.base_url if body and body.base_url else "").strip().rstrip("/")
        other_env = "global" if env == "china" else "china"
        if not raw_url or raw_url == XMAX_DEFAULT_URLS[other_env]:
            base_url = XMAX_DEFAULT_URLS[env]
        else:
            base_url = _normalize_xmax_base_url(raw_url, env)

        source = "official_catalog"
        warning = ""
        account_info = {}
        api_key = _optional_api_key(body, prov)
        if api_key:
            try:
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                    resp = await client.get(f"{base_url}/balance", headers=_xmax_headers(api_key))
                    data = _parse_xmax_envelope(resp)
                    bal = float(data.get("currentBalance") or 0.0)
                    account_info = {"balance": bal, "currency": "credits", "environment": env}
                    source = "live_api+official_catalog"
            except Exception as exc:
                warning = sanitize_error_message(str(exc))

        bal_note = f" · 当前余额 {account_info['balance']:.0f} credits" if "balance" in account_info else ""
        allowed_models_for_env = ["x2.1"] if env == "global" else ["x2.1", "x2.1-flash"]
        env_model_note = "仅开放 X2.1 (1080p)" if env == "global" else "开放 X2.1 / X2.1-Flash"
        return {
            "ok": True,
            "provider": "xmax",
            "source": source,
            "fetched_at": fetched_at,
            "summary": f"Xmax X2.1 ({env}, {env_model_note})：1 credit/s (~$0.10/min){bal_note}",
            "warning": warning or None,
            "official_rates": {
                "x2.1": {"credits_per_second": 1, "cents_per_minute": 10, "resolution": "1080p"},
                "x2.1-flash": {"credits_per_second": 1, "cents_per_minute": 10, "resolution": "720p (China node only)"},
            },
            "account_info": account_info,
            "suggested_fields": {
                "environment": env,
                "base_url": base_url,
                "default_model": "x2.1",
                "allowed_models": allowed_models_for_env,
                "camera_preset": "1080x1920",
                "face_restoration": True,
                "min_seconds": 10,
                "max_seconds": 60,
                "default_seconds": 30,
                "credits_per_second": 1,
                "cents_per_minute": 10,
                "daily_cents": 200,
                "monthly_cents": 1000,
                "visitor_daily_cents": 50,
                "min_account_credits": 60,
                "max_active": 1,
                "starts_per_minute": 3,
                "default_prompt": XMAX_DEFAULT_PROMPT,
            },
        }

    # Decart official catalog + optional zero-cost token probe
    prov, _ = _rows(db)
    source = "official_catalog"
    warning = ""
    account_info = {}
    api_key = _optional_api_key(body, prov)
    if api_key:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                resp = await client.post(
                    f"{((prov.base_url if prov else None) or DECART_BASE_URL).rstrip('/')}/v1/client/tokens",
                    headers={"X-API-KEY": api_key},
                    json={
                        "expiresIn": MIN_SECONDS,
                        "allowedModels": [MODEL],
                        "constraints": {"realtime": {"maxSessionDuration": MIN_SECONDS}},
                    },
                )
                if resp.status_code in (200, 201):
                    account_info = {"token_probe": "ok"}
                    source = "live_api+official_catalog"
                else:
                    warning = f"HTTP {resp.status_code}"
        except Exception as exc:
            warning = sanitize_error_message(str(exc))

    probe_note = " · API Key 鉴权正常" if account_info.get("token_probe") == "ok" else ""
    return {
        "ok": True,
        "provider": "decart",
        "source": source,
        "fetched_at": fetched_at,
        "summary": f"Decart Lucy VTON 3.6 ({MODEL}) · 720p · $0.02/s (2¢/s){probe_note}",
        "warning": warning or None,
        "official_rates": {
            MODEL: {"cents_per_second": 2, "usd_per_second": "0.02", "resolution": "720p"},
        },
        "account_info": account_info,
        "suggested_fields": {
            "cents_per_second": 2,
            "max_seconds": 20,
            "default_seconds": 15,
            "daily_cents": 200,
            "monthly_cents": 1000,
            "visitor_daily_cents": 80,
            "max_active": 1,
            "starts_per_minute": 3,
            "default_prompt": DECART_DEFAULT_PROMPT,
        },
    }


def _calendar(now: float) -> tuple[str, str, datetime]:
    local = datetime.fromtimestamp(now, BUDGET_ZONE)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return local.date().isoformat(), local.date().replace(day=1).isoformat(), midnight + timedelta(days=1)


def _row_provider_key(row: WorkbenchRealtimeSession) -> str:
    return (row.provider_key or "decart").strip().lower() or "decart"


def _effective_session(row: WorkbenchRealtimeSession, now: float) -> tuple[str, str | None, int, bool]:
    state = row.state
    reason = row.reason
    cents = int(row.accounted_cents or 0)
    if state == "reserved" and row.claim_before <= now:
        state, reason, cents = "ended", "expired", 0
    elif state == "claimed" and row.hold_until <= now:
        state, reason = "ended", "usage_unconfirmed"
    is_active = state in ("reserved", "claimed")
    return state, reason, cents, is_active


def _serialize_session(row: WorkbenchRealtimeSession, now: float) -> dict:
    eff_state, eff_reason, eff_cents, is_active = _effective_session(row, now)
    provider_key = _row_provider_key(row)
    is_subcent = provider_key in ("xmax", "reactor")
    default_cpm = REACTOR_DEFAULT_CENTS_PER_MINUTE if provider_key == "reactor" else 10
    default_model = REACTOR_DEFAULT_MODEL if provider_key == "reactor" else ("x2.1" if provider_key == "xmax" else MODEL)
    max_cents = (
        _xmax_session_cents(int(row.limit_seconds), int(row.cents_per_minute or default_cpm))
        if is_subcent
        else int(row.limit_seconds) * int(row.cents_per_second)
    )
    created_hk = datetime.fromtimestamp(row.created_at, BUDGET_ZONE).strftime("%Y-%m-%d %H:%M:%S")
    ended_hk = (
        datetime.fromtimestamp(row.ended_at, BUDGET_ZONE).strftime("%Y-%m-%d %H:%M:%S")
        if row.ended_at
        else None
    )
    return {
        "id": row.id,
        "provider_key": provider_key,
        "model_id": row.model_id or default_model,
        "visitor_short": row.visitor_hash[:10],
        "budget_day": row.budget_day,
        "state": eff_state,
        "raw_state": row.state,
        "is_active": is_active,
        "stop_requested": bool(row.stop_requested),
        "limit_seconds": int(row.limit_seconds),
        "cents_per_second": int(row.cents_per_second),
        "cents_per_minute": int(row.cents_per_minute) if row.cents_per_minute is not None else None,
        "credits_per_second": row.credits_per_second,
        "max_credits": row.max_credits,
        "max_cents": max_cents,
        "accounted_cents": eff_cents,
        "provider_seconds": row.provider_seconds,
        "provider_credits": row.provider_credits,
        "provider_session_id": row.provider_session_id,
        "provider_temp_key_uid": row.provider_temp_key_uid,
        "can_sync_upstream": bool(
            (provider_key == "xmax" and (row.provider_temp_key_encrypted or row.provider_session_id))
            or (provider_key == "reactor" and row.provider_session_id)
        ),
        "reason": eff_reason,
        "created_at": created_hk,
        "ended_at": ended_hk,
        "hold_remaining_seconds": max(0, round(row.hold_until - now, 1)) if is_active else 0,
    }


async def _reactor_upstream_stop_and_settle(
    db: Session,
    row: WorkbenchRealtimeSession,
    *,
    reason_on_confirm: str = "admin_stopped",
    stop_first: bool = True,
) -> bool:
    provider, feature = _reactor_rows(db)
    if not provider or not provider.api_key_encrypted:
        return False
    try:
        api_key = decrypt_secret(provider.api_key_encrypted).strip()
    except Exception:
        return False
    if not api_key:
        return False

    cfg = _serialize_reactor_config(provider, feature)
    base_url = cfg["base_url"].rstrip("/")
    sid = str(row.provider_session_id or "").strip()
    if not sid:
        return False

    headers = _reactor_headers(api_key)
    billed_seconds: float | None = None
    is_terminal = False

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
        if stop_first:
            with suppress(Exception):
                await client.request(
                    "DELETE",
                    f"{base_url}/sessions/{quote(sid, safe='')}",
                    headers=headers,
                    json={"reason": str(reason_on_confirm or "admin_stopped")[:200]},
                )

        sess_payload: dict | None = None
        with suppress(Exception):
            r_sess = await client.get(f"{base_url}/sessions/{quote(sid, safe='')}", headers=headers)
            if 200 <= r_sess.status_code < 300:
                sess_payload = _reactor_parse_json(r_sess)

        if sess_payload is None:
            with suppress(Exception):
                r_me = await client.get(f"{base_url}/me", headers=headers)
                aid = _reactor_extract_account_id(_reactor_parse_json(r_me))
                if aid:
                    r_list = await client.get(
                        f"{base_url}/accounts/{quote(aid, safe='')}/sessions",
                        headers=headers,
                        params={"status": "all", "limit": 50},
                    )
                    listing = _reactor_parse_json(r_list)
                    items = listing.get("items") or listing.get("sessions") or []
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict) and str(item.get("id") or item.get("session_id") or "").strip() == sid:
                                sess_payload = item
                                break

        if isinstance(sess_payload, dict):
            billed_seconds, is_terminal = _reactor_extract_billed_seconds(sess_payload)

    if billed_seconds is not None and (is_terminal or billed_seconds > 0):
        cps = max(0.001, float(row.credits_per_second or REACTOR_DEFAULT_CREDITS_PER_SECOND))
        cpm = max(1, int(row.cents_per_minute or REACTOR_DEFAULT_CENTS_PER_MINUTE))
        row.provider_seconds = round(float(billed_seconds), 3)
        row.provider_credits = round(float(billed_seconds) * cps, 2)
        row.accounted_cents = max(1, math.ceil(float(billed_seconds) * cpm / 60.0)) if billed_seconds > 0 else 0
        row.hold_until = 0.0
        row.state = "ended"
        if row.reason not in {"timeout", "stopped", "admin_stopped", "admin_reconciled"}:
            row.reason = reason_on_confirm
        if not row.ended_at:
            row.ended_at = time.time()
        row.provider_temp_key_encrypted = None
        return True
    return False


async def _xmax_upstream_stop_and_settle(
    db: Session,
    row: WorkbenchRealtimeSession,
    *,
    reason_on_confirm: str = "admin_stopped",
) -> bool:
    provider, feature = _xmax_rows(db)
    if not provider or not provider.api_key_encrypted:
        return False
    try:
        api_key = decrypt_secret(provider.api_key_encrypted).strip()
    except Exception:
        return False
    if not api_key:
        return False

    cfg = _serialize_xmax_config(provider, feature)
    base_url = cfg["base_url"].rstrip("/")
    temp_key = _decrypt_temp_key(row)
    upstream_settled = False

    async with httpx.AsyncClient(timeout=6.0, follow_redirects=False) as client:
        if row.provider_session_id:
            with suppress(Exception):
                await client.delete(
                    f"{base_url}/session/{quote(row.provider_session_id, safe='')}",
                    headers=_xmax_headers(temp_key or api_key),
                )
        if temp_key:
            with suppress(Exception):
                await client.put(
                    f"{base_url}/temporary-api-key/{quote(temp_key, safe='')}/inactive",
                    headers=_xmax_headers(api_key),
                )

        consumed_credits: float | None = None
        is_terminal = False
        if temp_key:
            with suppress(Exception):
                resp = await client.get(
                    f"{base_url}/temporary-api-key/{quote(temp_key, safe='')}/status",
                    headers=_xmax_headers(api_key),
                )
                data = _parse_xmax_envelope(resp)
                raw_credit = data.get("consumedCredit")
                if isinstance(raw_credit, (int, float)) and not isinstance(raw_credit, bool) and raw_credit >= 0:
                    consumed_credits = float(raw_credit)
                if str(data.get("status") or "").lower() in {"inactive", "timeout"}:
                    is_terminal = True

        if consumed_credits is None and row.provider_session_id:
            with suppress(Exception):
                resp = await client.get(
                    f"{base_url}/session/{quote(row.provider_session_id, safe='')}/status",
                    headers=_xmax_headers(api_key),
                )
                data = _parse_xmax_envelope(resp)
                raw_credit = data.get("consumedCredit")
                if isinstance(raw_credit, (int, float)) and not isinstance(raw_credit, bool) and raw_credit >= 0:
                    consumed_credits = float(raw_credit)
                if str(data.get("status") or "").upper() in {"CLOSED", "TIMEOUT"}:
                    is_terminal = True

        if consumed_credits is not None:
            cps = max(0.001, float(row.credits_per_second or 1.0))
            cpm = max(1, int(row.cents_per_minute or 10))
            row.provider_credits = round(consumed_credits, 3)
            row.provider_seconds = round(consumed_credits / cps, 3)
            row.accounted_cents = _xmax_credits_to_cents(consumed_credits, cps, cpm)
            row.hold_until = 0.0
            row.state = "ended"
            if row.reason not in {"timeout", "stopped", "admin_stopped", "admin_reconciled"}:
                row.reason = reason_on_confirm
            if not row.ended_at:
                row.ended_at = time.time()
            upstream_settled = True

        if is_terminal or upstream_settled:
            row.provider_temp_key_encrypted = None

    return upstream_settled


def _provider_filter_clause(provider_scope: str):
    if provider_scope == "xmax":
        return WorkbenchRealtimeSession.provider_key == "xmax"
    if provider_scope == "reactor":
        return WorkbenchRealtimeSession.provider_key == "reactor"
    if provider_scope == "decart":
        return or_(WorkbenchRealtimeSession.provider_key == "decart", WorkbenchRealtimeSession.provider_key.is_(None))
    return None


async def _execute_emergency_stop(
    provider_scope: Literal["all", "decart", "xmax", "reactor"],
    admin: AdminUser,
    db: Session,
) -> dict:
    now = time.time()
    if provider_scope in {"all", "decart"}:
        d_prov, d_feat = _ensure_rows(db)
        d_prov.enabled = False
        d_feat.enabled = False
        d_prov.updated_by = d_feat.updated_by = admin.username

    if provider_scope in {"all", "xmax"}:
        x_prov, x_feat = _ensure_xmax_rows(db)
        x_prov.enabled = False
        x_feat.enabled = False
        x_prov.updated_by = x_feat.updated_by = admin.username

    if provider_scope in {"all", "reactor"}:
        r_prov, r_feat = _ensure_reactor_rows(db)
        r_prov.enabled = False
        r_feat.enabled = False
        r_prov.updated_by = r_feat.updated_by = admin.username

    clause = _provider_filter_clause(provider_scope)

    res_q = db.query(WorkbenchRealtimeSession).filter(WorkbenchRealtimeSession.state == "reserved")
    if clause is not None:
        res_q = res_q.filter(clause)
    canceled_reserved = 0
    for row in res_q.all():
        row.state = "ended"
        row.hold_until = 0.0
        row.accounted_cents = 0
        row.reason = "admin_stopped"
        row.ended_at = now
        row.provider_temp_key_encrypted = None
        canceled_reserved += 1

    claimed_q = db.query(WorkbenchRealtimeSession).filter(
        WorkbenchRealtimeSession.state == "claimed",
        WorkbenchRealtimeSession.hold_until > now,
    )
    if clause is not None:
        claimed_q = claimed_q.filter(clause)
    signaled_active = 0
    for row in claimed_q.all():
        if not row.stop_requested:
            row.stop_requested = True
            signaled_active += 1
        p_key = _row_provider_key(row)
        if p_key == "xmax":
            await _xmax_upstream_stop_and_settle(db, row, reason_on_confirm="admin_stopped")
        elif p_key == "reactor":
            await _reactor_upstream_stop_and_settle(db, row, reason_on_confirm="admin_stopped", stop_first=True)

    db.commit()
    return {
        "ok": True,
        "provider": provider_scope,
        "disabled": True,
        "canceled_reserved": canceled_reserved,
        "signaled_active": signaled_active,
    }


@config_router.post("/emergency-stop")
async def emergency_stop_config(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    return await _execute_emergency_stop("all", admin, db)


@config_router.post("/xmax/emergency-stop")
async def emergency_stop_xmax(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    return await _execute_emergency_stop("xmax", admin, db)


@config_router.post("/reactor/emergency-stop")
async def emergency_stop_reactor(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    return await _execute_emergency_stop("reactor", admin, db)


@admin_router.post("/emergency-stop")
async def emergency_stop(
    provider: Literal["all", "decart", "xmax", "reactor"] = "all",
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return await _execute_emergency_stop(provider, admin, db)


@admin_router.get("/overview")
def get_overview(
    provider: Literal["all", "decart", "xmax", "reactor"] = "all",
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    del admin
    now = time.time()
    day_str, month_str, tomorrow = _calendar(now)
    d_prov, d_feat = _rows(db)
    x_prov, x_feat = _xmax_rows(db)
    r_prov, r_feat = _reactor_rows(db)
    decart_cfg = _serialize_config(d_prov, d_feat)
    xmax_cfg = _serialize_xmax_config(x_prov, x_feat)
    reactor_cfg = _serialize_reactor_config(r_prov, r_feat)

    start_14d_dt = datetime.fromtimestamp(now, BUDGET_ZONE).date() - timedelta(days=13)
    min_day_needed = min(month_str, start_14d_dt.isoformat())
    q = db.query(WorkbenchRealtimeSession).filter(WorkbenchRealtimeSession.budget_day >= min_day_needed)
    rows = q.all()

    trend_map: dict[str, dict] = {}
    for offset in range(13, -1, -1):
        d = (datetime.fromtimestamp(now, BUDGET_ZONE).date() - timedelta(days=offset)).isoformat()
        trend_map[d] = {
            "date": d,
            "sessions": 0,
            "accounted_cents": 0,
            "confirmed_cents": 0,
            "provider_seconds": 0.0,
        }

    reason_counts: dict[str, int] = defaultdict(int)
    visitor_map: dict[str, dict] = {}

    per_provider_stats: dict[str, dict] = {
        key: {
            "active_sessions": 0,
            "starts_last_minute": 0,
            "daily_accounted": 0,
            "daily_confirmed": 0,
            "daily_sessions": 0,
            "monthly_accounted": 0,
            "monthly_confirmed": 0,
            "monthly_sessions": 0,
        }
        for key in ("decart", "reactor", "xmax")
    }

    daily_accounted = 0
    daily_confirmed = 0
    daily_sessions = 0
    monthly_accounted = 0
    monthly_confirmed = 0
    monthly_sessions = 0
    active_sessions = 0
    starts_last_minute = 0

    for row in rows:
        p_key = _row_provider_key(row)
        eff_state, eff_reason, eff_cents, is_active = _effective_session(row, now)
        counts_toward_budget = not (row.state == "reserved" and row.claim_before <= now)
        confirmed = (row.provider_seconds is not None) or (row.provider_credits is not None)

        ps = per_provider_stats.get(p_key)
        if ps is not None:
            if is_active:
                ps["active_sessions"] += 1
            if row.created_at > now - 60:
                ps["starts_last_minute"] += 1
            if month_str <= row.budget_day <= day_str and counts_toward_budget:
                ps["monthly_sessions"] += 1
                ps["monthly_accounted"] += eff_cents
                if confirmed:
                    ps["monthly_confirmed"] += eff_cents
                if row.budget_day == day_str:
                    ps["daily_sessions"] += 1
                    ps["daily_accounted"] += eff_cents
                    if confirmed:
                        ps["daily_confirmed"] += eff_cents

        if provider != "all" and p_key != provider:
            continue

        if is_active:
            active_sessions += 1
        if row.created_at > now - 60:
            starts_last_minute += 1

        if row.budget_day in trend_map and counts_toward_budget:
            bucket = trend_map[row.budget_day]
            bucket["sessions"] += 1
            bucket["accounted_cents"] += eff_cents
            if confirmed:
                bucket["confirmed_cents"] += eff_cents
                bucket["provider_seconds"] = round(bucket["provider_seconds"] + float(row.provider_seconds or 0.0), 2)

        if month_str <= row.budget_day <= day_str:
            if not is_active and eff_reason:
                reason_counts[eff_reason] += 1
            if counts_toward_budget:
                monthly_sessions += 1
                monthly_accounted += eff_cents
                if confirmed:
                    monthly_confirmed += eff_cents

                if row.budget_day == day_str:
                    daily_sessions += 1
                    daily_accounted += eff_cents
                    if confirmed:
                        daily_confirmed += eff_cents
                    v_key = row.visitor_hash[:10]
                    v_entry = visitor_map.setdefault(
                        v_key,
                        {"visitor_short": v_key, "sessions": 0, "confirmed_sessions": 0, "accounted_cents": 0},
                    )
                    v_entry["sessions"] += 1
                    v_entry["accounted_cents"] += eff_cents
                    if confirmed:
                        v_entry["confirmed_sessions"] += 1

    cfg_map = {"decart": decart_cfg, "xmax": xmax_cfg, "reactor": reactor_cfg}
    if provider in cfg_map:
        selected_cfg = cfg_map[provider]
        daily_limit = selected_cfg["daily_cents"]
        monthly_limit = selected_cfg["monthly_cents"]
        visitor_limit = selected_cfg["visitor_daily_cents"]
        max_active = selected_cfg["max_active"]
        starts_per_minute = selected_cfg["starts_per_minute"]
        active_cfg = selected_cfg
    else:
        enabled_cfgs = [c for c in (decart_cfg, reactor_cfg, xmax_cfg) if c["enabled"]]
        if len(enabled_cfgs) == 1:
            primary = enabled_cfgs[0]
            daily_limit = primary["daily_cents"]
            monthly_limit = primary["monthly_cents"]
            visitor_limit = primary["visitor_daily_cents"]
            max_active = primary["max_active"]
            starts_per_minute = primary["starts_per_minute"]
            active_cfg = primary
        elif len(enabled_cfgs) >= 2:
            daily_limit = sum(c["daily_cents"] for c in enabled_cfgs)
            monthly_limit = sum(c["monthly_cents"] for c in enabled_cfgs)
            visitor_limit = sum(c["visitor_daily_cents"] for c in enabled_cfgs)
            max_active = sum(c["max_active"] for c in enabled_cfgs)
            starts_per_minute = sum(c["starts_per_minute"] for c in enabled_cfgs)
            active_cfg = {
                **enabled_cfgs[0],
                "ready_to_serve": any(c["ready_to_serve"] for c in enabled_cfgs),
                "blocking_reasons": [] if any(c["ready_to_serve"] for c in enabled_cfgs) else enabled_cfgs[0]["blocking_reasons"],
            }
        else:
            daily_limit = decart_cfg["daily_cents"]
            monthly_limit = decart_cfg["monthly_cents"]
            visitor_limit = decart_cfg["visitor_daily_cents"]
            max_active = decart_cfg["max_active"]
            starts_per_minute = decart_cfg["starts_per_minute"]
            active_cfg = decart_cfg

    visitors_today = sorted(
        [
            {**v, "remaining_cents": max(0, visitor_limit - v["accounted_cents"])}
            for v in visitor_map.values()
        ],
        key=lambda item: (-item["accounted_cents"], -item["sessions"]),
    )

    def _window(limit: int, accounted: int, confirmed_val: int, count: int) -> dict:
        return {
            "limit_cents": limit,
            "accounted_cents": accounted,
            "confirmed_cents": confirmed_val,
            "held_unconfirmed_cents": max(0, accounted - confirmed_val),
            "remaining_cents": max(0, limit - accounted),
            "utilization_pct": round(accounted / limit * 100, 1) if limit > 0 else 0.0,
            "session_count": count,
        }

    def _provider_summary(key: str, p_cfg: dict) -> dict:
        stats = per_provider_stats[key]
        return {
            "config": p_cfg,
            "active_sessions": stats["active_sessions"],
            "max_active": p_cfg["max_active"],
            "daily": _window(p_cfg["daily_cents"], stats["daily_accounted"], stats["daily_confirmed"], stats["daily_sessions"]),
            "monthly": _window(p_cfg["monthly_cents"], stats["monthly_accounted"], stats["monthly_confirmed"], stats["monthly_sessions"]),
        }

    return {
        "currency": "USD",
        "unit": "cent",
        "timezone": BUDGET_ZONE.key,
        "provider": provider,
        "day": day_str,
        "next_daily_reset": tomorrow.isoformat(),
        "config": active_cfg,
        "providers": {
            "decart": _provider_summary("decart", decart_cfg),
            "reactor": _provider_summary("reactor", reactor_cfg),
            "xmax": _provider_summary("xmax", xmax_cfg),
        },
        "active_sessions": active_sessions,
        "max_active": max_active,
        "starts_last_minute": starts_last_minute,
        "starts_per_minute": starts_per_minute,
        "daily": _window(daily_limit, daily_accounted, daily_confirmed, daily_sessions),
        "monthly": _window(monthly_limit, monthly_accounted, monthly_confirmed, monthly_sessions),
        "trend_14d": list(trend_map.values()),
        "reason_distribution": [
            {"reason": k, "count": v}
            for k, v in sorted(reason_counts.items(), key=lambda item: -item[1])
        ],
        "visitors_today": visitors_today,
    }


@admin_router.get("/sessions")
def list_sessions(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    provider: Literal["all", "decart", "xmax", "reactor"] = "all",
    state: Literal["all", "active", "reserved", "claimed", "ended"] = "all",
    reason: str = "",
    budget_day: str = "",
    search: str = "",
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    del admin
    now = time.time()
    q = db.query(WorkbenchRealtimeSession)
    clause = _provider_filter_clause(provider)
    if clause is not None:
        q = q.filter(clause)
    if budget_day.strip():
        q = q.filter(WorkbenchRealtimeSession.budget_day == budget_day.strip())
    if search.strip():
        pattern = f"%{search.strip()}%"
        q = q.filter(
            or_(
                WorkbenchRealtimeSession.id.ilike(pattern),
                WorkbenchRealtimeSession.visitor_hash.ilike(pattern),
                WorkbenchRealtimeSession.provider_session_id.ilike(pattern),
                WorkbenchRealtimeSession.model_id.ilike(pattern),
                WorkbenchRealtimeSession.provider_temp_key_uid.ilike(pattern),
                WorkbenchRealtimeSession.reason.ilike(pattern),
            )
        )
    if state == "active":
        q = q.filter(
            or_(
                and_(WorkbenchRealtimeSession.state == "reserved", WorkbenchRealtimeSession.claim_before > now),
                and_(WorkbenchRealtimeSession.state == "claimed", WorkbenchRealtimeSession.hold_until > now),
            )
        )
    elif state == "reserved":
        q = q.filter(WorkbenchRealtimeSession.state == "reserved", WorkbenchRealtimeSession.claim_before > now)
    elif state == "claimed":
        q = q.filter(WorkbenchRealtimeSession.state == "claimed", WorkbenchRealtimeSession.hold_until > now)
    elif state == "ended":
        q = q.filter(
            or_(
                WorkbenchRealtimeSession.state == "ended",
                and_(WorkbenchRealtimeSession.state == "reserved", WorkbenchRealtimeSession.claim_before <= now),
                and_(WorkbenchRealtimeSession.state == "claimed", WorkbenchRealtimeSession.hold_until <= now),
            )
        )

    rows = q.order_by(WorkbenchRealtimeSession.created_at.desc()).all()
    items = [_serialize_session(r, now) for r in rows]
    clean_reason = reason.strip()
    if clean_reason:
        items = [item for item in items if item.get("reason") == clean_reason]

    total = len(items)
    start_idx = (page - 1) * size
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": items[start_idx : start_idx + size],
    }


@admin_router.post("/sessions/{session_id}/stop")
async def force_stop_session(
    session_id: str,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    del admin
    row = db.get(WorkbenchRealtimeSession, session_id)
    if not row:
        raise HTTPException(404, "实时试穿会话不存在")
    now = time.time()
    eff_state, _, _, is_active = _effective_session(row, now)
    if not is_active:
        return {"ok": True, "session": _serialize_session(row, now)}

    if eff_state == "reserved":
        row.state = "ended"
        row.hold_until = 0.0
        row.accounted_cents = 0
        row.reason = "admin_stopped"
        row.ended_at = now
        row.provider_temp_key_encrypted = None
    else:
        row.stop_requested = True
        p_key = _row_provider_key(row)
        if p_key == "xmax":
            await _xmax_upstream_stop_and_settle(db, row, reason_on_confirm="admin_stopped")
        elif p_key == "reactor":
            await _reactor_upstream_stop_and_settle(db, row, reason_on_confirm="admin_stopped", stop_first=True)
    db.commit()
    db.refresh(row)
    return {"ok": True, "session": _serialize_session(row, now)}


@admin_router.post("/sessions/{session_id}/sync-usage")
async def sync_session_usage(
    session_id: str,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    del admin
    row = db.get(WorkbenchRealtimeSession, session_id)
    if not row:
        raise HTTPException(404, "实时试穿会话不存在")
    p_key = _row_provider_key(row)
    if p_key == "xmax":
        if not row.provider_temp_key_encrypted and not row.provider_session_id:
            raise HTTPException(400, "该会话缺少 Xmax 临时密钥或上游会话 ID，无法在线对账")
        settled = await _xmax_upstream_stop_and_settle(db, row, reason_on_confirm="upstream_synced")
    elif p_key == "reactor":
        if not row.provider_session_id:
            raise HTTPException(400, "该会话缺少 Reactor 上游会话 ID，无法在线对账")
        settled = await _reactor_upstream_stop_and_settle(
            db, row, reason_on_confirm="upstream_synced", stop_first=False
        )
    else:
        raise HTTPException(400, "仅 Xmax / Reactor 会话支持在线拉取上游用量对账")

    db.commit()
    db.refresh(row)
    return {
        "ok": True,
        "synced": settled,
        "session": _serialize_session(row, time.time()),
    }


@admin_router.post("/sessions/{session_id}/reconcile")
def reconcile_session(
    session_id: str,
    body: ReconcileRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    del admin
    row = db.get(WorkbenchRealtimeSession, session_id)
    if not row:
        raise HTTPException(404, "实时试穿会话不存在")
    now = time.time()
    _, _, _, is_active = _effective_session(row, now)
    if is_active:
        raise HTTPException(400, "会话仍在运行或等待连接中，请先停止后再对账结算")
    if body.confirmed_seconds is None and body.confirmed_credits is None:
        raise HTTPException(400, "请填写确认秒数或确认积分")

    p_key = _row_provider_key(row)
    if p_key in {"xmax", "reactor"}:
        default_cps = float(REACTOR_DEFAULT_CREDITS_PER_SECOND) if p_key == "reactor" else 1.0
        default_cpm = REACTOR_DEFAULT_CENTS_PER_MINUTE if p_key == "reactor" else 10
        cps = max(0.001, float(row.credits_per_second or default_cps))
        cpm = max(1, int(row.cents_per_minute or default_cpm))
        if body.confirmed_credits is not None:
            credits_val = float(body.confirmed_credits)
            seconds_val = credits_val / cps
        else:
            seconds_val = float(body.confirmed_seconds or 0.0)
            credits_val = seconds_val * cps
        max_credits_bound = float(row.max_credits or (row.limit_seconds * cps))
        if seconds_val > row.limit_seconds and credits_val > max_credits_bound:
            raise HTTPException(400, f"确认用量不能超过本次会话上限 ({row.limit_seconds} 秒 / {int(max_credits_bound)} 积分)")
        row.provider_credits = round(credits_val, 3)
        row.provider_seconds = round(seconds_val, 3)
        row.accounted_cents = _xmax_credits_to_cents(credits_val, cps, cpm)
        row.provider_temp_key_encrypted = None
    else:
        seconds_val = float(body.confirmed_seconds or 0.0)
        if seconds_val > row.limit_seconds:
            raise HTTPException(400, f"确认秒数不能超过本次会话上限 ({row.limit_seconds} 秒)")
        row.provider_seconds = round(seconds_val, 3)
        row.accounted_cents = math.ceil(seconds_val) * int(row.cents_per_second)

    row.hold_until = 0.0
    row.state = "ended"
    row.reason = "admin_reconciled"
    if not row.ended_at:
        row.ended_at = now
    if body.provider_session_id is not None and body.provider_session_id.strip():
        row.provider_session_id = body.provider_session_id.strip()

    db.commit()
    db.refresh(row)
    return {"ok": True, "session": _serialize_session(row, now)}


@admin_router.get("/reactor/balance")
async def get_reactor_balance(
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    del admin
    provider, feature = _reactor_rows(db)
    if not provider or not provider.api_key_encrypted:
        raise HTTPException(400, "请先保存 Reactor API Key")
    try:
        api_key = decrypt_secret(provider.api_key_encrypted).strip()
    except Exception:
        raise HTTPException(400, "已保存的 Reactor API Key 无法解密，请重新保存")
    if not api_key:
        raise HTTPException(400, "Reactor API Key 为空")

    cfg = _serialize_reactor_config(provider, feature)
    base_url = cfg["base_url"].rstrip("/")
    headers = _reactor_headers(api_key)
    quotas: dict = {}

    try:
        async with httpx.AsyncClient(timeout=provider.timeout_seconds or 15, follow_redirects=False) as client:
            r_me = await client.get(f"{base_url}/me", headers=headers)
            account_id = _reactor_extract_account_id(_reactor_parse_json(r_me))
            if not account_id:
                raise ValueError("Reactor /me missing account_id")
            r_credits = await client.get(f"{base_url}/accounts/{quote(account_id, safe='')}/credits", headers=headers)
            cr = _reactor_parse_json(r_credits)
            raw_bal = cr.get("balance")
            if raw_bal is None and isinstance(cr.get("credits"), (int, float)):
                raw_bal = cr.get("credits")
            if not isinstance(raw_bal, (int, float)) or isinstance(raw_bal, bool) or raw_bal < 0:
                raise ValueError("Invalid Reactor balance")
            balance = float(raw_bal)
            raw_usd = cr.get("balance_usd")
            balance_usd = (
                round(float(raw_usd), 4)
                if isinstance(raw_usd, (int, float)) and not isinstance(raw_usd, bool)
                else round(balance / 10000.0, 4)
            )
            currency_code = str(cr.get("currency_code") or "USD")
            with suppress(Exception):
                r_q = await client.get(f"{base_url}/accounts/{quote(account_id, safe='')}/quotas", headers=headers)
                quotas = _reactor_parse_json(r_q)
    except Exception as exc:
        raise HTTPException(502, sanitize_error_message(str(exc)))

    return {
        "ok": True,
        "account_id": account_id,
        "balance": balance,
        "balance_usd": balance_usd,
        "currency_code": currency_code,
        "quotas": quotas,
        "base_url": base_url,
        "checked_at": datetime.now(tz=BUDGET_ZONE).strftime("%Y-%m-%d %H:%M:%S"),
        "message": "ok",
    }


@admin_router.get("/xmax/balance")
async def get_xmax_balance(
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    del admin
    provider, feature = _xmax_rows(db)
    if not provider or not provider.api_key_encrypted:
        raise HTTPException(400, "请先保存 Xmax API Key")
    try:
        api_key = decrypt_secret(provider.api_key_encrypted).strip()
    except Exception:
        raise HTTPException(400, "已保存的 Xmax API Key 无法解密，请重新保存")
    if not api_key:
        raise HTTPException(400, "Xmax API Key 为空")

    cfg = _serialize_xmax_config(provider, feature)
    base_url = cfg["base_url"].rstrip("/")

    current_balance: float | None = None
    consumed_24h: float | None = None
    message = "ok"

    try:
        async with httpx.AsyncClient(timeout=provider.timeout_seconds or 15, follow_redirects=False) as client:
            resp = await client.get(f"{base_url}/balance", headers=_xmax_headers(api_key))
            data = _parse_xmax_envelope(resp)
            bal = data.get("currentBalance")
            if not isinstance(bal, (int, float)) or isinstance(bal, bool) or bal < 0:
                raise ValueError("Invalid currentBalance")
            current_balance = float(bal)

            now_hk = datetime.now(tz=BUDGET_ZONE)
            start_hk = now_hk - timedelta(hours=24)
            with suppress(Exception):
                r_stats = await client.get(
                    f"{base_url}/points/consume/range-stats",
                    headers=_xmax_headers(api_key),
                    params={
                        "dimension": "hour",
                        "startTimestamp": start_hk.strftime("%Y-%m-%d %H:%M:%S"),
                        "endTimestamp": now_hk.strftime("%Y-%m-%d %H:%M:%S"),
                    },
                )
                s_data = _parse_xmax_envelope(r_stats)
                s_sum = s_data.get("sum")
                if isinstance(s_sum, (int, float)) and not isinstance(s_sum, bool) and s_sum >= 0:
                    consumed_24h = float(s_sum)
    except Exception as exc:
        raise HTTPException(502, sanitize_error_message(str(exc)))

    return {
        "ok": True,
        "environment": cfg["environment"],
        "base_url": base_url,
        "current_balance": current_balance,
        "consumed_24h": consumed_24h,
        "checked_at": datetime.now(tz=BUDGET_ZONE).strftime("%Y-%m-%d %H:%M:%S"),
        "message": message,
    }
