"""Shared admission and usage accounting for realtime try-on (Decart & Xmax X2.1)."""

from __future__ import annotations

import json
import math
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from sqlalchemy import case, create_engine, func, inspect as sa_inspect, or_, select, text, update

from app.admin_runtime_config import _LOCAL_ADMIN_DB, _decrypt_secret, _encrypt_secret
from app.task_db import WorkbenchRealtimeSession as SessionRecord
from app.task_db import get_session_factory, is_production_env
from app import reactor_client
from app.xmax_client import (
    XMAX_MODELS,
    normalize_camera_preset,
    normalize_environment,
    normalize_model,
    resolve_base_url,
    supported_models_for_environment,
)

MODEL = "lucy-vton-3.6"
MIN_SECONDS = 10  # Decart's minimum token session cap.
TICKET_SECONDS = 15
SETUP_SECONDS = 8
CLOSE_SECONDS = 3

XMAX_MIN_SECONDS = 10
XMAX_MAX_SECONDS_CAP = 120
XMAX_SETUP_SECONDS = 25

REACTOR_MIN_SECONDS = 10
REACTOR_MAX_SECONDS_CAP = 120
REACTOR_SETUP_SECONDS = 30

BUDGET_ZONE = ZoneInfo("Asia/Hong_Kong")
_DB_CACHE_TTL_SECONDS = 15.0

_db_cache_lock = threading.Lock()
_db_cache: Settings | None = None
_db_cache_at: float = 0.0
_db_cache_key: tuple[str, str, str, str] | None = None

_xmax_db_cache: XmaxSettings | None = None
_xmax_db_cache_at: float = 0.0
_xmax_db_cache_key: tuple[str, str, str, str, str] | None = None

_reactor_db_cache: ReactorSettings | None = None
_reactor_db_cache_at: float = 0.0
_reactor_db_cache_key: tuple[str, str, str, str, str, str] | None = None

_cfg_engines: dict[str, object] = {}


@dataclass(frozen=True)
class Settings:
    enabled: bool
    api_key: str = field(repr=False)
    access_code: str = field(repr=False)
    origin: str
    max_seconds: int
    cents_per_second: int
    daily_cents: int
    monthly_cents: int
    visitor_daily_cents: int
    max_active: int
    starts_per_minute: int
    require_access_code: bool = True
    default_seconds: int = 15
    default_prompt: str = ""
    source: str = "environment"

    @property
    def available(self):
        if not self.enabled or not self.api_key:
            return False
        if self.require_access_code and not (16 <= len(self.access_code) <= 256):
            return False
        return True


@dataclass(frozen=True)
class XmaxSettings:
    enabled: bool
    api_key: str = field(repr=False)
    access_code: str = field(repr=False)
    environment: str
    base_url: str
    default_model: str
    allowed_models: tuple[str, ...]
    camera_preset: str
    face_restoration: bool
    origin: str
    min_seconds: int
    max_seconds: int
    default_seconds: int
    credits_per_second: int
    cents_per_minute: int
    daily_cents: int
    monthly_cents: int
    visitor_daily_cents: int
    min_account_credits: int
    max_active: int
    starts_per_minute: int
    require_access_code: bool = True
    default_prompt: str = ""
    source: str = "environment"

    @property
    def available(self) -> bool:
        if not self.enabled or not self.api_key:
            return False
        if self.require_access_code and not (16 <= len(self.access_code) <= 256):
            return False
        return True


@dataclass(frozen=True)
class ReactorSettings:
    enabled: bool
    api_key: str = field(repr=False)
    access_code: str = field(repr=False)
    base_url: str
    default_model: str
    allowed_models: tuple[str, ...]
    origin: str
    min_seconds: int
    max_seconds: int
    default_seconds: int
    credits_per_second: int
    cents_per_minute: int
    daily_cents: int
    monthly_cents: int
    visitor_daily_cents: int
    min_account_credits: int
    max_active: int
    starts_per_minute: int
    require_access_code: bool = True
    default_prompt: str = ""
    source: str = "environment"

    @property
    def available(self) -> bool:
        if not self.enabled or not self.api_key:
            return False
        if self.require_access_code and not (16 <= len(self.access_code) <= 256):
            return False
        return True


def clear_settings_cache() -> None:
    global _db_cache, _db_cache_at, _db_cache_key
    global _xmax_db_cache, _xmax_db_cache_at, _xmax_db_cache_key
    global _reactor_db_cache, _reactor_db_cache_at, _reactor_db_cache_key
    with _db_cache_lock:
        _db_cache = None
        _db_cache_at = 0.0
        _db_cache_key = None
        _xmax_db_cache = None
        _xmax_db_cache_at = 0.0
        _xmax_db_cache_key = None
        _reactor_db_cache = None
        _reactor_db_cache_at = 0.0
        _reactor_db_cache_key = None


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


def _resolve_origin(configured_origin: str = "", *, provider: str = "decart") -> str:
    if provider == "reactor":
        candidates = (
            str(configured_origin or "").strip(),
            os.getenv("REACTOR_REALTIME_ORIGIN", "").strip(),
            os.getenv("WORKBENCH_PUBLIC_URL", "").strip(),
            os.getenv("XMAX_REALTIME_ORIGIN", "").strip(),
            os.getenv("DECART_REALTIME_ORIGIN", "").strip(),
            os.getenv("ROUTER01_MEDIA_BASE_URL", "").strip(),
        )
    elif provider == "xmax":
        candidates = (
            str(configured_origin or "").strip(),
            os.getenv("XMAX_REALTIME_ORIGIN", "").strip(),
            os.getenv("WORKBENCH_PUBLIC_URL", "").strip(),
            os.getenv("DECART_REALTIME_ORIGIN", "").strip(),
            os.getenv("ROUTER01_MEDIA_BASE_URL", "").strip(),
        )
    else:
        candidates = (
            str(configured_origin or "").strip(),
            os.getenv("DECART_REALTIME_ORIGIN", "").strip(),
            os.getenv("WORKBENCH_PUBLIC_URL", "").strip(),
            os.getenv("ROUTER01_MEDIA_BASE_URL", "").strip(),
        )
    origin = next((c for c in candidates if c), "").rstrip("/")
    if origin:
        url = urlsplit(origin)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.path
            or url.query
            or url.fragment
            or url.username
            or url.password
        ):
            raise ValueError(f"Invalid {provider} realtime origin")
    return origin


def _resolve_config_db_url() -> str | None:
    for env_name in ("AI_CONFIG_DATABASE_URL", "DATABASE_URL", "TASK_DATABASE_URL"):
        raw = os.getenv(env_name, "").strip()
        if raw:
            if raw.startswith("postgres://"):
                return "postgresql+psycopg://" + raw[len("postgres://"):]
            if raw.startswith("postgresql://") and "+psycopg" not in raw:
                return "postgresql+psycopg://" + raw[len("postgresql://"):]
            return raw
    if not is_production_env() and _LOCAL_ADMIN_DB.exists():
        return f"sqlite:///{_LOCAL_ADMIN_DB.as_posix()}"
    return None


def _get_config_engine(url: str):
    with _db_cache_lock:
        engine = _cfg_engines.get(url)
        if engine is None:
            connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
            engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
            _cfg_engines[url] = engine
        return engine


def _parse_json_dict(raw) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    return dict(raw) if isinstance(raw, dict) else {}


def _parse_allowed_models(
    raw_allowed,
    default_model: str,
    *,
    environment: str | None = None,
) -> tuple[str, ...]:
    supported = supported_models_for_environment(environment) if environment is not None else XMAX_MODELS
    items: list[str] = []
    if isinstance(raw_allowed, str):
        raw_allowed = [part.strip() for part in raw_allowed.split(",") if part.strip()]
    if isinstance(raw_allowed, (list, tuple)):
        for item in raw_allowed:
            clean = str(item or "").strip().lower()
            if clean in supported and clean not in items:
                items.append(clean)
    safe_default = normalize_model(default_model, environment=environment)
    if safe_default not in items:
        items.insert(0, safe_default)
    return tuple(items or [safe_default])


def _read_db_settings() -> Settings | None:
    global _db_cache, _db_cache_at, _db_cache_key
    db_url = _resolve_config_db_url()
    if not db_url:
        return None
    cache_key = (
        db_url,
        os.getenv("DECART_REALTIME_ORIGIN", "").strip(),
        os.getenv("WORKBENCH_PUBLIC_URL", "").strip(),
        os.getenv("ROUTER01_MEDIA_BASE_URL", "").strip(),
    )
    now_mono = time.monotonic()
    with _db_cache_lock:
        if (
            _db_cache is not None
            and _db_cache_key == cache_key
            and (now_mono - _db_cache_at) < _DB_CACHE_TTL_SECONDS
        ):
            return _db_cache

    try:
        engine = _get_config_engine(db_url)
        inspector = sa_inspect(engine)
        if not (inspector.has_table("ai_api_providers") and inspector.has_table("ai_feature_configs")):
            return None
        with engine.connect() as conn:
            provider = conn.execute(
                text("SELECT enabled, api_key_encrypted FROM ai_api_providers WHERE provider_key = 'decart'")
            ).mappings().first()
            feature = conn.execute(
                text("SELECT enabled, config FROM ai_feature_configs WHERE feature_key = 'tryon_realtime'")
            ).mappings().first()
    except Exception:
        return None

    if provider is None and feature is None:
        return None

    raw_cfg = _parse_json_dict((feature or {}).get("config"))
    enabled = bool(provider and provider["enabled"] and feature and feature["enabled"])
    api_key = ""
    if provider and provider.get("api_key_encrypted"):
        try:
            api_key = _decrypt_secret(provider["api_key_encrypted"]).strip()
        except Exception:
            enabled = False

    access_code = ""
    if raw_cfg.get("access_code_encrypted"):
        try:
            access_code = _decrypt_secret(str(raw_cfg["access_code_encrypted"])).strip()
        except Exception:
            enabled = False

    max_seconds = _clamp_int(raw_cfg.get("max_seconds"), 20, MIN_SECONDS, 60)
    default_seconds = _clamp_int(raw_cfg.get("default_seconds"), min(15, max_seconds), MIN_SECONDS, max_seconds)
    require_access_code = bool(raw_cfg.get("require_access_code", True))
    origin = _resolve_origin(str(raw_cfg.get("origin") or ""), provider="decart")
    if enabled and is_production_env() and not origin.startswith("https://"):
        raise ValueError("Decart realtime requires a public HTTPS origin in production")

    loaded = Settings(
        enabled=enabled,
        api_key=api_key,
        access_code=access_code,
        origin=origin,
        max_seconds=max_seconds,
        cents_per_second=_clamp_int(raw_cfg.get("cents_per_second"), 2, 2, 1000),
        daily_cents=_clamp_int(raw_cfg.get("daily_cents"), 200, 0, 10_000_000),
        monthly_cents=_clamp_int(raw_cfg.get("monthly_cents"), 1000, 0, 10_000_000),
        visitor_daily_cents=_clamp_int(raw_cfg.get("visitor_daily_cents"), 80, 0, 10_000_000),
        max_active=_clamp_int(raw_cfg.get("max_active"), 1, 1, 5),
        starts_per_minute=_clamp_int(raw_cfg.get("starts_per_minute"), 3, 1, 30),
        require_access_code=require_access_code,
        default_seconds=default_seconds,
        default_prompt=str(raw_cfg.get("default_prompt") or "").strip()[:280],
        source="admin_db",
    )
    with _db_cache_lock:
        _db_cache = loaded
        _db_cache_at = now_mono
        _db_cache_key = cache_key
    return loaded


def load_settings():
    db_settings = _read_db_settings()
    if db_settings is not None:
        return db_settings

    def integer(name, default, minimum, maximum):
        value = int(os.getenv("DECART_REALTIME_" + name, str(default)))
        if not minimum <= value <= maximum:
            raise ValueError("Invalid Decart realtime setting: " + name)
        return value

    enabled = os.getenv("DECART_REALTIME_ENABLED", "").strip().lower() in {"1", "true", "yes"}
    origin = _resolve_origin(provider="decart")
    if enabled and is_production_env() and not origin.startswith("https://"):
        raise ValueError("Decart realtime requires a public HTTPS origin in production")
    max_seconds = integer("MAX_SECONDS", 20, MIN_SECONDS, 60)
    default_seconds = integer("DEFAULT_SECONDS", min(15, max_seconds), MIN_SECONDS, max_seconds)
    require_access_code = os.getenv("DECART_REALTIME_REQUIRE_ACCESS_CODE", "true").strip().lower() not in {"0", "false", "no"}
    return Settings(
        enabled=enabled,
        api_key=os.getenv("DECART_API_KEY", "").strip(),
        access_code=os.getenv("DECART_REALTIME_ACCESS_CODE", "").strip(),
        origin=origin,
        max_seconds=max_seconds,
        cents_per_second=integer("CENTS_PER_SECOND", 2, 2, 1000),
        daily_cents=integer("DAILY_CENTS", 200, 0, 10_000_000),
        monthly_cents=integer("MONTHLY_CENTS", 1000, 0, 10_000_000),
        visitor_daily_cents=integer("VISITOR_DAILY_CENTS", 80, 0, 10_000_000),
        max_active=integer("MAX_ACTIVE", 1, 1, 5),
        starts_per_minute=integer("STARTS_PER_MINUTE", 3, 1, 30),
        require_access_code=require_access_code,
        default_seconds=default_seconds,
        default_prompt=os.getenv("DECART_REALTIME_DEFAULT_PROMPT", "").strip()[:280],
        source="environment",
    )


def _read_xmax_db_settings() -> XmaxSettings | None:
    global _xmax_db_cache, _xmax_db_cache_at, _xmax_db_cache_key
    db_url = _resolve_config_db_url()
    if not db_url:
        return None
    cache_key = (
        db_url,
        os.getenv("XMAX_REALTIME_ORIGIN", "").strip(),
        os.getenv("WORKBENCH_PUBLIC_URL", "").strip(),
        os.getenv("DECART_REALTIME_ORIGIN", "").strip(),
        os.getenv("ROUTER01_MEDIA_BASE_URL", "").strip(),
    )
    now_mono = time.monotonic()
    with _db_cache_lock:
        if (
            _xmax_db_cache is not None
            and _xmax_db_cache_key == cache_key
            and (now_mono - _xmax_db_cache_at) < _DB_CACHE_TTL_SECONDS
        ):
            return _xmax_db_cache

    try:
        engine = _get_config_engine(db_url)
        inspector = sa_inspect(engine)
        if not (inspector.has_table("ai_api_providers") and inspector.has_table("ai_feature_configs")):
            return None
        with engine.connect() as conn:
            provider = conn.execute(
                text(
                    "SELECT enabled, base_url, default_model, api_key_encrypted "
                    "FROM ai_api_providers WHERE provider_key = 'xmax'"
                )
            ).mappings().first()
            feature = conn.execute(
                text(
                    "SELECT enabled, default_model, config "
                    "FROM ai_feature_configs WHERE feature_key = 'tryon_realtime_xmax'"
                )
            ).mappings().first()
    except Exception:
        return None

    if provider is None and feature is None:
        return None

    raw_cfg = _parse_json_dict((feature or {}).get("config"))
    enabled = bool(provider and provider["enabled"] and feature and feature["enabled"])
    api_key = ""
    if provider and provider.get("api_key_encrypted"):
        try:
            api_key = _decrypt_secret(provider["api_key_encrypted"]).strip()
        except Exception:
            enabled = False

    access_code = ""
    if raw_cfg.get("access_code_encrypted"):
        try:
            access_code = _decrypt_secret(str(raw_cfg["access_code_encrypted"])).strip()
        except Exception:
            enabled = False

    environment = normalize_environment(str(raw_cfg.get("environment") or "global"))
    base_url = resolve_base_url(environment, str((provider or {}).get("base_url") or ""))
    default_model = normalize_model(
        str((feature or {}).get("default_model") or (provider or {}).get("default_model") or "x2.1"),
        environment=environment,
    )
    allowed_models = _parse_allowed_models(
        raw_cfg.get("allowed_models"),
        default_model,
        environment=environment,
    )
    camera_preset = normalize_camera_preset(default_model, str(raw_cfg.get("camera_preset") or ""))
    face_restoration = _bool_value(raw_cfg.get("face_restoration"), True)

    min_seconds = _clamp_int(raw_cfg.get("min_seconds"), XMAX_MIN_SECONDS, XMAX_MIN_SECONDS, 60)
    max_seconds = _clamp_int(raw_cfg.get("max_seconds"), 60, min_seconds, XMAX_MAX_SECONDS_CAP)
    default_seconds = _clamp_int(raw_cfg.get("default_seconds"), min(30, max_seconds), min_seconds, max_seconds)
    require_access_code = _bool_value(raw_cfg.get("require_access_code"), True)
    origin = _resolve_origin(str(raw_cfg.get("origin") or ""), provider="xmax")
    if enabled and is_production_env() and not origin.startswith("https://"):
        raise ValueError("Xmax realtime requires a public HTTPS origin in production")

    loaded = XmaxSettings(
        enabled=enabled,
        api_key=api_key,
        access_code=access_code,
        environment=environment,
        base_url=base_url,
        default_model=default_model,
        allowed_models=allowed_models,
        camera_preset=camera_preset,
        face_restoration=face_restoration,
        origin=origin,
        min_seconds=min_seconds,
        max_seconds=max_seconds,
        default_seconds=default_seconds,
        credits_per_second=_clamp_int(raw_cfg.get("credits_per_second"), 1, 1, 100),
        cents_per_minute=_clamp_int(raw_cfg.get("cents_per_minute"), 10, 1, 10_000),
        daily_cents=_clamp_int(raw_cfg.get("daily_cents"), 200, 0, 10_000_000),
        monthly_cents=_clamp_int(raw_cfg.get("monthly_cents"), 1000, 0, 10_000_000),
        visitor_daily_cents=_clamp_int(raw_cfg.get("visitor_daily_cents"), 50, 0, 10_000_000),
        min_account_credits=_clamp_int(raw_cfg.get("min_account_credits"), 60, 0, 10_000_000),
        max_active=_clamp_int(raw_cfg.get("max_active"), 1, 1, 5),
        starts_per_minute=_clamp_int(raw_cfg.get("starts_per_minute"), 3, 1, 30),
        require_access_code=require_access_code,
        default_prompt=str(raw_cfg.get("default_prompt") or "").strip()[:280],
        source="admin_db",
    )
    with _db_cache_lock:
        _xmax_db_cache = loaded
        _xmax_db_cache_at = now_mono
        _xmax_db_cache_key = cache_key
    return loaded


def load_xmax_settings() -> XmaxSettings:
    db_settings = _read_xmax_db_settings()
    if db_settings is not None:
        return db_settings

    def integer(name, default, minimum, maximum):
        value = int(os.getenv("XMAX_REALTIME_" + name, str(default)))
        if not minimum <= value <= maximum:
            raise ValueError("Invalid Xmax realtime setting: " + name)
        return value

    enabled = os.getenv("XMAX_REALTIME_ENABLED", "").strip().lower() in {"1", "true", "yes"}
    origin = _resolve_origin(provider="xmax")
    if enabled and is_production_env() and not origin.startswith("https://"):
        raise ValueError("Xmax realtime requires a public HTTPS origin in production")

    environment = normalize_environment(os.getenv("XMAX_REALTIME_ENVIRONMENT", "global"))
    base_url = resolve_base_url(environment, os.getenv("XMAX_REALTIME_BASE_URL", ""))
    default_model = normalize_model(os.getenv("XMAX_REALTIME_MODEL", "x2.1"), environment=environment)
    allowed_models = _parse_allowed_models(
        os.getenv("XMAX_REALTIME_ALLOWED_MODELS", "x2.1,x2.1-flash"),
        default_model,
        environment=environment,
    )
    camera_preset = normalize_camera_preset(default_model, os.getenv("XMAX_REALTIME_CAMERA_PRESET", ""))
    face_restoration = _bool_value(os.getenv("XMAX_REALTIME_FACE_RESTORATION", "true"), True)

    min_seconds = integer("MIN_SECONDS", XMAX_MIN_SECONDS, XMAX_MIN_SECONDS, 60)
    max_seconds = integer("MAX_SECONDS", 60, min_seconds, XMAX_MAX_SECONDS_CAP)
    default_seconds = integer("DEFAULT_SECONDS", min(30, max_seconds), min_seconds, max_seconds)
    require_access_code = os.getenv("XMAX_REALTIME_REQUIRE_ACCESS_CODE", "true").strip().lower() not in {"0", "false", "no"}

    return XmaxSettings(
        enabled=enabled,
        api_key=os.getenv("XMAX_API_KEY", "").strip(),
        access_code=os.getenv("XMAX_REALTIME_ACCESS_CODE", "").strip(),
        environment=environment,
        base_url=base_url,
        default_model=default_model,
        allowed_models=allowed_models,
        camera_preset=camera_preset,
        face_restoration=face_restoration,
        origin=origin,
        min_seconds=min_seconds,
        max_seconds=max_seconds,
        default_seconds=default_seconds,
        credits_per_second=integer("CREDITS_PER_SECOND", 1, 1, 100),
        cents_per_minute=integer("CENTS_PER_MINUTE", 10, 1, 10_000),
        daily_cents=integer("DAILY_CENTS", 200, 0, 10_000_000),
        monthly_cents=integer("MONTHLY_CENTS", 1000, 0, 10_000_000),
        visitor_daily_cents=integer("VISITOR_DAILY_CENTS", 50, 0, 10_000_000),
        min_account_credits=integer("MIN_ACCOUNT_CREDITS", 60, 0, 10_000_000),
        max_active=integer("MAX_ACTIVE", 1, 1, 5),
        starts_per_minute=integer("STARTS_PER_MINUTE", 3, 1, 30),
        require_access_code=require_access_code,
        default_prompt=os.getenv(
            "XMAX_REALTIME_DEFAULT_PROMPT",
            "将参考图的服装穿戴到视频角色身上，跟随角色原有动作。",
        ).strip()[:280],
        source="environment",
    )


def xmax_session_cents(seconds: int, cents_per_minute: int) -> int:
    if seconds <= 0:
        return 0
    return max(1, math.ceil(int(seconds) * max(1, int(cents_per_minute)) / 60))


def xmax_credits_to_cents(credits: float, credits_per_second: float, cents_per_minute: int) -> int:
    if credits <= 0:
        return 0
    cps = max(0.001, float(credits_per_second or 1.0))
    return max(1, math.ceil((float(credits) / cps) * max(1, int(cents_per_minute)) / 60))


def _parse_reactor_allowed_models(raw_allowed, default_model: str) -> tuple[str, ...]:
    items: list[str] = []
    if isinstance(raw_allowed, str):
        raw_allowed = [part.strip() for part in raw_allowed.split(",") if part.strip()]
    if isinstance(raw_allowed, (list, tuple)):
        for item in raw_allowed:
            raw_text = str(item or "").strip().lower()
            if not raw_text:
                continue
            if raw_text in reactor_client.REACTOR_MODEL_ALIASES:
                normalized = reactor_client.normalize_model(raw_text, default=default_model)
                if normalized not in items:
                    items.append(normalized)
    if default_model not in items:
        items.insert(0, default_model)
    return tuple(items or [default_model])


def _read_reactor_db_settings() -> ReactorSettings | None:
    global _reactor_db_cache, _reactor_db_cache_at, _reactor_db_cache_key
    db_url = _resolve_config_db_url()
    if not db_url:
        return None
    cache_key = (
        db_url,
        os.getenv("REACTOR_REALTIME_ORIGIN", "").strip(),
        os.getenv("WORKBENCH_PUBLIC_URL", "").strip(),
        os.getenv("XMAX_REALTIME_ORIGIN", "").strip(),
        os.getenv("DECART_REALTIME_ORIGIN", "").strip(),
        os.getenv("ROUTER01_MEDIA_BASE_URL", "").strip(),
    )
    now_mono = time.monotonic()
    with _db_cache_lock:
        if (
            _reactor_db_cache is not None
            and _reactor_db_cache_key == cache_key
            and (now_mono - _reactor_db_cache_at) < _DB_CACHE_TTL_SECONDS
        ):
            return _reactor_db_cache

    try:
        engine = _get_config_engine(db_url)
        inspector = sa_inspect(engine)
        if not (inspector.has_table("ai_api_providers") and inspector.has_table("ai_feature_configs")):
            return None
        with engine.connect() as conn:
            provider = conn.execute(
                text(
                    "SELECT enabled, base_url, default_model, api_key_encrypted "
                    "FROM ai_api_providers WHERE provider_key = 'reactor'"
                )
            ).mappings().first()
            feature = conn.execute(
                text(
                    "SELECT enabled, default_model, config "
                    "FROM ai_feature_configs WHERE feature_key = 'tryon_realtime_reactor'"
                )
            ).mappings().first()
    except Exception:
        return None

    if provider is None and feature is None:
        return None

    raw_cfg = _parse_json_dict((feature or {}).get("config"))
    enabled = bool(provider and provider["enabled"] and feature and feature["enabled"])
    api_key = ""
    if provider and provider.get("api_key_encrypted"):
        try:
            api_key = _decrypt_secret(provider["api_key_encrypted"]).strip()
        except Exception:
            enabled = False

    access_code = ""
    if raw_cfg.get("access_code_encrypted"):
        try:
            access_code = _decrypt_secret(str(raw_cfg["access_code_encrypted"])).strip()
        except Exception:
            enabled = False

    base_url = reactor_client.resolve_base_url(str((provider or {}).get("base_url") or ""))
    default_model = reactor_client.normalize_model(
        str((feature or {}).get("default_model") or (provider or {}).get("default_model") or reactor_client.REACTOR_DEFAULT_MODEL)
    )
    allowed_models = _parse_reactor_allowed_models(raw_cfg.get("allowed_models"), default_model)

    min_seconds = _clamp_int(raw_cfg.get("min_seconds"), REACTOR_MIN_SECONDS, REACTOR_MIN_SECONDS, 60)
    max_seconds = _clamp_int(raw_cfg.get("max_seconds"), 60, min_seconds, REACTOR_MAX_SECONDS_CAP)
    default_seconds = _clamp_int(raw_cfg.get("default_seconds"), min(30, max_seconds), min_seconds, max_seconds)
    require_access_code = _bool_value(raw_cfg.get("require_access_code"), True)
    origin = _resolve_origin(str(raw_cfg.get("origin") or ""), provider="reactor")
    if enabled and is_production_env() and not origin.startswith("https://"):
        raise ValueError("Reactor realtime requires a public HTTPS origin in production")

    loaded = ReactorSettings(
        enabled=enabled,
        api_key=api_key,
        access_code=access_code,
        base_url=base_url,
        default_model=default_model,
        allowed_models=allowed_models,
        origin=origin,
        min_seconds=min_seconds,
        max_seconds=max_seconds,
        default_seconds=default_seconds,
        credits_per_second=_clamp_int(raw_cfg.get("credits_per_second"), reactor_client.REACTOR_DEFAULT_CREDITS_PER_SECOND, 1, 10000),
        cents_per_minute=_clamp_int(raw_cfg.get("cents_per_minute"), reactor_client.REACTOR_DEFAULT_CENTS_PER_MINUTE, 1, 10_000),
        daily_cents=_clamp_int(raw_cfg.get("daily_cents"), 200, 0, 10_000_000),
        monthly_cents=_clamp_int(raw_cfg.get("monthly_cents"), 1000, 0, 10_000_000),
        visitor_daily_cents=_clamp_int(raw_cfg.get("visitor_daily_cents"), 50, 0, 10_000_000),
        min_account_credits=_clamp_int(raw_cfg.get("min_account_credits"), 1000, 0, 10_000_000),
        max_active=_clamp_int(raw_cfg.get("max_active"), 1, 1, 5),
        starts_per_minute=_clamp_int(raw_cfg.get("starts_per_minute"), 3, 1, 30),
        require_access_code=require_access_code,
        default_prompt=str(raw_cfg.get("default_prompt") or "").strip()[:280],
        source="admin_db",
    )
    with _db_cache_lock:
        _reactor_db_cache = loaded
        _reactor_db_cache_at = now_mono
        _reactor_db_cache_key = cache_key
    return loaded


def load_reactor_settings() -> ReactorSettings:
    db_settings = _read_reactor_db_settings()
    if db_settings is not None:
        return db_settings

    def integer(name, default, minimum, maximum):
        value = int(os.getenv("REACTOR_REALTIME_" + name, str(default)))
        if not minimum <= value <= maximum:
            raise ValueError("Invalid Reactor realtime setting: " + name)
        return value

    enabled = os.getenv("REACTOR_REALTIME_ENABLED", "").strip().lower() in {"1", "true", "yes"}
    origin = _resolve_origin(provider="reactor")
    if enabled and is_production_env() and not origin.startswith("https://"):
        raise ValueError("Reactor realtime requires a public HTTPS origin in production")

    base_url = reactor_client.resolve_base_url(os.getenv("REACTOR_REALTIME_BASE_URL", ""))
    default_model = reactor_client.normalize_model(os.getenv("REACTOR_REALTIME_MODEL", reactor_client.REACTOR_DEFAULT_MODEL))
    allowed_models = _parse_reactor_allowed_models(
        os.getenv("REACTOR_REALTIME_ALLOWED_MODELS", "reactor/xmax-x2-1,xmax/x2"),
        default_model,
    )
    min_seconds = integer("MIN_SECONDS", REACTOR_MIN_SECONDS, REACTOR_MIN_SECONDS, 60)
    max_seconds = integer("MAX_SECONDS", 60, min_seconds, REACTOR_MAX_SECONDS_CAP)
    default_seconds = integer("DEFAULT_SECONDS", min(30, max_seconds), min_seconds, max_seconds)
    require_access_code = os.getenv("REACTOR_REALTIME_REQUIRE_ACCESS_CODE", "true").strip().lower() not in {"0", "false", "no"}

    return ReactorSettings(
        enabled=enabled,
        api_key=os.getenv("REACTOR_API_KEY", "").strip(),
        access_code=os.getenv("REACTOR_REALTIME_ACCESS_CODE", "").strip(),
        base_url=base_url,
        default_model=default_model,
        allowed_models=allowed_models,
        origin=origin,
        min_seconds=min_seconds,
        max_seconds=max_seconds,
        default_seconds=default_seconds,
        credits_per_second=integer("CREDITS_PER_SECOND", reactor_client.REACTOR_DEFAULT_CREDITS_PER_SECOND, 1, 10000),
        cents_per_minute=integer("CENTS_PER_MINUTE", reactor_client.REACTOR_DEFAULT_CENTS_PER_MINUTE, 1, 10_000),
        daily_cents=integer("DAILY_CENTS", 200, 0, 10_000_000),
        monthly_cents=integer("MONTHLY_CENTS", 1000, 0, 10_000_000),
        visitor_daily_cents=integer("VISITOR_DAILY_CENTS", 50, 0, 10_000_000),
        min_account_credits=integer("MIN_ACCOUNT_CREDITS", 1000, 0, 10_000_000),
        max_active=integer("MAX_ACTIVE", 1, 1, 5),
        starts_per_minute=integer("STARTS_PER_MINUTE", 3, 1, 30),
        require_access_code=require_access_code,
        default_prompt=os.getenv(
            "REACTOR_REALTIME_DEFAULT_PROMPT",
            "视频中人物衣服替换成参考图中衣服，保持人物面部与动作自然连贯。",
        ).strip()[:280],
        source="environment",
    )


def reactor_session_cents(seconds: int, cents_per_minute: int) -> int:
    if seconds <= 0:
        return 0
    return max(1, math.ceil(int(seconds) * max(1, int(cents_per_minute)) / 60))


def reactor_seconds_to_cents(seconds: float, cents_per_minute: int) -> int:
    if seconds <= 0:
        return 0
    return max(1, math.ceil(float(seconds) * max(1, int(cents_per_minute)) / 60))


class BudgetDenied(Exception):
    pass


def _calendar(now):
    local = datetime.fromtimestamp(now, BUDGET_ZONE)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return local.date().isoformat(), local.date().replace(day=1).isoformat(), midnight + timedelta(days=1)


def _totals(db, now, visitor="", provider_key="decart"):
    day, month, _ = _calendar(now)
    today = SessionRecord.budget_day == day
    owned = SessionRecord.visitor_hash == visitor
    confirmed = or_(
        SessionRecord.provider_seconds.is_not(None),
        SessionRecord.provider_credits.is_not(None),
    )
    cents = SessionRecord.accounted_cents
    return db.execute(select(
        func.coalesce(func.sum(cents), 0).label("month"),
        func.coalesce(func.sum(case((today, cents), else_=0)), 0).label("day"),
        func.coalesce(func.sum(case((today & owned, cents), else_=0)), 0).label("visitor"),
        func.coalesce(func.sum(case((confirmed, cents), else_=0)), 0).label("confirmed_month"),
        func.coalesce(func.sum(case((today & confirmed, cents), else_=0)), 0).label("confirmed_day"),
    ).where(
        SessionRecord.provider_key == provider_key,
        SessionRecord.budget_day >= month,
        SessionRecord.budget_day <= day,
        or_(SessionRecord.state != "reserved", SessionRecord.claim_before > now),
    )).one()


def _lock_admissions(db, engine):
    if engine.dialect.name == "sqlite" and not is_production_env():
        db.execute(text("BEGIN IMMEDIATE"))
    elif engine.dialect.name == "postgresql":
        # Serialize admissions across workers and replicas with the same ledger.
        db.execute(text("SELECT pg_advisory_xact_lock(553119843042)"))
    else:
        raise RuntimeError("Realtime try-on needs PostgreSQL in production or SQLite in development")


def reserve(settings, visitor, seconds, *, now=None):
    if not MIN_SECONDS <= seconds <= settings.max_seconds:
        raise BudgetDenied("invalid_duration")
    sessions, engine = get_session_factory()
    with sessions.begin() as db:
        _lock_admissions(db, engine)
        now = time.time() if now is None else now
        day, _, tomorrow = _calendar(now)
        if now + TICKET_SECONDS + SETUP_SECONDS + seconds + CLOSE_SECONDS >= tomorrow.timestamp():
            raise BudgetDenied("budget_reset")
        starts = db.scalar(
            select(func.count())
            .select_from(SessionRecord)
            .where(SessionRecord.provider_key == "decart", SessionRecord.created_at > now - 60)
        )
        if starts >= settings.starts_per_minute:
            raise BudgetDenied("rate_limit")
        active = db.scalar(
            select(func.count())
            .select_from(SessionRecord)
            .where(SessionRecord.provider_key == "decart", SessionRecord.hold_until > now)
        ) or 0
        own = db.scalar(
            select(func.count())
            .select_from(SessionRecord)
            .where(SessionRecord.visitor_hash == visitor, SessionRecord.hold_until > now)
        ) or 0
        if own or active >= settings.max_active:
            raise BudgetDenied("visitor_busy" if own else "busy")
        totals = _totals(db, now, visitor, provider_key="decart")
        cents = seconds * settings.cents_per_second
        for code, spent, cap in (
            ("daily_budget", totals.day, settings.daily_cents),
            ("monthly_budget", totals.month, settings.monthly_cents),
            ("visitor_budget", totals.visitor, settings.visitor_daily_cents),
        ):
            if spent + cents > cap:
                raise BudgetDenied(code)
        row = SessionRecord(
            id=uuid.uuid4().hex,
            provider_key="decart",
            model_id=MODEL,
            visitor_hash=visitor,
            budget_day=day,
            created_at=now,
            claim_before=now + TICKET_SECONDS,
            hold_until=now + TICKET_SECONDS,
            state="reserved",
            limit_seconds=seconds,
            cents_per_second=settings.cents_per_second,
            cents_per_minute=settings.cents_per_second * 60,
            accounted_cents=cents,
        )
        db.add(row)
    return row


def _reserve_subcent_provider(
    *,
    provider_key: str,
    chosen_model: str,
    seconds: int,
    setup_seconds: int,
    starts_per_minute: int,
    max_active: int,
    cents_per_minute: int,
    credits_per_second: int,
    daily_cents: int,
    monthly_cents: int,
    visitor_daily_cents: int,
    visitor: str,
    now=None,
):
    sessions, engine = get_session_factory()
    with sessions.begin() as db:
        _lock_admissions(db, engine)
        now = time.time() if now is None else now
        day, _, tomorrow = _calendar(now)
        if now + TICKET_SECONDS + setup_seconds + seconds + CLOSE_SECONDS >= tomorrow.timestamp():
            raise BudgetDenied("budget_reset")
        starts = db.scalar(
            select(func.count())
            .select_from(SessionRecord)
            .where(SessionRecord.provider_key == provider_key, SessionRecord.created_at > now - 60)
        )
        if starts >= starts_per_minute:
            raise BudgetDenied("rate_limit")
        active = db.scalar(
            select(func.count())
            .select_from(SessionRecord)
            .where(SessionRecord.provider_key == provider_key, SessionRecord.hold_until > now)
        ) or 0
        own = db.scalar(
            select(func.count())
            .select_from(SessionRecord)
            .where(SessionRecord.visitor_hash == visitor, SessionRecord.hold_until > now)
        ) or 0
        if own or active >= max_active:
            raise BudgetDenied("visitor_busy" if own else "busy")

        totals = _totals(db, now, visitor, provider_key=provider_key)
        cents = xmax_session_cents(seconds, cents_per_minute)
        max_credits = int(math.ceil(seconds * credits_per_second))
        for code, spent, cap in (
            ("daily_budget", totals.day, daily_cents),
            ("monthly_budget", totals.month, monthly_cents),
            ("visitor_budget", totals.visitor, visitor_daily_cents),
        ):
            if spent + cents > cap:
                raise BudgetDenied(code)

        row = SessionRecord(
            id=uuid.uuid4().hex,
            provider_key=provider_key,
            model_id=chosen_model,
            visitor_hash=visitor,
            budget_day=day,
            created_at=now,
            claim_before=now + TICKET_SECONDS,
            hold_until=now + TICKET_SECONDS,
            state="reserved",
            limit_seconds=seconds,
            cents_per_second=0,
            cents_per_minute=cents_per_minute,
            credits_per_second=float(credits_per_second),
            max_credits=max_credits,
            accounted_cents=cents,
        )
        db.add(row)
    return row


def reserve_xmax(settings: XmaxSettings, visitor: str, seconds: int, *, model_id: str | None = None, now=None):
    chosen_model = normalize_model(model_id or settings.default_model, default=settings.default_model)
    if model_id and chosen_model not in settings.allowed_models:
        raise BudgetDenied("invalid_model")
    if chosen_model not in settings.allowed_models:
        chosen_model = settings.allowed_models[0]
    if not settings.min_seconds <= seconds <= settings.max_seconds:
        raise BudgetDenied("invalid_duration")

    return _reserve_subcent_provider(
        provider_key="xmax",
        chosen_model=chosen_model,
        seconds=seconds,
        setup_seconds=XMAX_SETUP_SECONDS,
        starts_per_minute=settings.starts_per_minute,
        max_active=settings.max_active,
        cents_per_minute=settings.cents_per_minute,
        credits_per_second=settings.credits_per_second,
        daily_cents=settings.daily_cents,
        monthly_cents=settings.monthly_cents,
        visitor_daily_cents=settings.visitor_daily_cents,
        visitor=visitor,
        now=now,
    )


def reserve_reactor(settings: ReactorSettings, visitor: str, seconds: int, *, model_id: str | None = None, now=None):
    chosen_model = reactor_client.normalize_model(model_id or settings.default_model, default=settings.default_model)
    if model_id and chosen_model not in settings.allowed_models:
        raise BudgetDenied("invalid_model")
    if chosen_model not in settings.allowed_models:
        chosen_model = settings.allowed_models[0]
    if not settings.min_seconds <= seconds <= settings.max_seconds:
        raise BudgetDenied("invalid_duration")

    return _reserve_subcent_provider(
        provider_key="reactor",
        chosen_model=chosen_model,
        seconds=seconds,
        setup_seconds=REACTOR_SETUP_SECONDS,
        starts_per_minute=settings.starts_per_minute,
        max_active=settings.max_active,
        cents_per_minute=settings.cents_per_minute,
        credits_per_second=settings.credits_per_second,
        daily_cents=settings.daily_cents,
        monthly_cents=settings.monthly_cents,
        visitor_daily_cents=settings.visitor_daily_cents,
        visitor=visitor,
        now=now,
    )


def claim(session_id, visitor, *, now=None):
    sessions, engine = get_session_factory()
    with sessions.begin() as db:
        _lock_admissions(db, engine)
        now = time.time() if now is None else now
        result = db.execute(update(SessionRecord).where(
            SessionRecord.id == session_id,
            SessionRecord.visitor_hash == visitor,
            SessionRecord.provider_key == "decart",
            SessionRecord.state == "reserved",
            SessionRecord.claim_before > now,
        ).values(
            state="claimed", hold_until=now + SETUP_SECONDS + CLOSE_SECONDS + SessionRecord.limit_seconds,
        ))
        return db.get(SessionRecord, session_id) if result.rowcount == 1 else None


def _claim_provider(session_id: str, visitor: str, *, provider_key: str, setup_seconds: int, now=None):
    sessions, engine = get_session_factory()
    with sessions.begin() as db:
        _lock_admissions(db, engine)
        now = time.time() if now is None else now
        result = db.execute(update(SessionRecord).where(
            SessionRecord.id == session_id,
            SessionRecord.visitor_hash == visitor,
            SessionRecord.provider_key == provider_key,
            SessionRecord.state == "reserved",
            SessionRecord.claim_before > now,
        ).values(
            state="claimed",
            hold_until=now + setup_seconds + CLOSE_SECONDS + SessionRecord.limit_seconds,
        ))
        return db.get(SessionRecord, session_id) if result.rowcount == 1 else None


def claim_xmax(session_id: str, visitor: str, *, now=None):
    return _claim_provider(session_id, visitor, provider_key="xmax", setup_seconds=XMAX_SETUP_SECONDS, now=now)


def claim_reactor(session_id: str, visitor: str, *, now=None):
    return _claim_provider(session_id, visitor, provider_key="reactor", setup_seconds=REACTOR_SETUP_SECONDS, now=now)


def save_xmax_temp_key(session_id: str, *, temp_key_uid: str, temp_key_raw: str | None) -> None:
    enc = None
    if temp_key_raw:
        enc = _encrypt_secret(temp_key_raw)
    sessions, _ = get_session_factory()
    with sessions.begin() as db:
        db.execute(update(SessionRecord).where(
            SessionRecord.id == session_id,
            SessionRecord.provider_key == "xmax",
        ).values(
            provider_temp_key_uid=(temp_key_uid or "")[:128] or None,
            provider_temp_key_encrypted=enc,
        ))


def _attach_provider_session(session_id: str, visitor: str, provider_session_id: str, *, provider_key: str) -> bool:
    clean_sid = str(provider_session_id or "").strip()[:128]
    if not clean_sid:
        return False
    sessions, _ = get_session_factory()
    with sessions.begin() as db:
        res = db.execute(update(SessionRecord).where(
            SessionRecord.id == session_id,
            SessionRecord.visitor_hash == visitor,
            SessionRecord.provider_key == provider_key,
        ).values(provider_session_id=clean_sid))
        return res.rowcount == 1


def attach_xmax_provider_session(session_id: str, visitor: str, provider_session_id: str) -> bool:
    return _attach_provider_session(session_id, visitor, provider_session_id, provider_key="xmax")


def attach_reactor_provider_session(session_id: str, visitor: str, provider_session_id: str) -> bool:
    return _attach_provider_session(session_id, visitor, provider_session_id, provider_key="reactor")


def get_session_row(session_id: str) -> SessionRecord | None:
    sessions, _ = get_session_factory()
    with sessions() as db:
        return db.get(SessionRecord, session_id)


def decrypt_xmax_temp_key(row: SessionRecord | None) -> str:
    if not row or not row.provider_temp_key_encrypted:
        return ""
    try:
        return _decrypt_secret(row.provider_temp_key_encrypted).strip()
    except Exception:
        return ""


def request_stop(session_id, visitor, *, reason: str = "stopped"):
    clean_reason = str(reason or "stopped").strip().lower()[:32] or "stopped"
    sessions, _ = get_session_factory()
    with sessions.begin() as db:
        canceled = db.execute(update(SessionRecord).where(
            SessionRecord.id == session_id, SessionRecord.visitor_hash == visitor, SessionRecord.state == "reserved",
        ).values(
            state="ended",
            hold_until=0,
            accounted_cents=0,
            reason=clean_reason,
            ended_at=time.time(),
            provider_temp_key_encrypted=None,
        ))
        if not canceled.rowcount:
            db.execute(update(SessionRecord).where(
                SessionRecord.id == session_id, SessionRecord.visitor_hash == visitor, SessionRecord.state == "claimed",
            ).values(stop_requested=True))
        return db.get(SessionRecord, session_id)


def stop_requested(session_id):
    sessions, _ = get_session_factory()
    with sessions() as db:
        return db.scalar(select(SessionRecord.stop_requested).where(SessionRecord.id == session_id))


def finalize(row, *, reason, provider_session_id, provider_seconds, join_sent):
    confirmed = provider_seconds is not None
    values = {
        "state": "ended", "reason": reason, "provider_session_id": provider_session_id,
        "provider_seconds": provider_seconds, "ended_at": time.time(),
    }
    if confirmed or not join_sent:
        values["hold_until"] = 0
        values["accounted_cents"] = math.ceil(provider_seconds or 0) * row.cents_per_second
    sessions, _ = get_session_factory()
    with sessions.begin() as db:
        db.execute(update(SessionRecord).where(
            SessionRecord.id == row.id, SessionRecord.state == "claimed",
        ).values(**values))


def finalize_xmax(
    session_id: str,
    *,
    reason: str,
    provider_session_id: str | None = None,
    provider_credits: float | None = None,
    zero_charge: bool = False,
    clear_temp_key: bool = True,
) -> SessionRecord | None:
    sessions, _ = get_session_factory()
    with sessions.begin() as db:
        row = db.get(SessionRecord, session_id)
        if not row or row.provider_key != "xmax":
            return None
        if row.state == "ended":
            if clear_temp_key and row.provider_temp_key_encrypted is not None:
                row.provider_temp_key_encrypted = None
            return row

        now = time.time()
        cps = max(0.001, float(row.credits_per_second or 1.0))
        cpm = max(1, int(row.cents_per_minute or 10))
        values: dict[str, object] = {
            "state": "ended",
            "reason": reason,
            "ended_at": now,
        }
        if provider_session_id:
            values["provider_session_id"] = provider_session_id[:128]
        if clear_temp_key:
            values["provider_temp_key_encrypted"] = None

        if zero_charge:
            values["hold_until"] = 0
            values["provider_credits"] = 0.0
            values["provider_seconds"] = 0.0
            values["accounted_cents"] = 0
        elif provider_credits is not None:
            credits_val = max(0.0, float(provider_credits))
            values["hold_until"] = 0
            values["provider_credits"] = round(credits_val, 3)
            values["provider_seconds"] = round(credits_val / cps, 3)
            values["accounted_cents"] = xmax_credits_to_cents(credits_val, cps, cpm)
        # Else: keep conservative accounted_cents and hold_until so unconfirmed usage stays reserved.

        db.execute(update(SessionRecord).where(
            SessionRecord.id == session_id,
            SessionRecord.state.in_(("reserved", "claimed")),
        ).values(**values))
        db.expire(row)
        return db.get(SessionRecord, session_id)


def finalize_reactor(
    session_id: str,
    *,
    reason: str,
    provider_session_id: str | None = None,
    provider_seconds: float | None = None,
    provider_credits: float | None = None,
    zero_charge: bool = False,
) -> SessionRecord | None:
    sessions, _ = get_session_factory()
    with sessions.begin() as db:
        row = db.get(SessionRecord, session_id)
        if not row or row.provider_key != "reactor":
            return None
        if row.state == "ended":
            return row

        now = time.time()
        cps = max(0.001, float(row.credits_per_second or reactor_client.REACTOR_DEFAULT_CREDITS_PER_SECOND))
        cpm = max(1, int(row.cents_per_minute or reactor_client.REACTOR_DEFAULT_CENTS_PER_MINUTE))
        values: dict[str, object] = {
            "state": "ended",
            "reason": reason,
            "ended_at": now,
        }
        if provider_session_id:
            values["provider_session_id"] = provider_session_id[:128]

        if zero_charge:
            values["hold_until"] = 0
            values["provider_credits"] = 0.0
            values["provider_seconds"] = 0.0
            values["accounted_cents"] = 0
        elif provider_seconds is not None or provider_credits is not None:
            if provider_seconds is not None:
                sec_val = max(0.0, float(provider_seconds))
                cred_val = float(provider_credits) if provider_credits is not None else sec_val * cps
            else:
                cred_val = max(0.0, float(provider_credits or 0.0))
                sec_val = cred_val / cps
            values["hold_until"] = 0
            values["provider_seconds"] = round(sec_val, 3)
            values["provider_credits"] = round(cred_val, 3)
            values["accounted_cents"] = reactor_seconds_to_cents(sec_val, cpm)
        # Else: keep conservative accounted_cents and hold_until until confirmed/reconciled.

        db.execute(update(SessionRecord).where(
            SessionRecord.id == session_id,
            SessionRecord.state.in_(("reserved", "claimed")),
        ).values(**values))
        db.expire(row)
        return db.get(SessionRecord, session_id)


def receipt(row, *, now=None):
    now = time.time() if now is None else now
    state, reason, cents = row.state, row.reason, row.accounted_cents
    if state == "reserved" and row.claim_before <= now:
        state, reason, cents = "ended", "expired", 0
    if state == "claimed" and row.hold_until <= now:
        state, reason = "ended", "usage_unconfirmed"
    p_key = row.provider_key or "decart"
    is_subcent = p_key in {"xmax", "reactor"}
    default_cpm = reactor_client.REACTOR_DEFAULT_CENTS_PER_MINUTE if p_key == "reactor" else 10
    default_model = (
        reactor_client.REACTOR_DEFAULT_MODEL
        if p_key == "reactor"
        else ("x2.1" if p_key == "xmax" else MODEL)
    )
    max_cents = (
        xmax_session_cents(row.limit_seconds, int(row.cents_per_minute or default_cpm))
        if is_subcent
        else row.limit_seconds * row.cents_per_second
    )
    payload = {
        "id": row.id,
        "provider_key": p_key,
        "model_id": row.model_id or default_model,
        "state": state,
        "reason": reason,
        "max_seconds": row.limit_seconds,
        "cents_per_second": row.cents_per_second,
        "cents_per_minute": row.cents_per_minute,
        "credits_per_second": row.credits_per_second,
        "max_credits": row.max_credits,
        "max_cents": max_cents,
        "accounted_cents": cents,
        "provider_seconds": row.provider_seconds,
        "provider_credits": row.provider_credits,
    }
    return payload


def get_receipt(session_id, visitor):
    sessions, _ = get_session_factory()
    with sessions() as db:
        row = db.get(SessionRecord, session_id)
        return receipt(row) if row and row.visitor_hash == visitor else None


def status_snapshot(settings: Settings, visitor: str = "", *, now=None):
    now = time.time() if now is None else now
    _, _, tomorrow = _calendar(now)
    sessions, _ = get_session_factory()
    with sessions() as db:
        totals = _totals(db, now, visitor, provider_key="decart")
        active_sessions = int(
            db.scalar(
                select(func.count())
                .select_from(SessionRecord)
                .where(
                    SessionRecord.provider_key == "decart",
                    SessionRecord.hold_until > now,
                    SessionRecord.state.in_(("reserved", "claimed")),
                )
            )
            or 0
        )
    visitor_remaining = max(0, settings.visitor_daily_cents - int(totals.visitor))
    site_daily_remaining = max(0, settings.daily_cents - int(totals.day))
    site_monthly_remaining = max(0, settings.monthly_cents - int(totals.month))
    min_session_cents = MIN_SECONDS * settings.cents_per_second
    can_start_min_session = (
        settings.available
        and active_sessions < settings.max_active
        and visitor_remaining >= min_session_cents
        and site_daily_remaining >= min_session_cents
        and site_monthly_remaining >= min_session_cents
    )
    return {
        "timezone": BUDGET_ZONE.key,
        "next_daily_reset": tomorrow.isoformat(),
        "active_sessions": active_sessions,
        "max_active": settings.max_active,
        "visitor_daily_cents": settings.visitor_daily_cents,
        "visitor_spent_cents": int(totals.visitor),
        "visitor_remaining_cents": visitor_remaining,
        "site_daily_remaining_cents": site_daily_remaining,
        "site_monthly_remaining_cents": site_monthly_remaining,
        "min_session_cents": min_session_cents,
        "can_start_min_session": can_start_min_session,
    }


def _subcent_status_snapshot(provider_key: str, settings: XmaxSettings | ReactorSettings, visitor: str = "", *, now=None):
    now = time.time() if now is None else now
    _, _, tomorrow = _calendar(now)
    sessions, _ = get_session_factory()
    with sessions() as db:
        totals = _totals(db, now, visitor, provider_key=provider_key)
        active_sessions = int(
            db.scalar(
                select(func.count())
                .select_from(SessionRecord)
                .where(
                    SessionRecord.provider_key == provider_key,
                    SessionRecord.hold_until > now,
                    SessionRecord.state.in_(("reserved", "claimed")),
                )
            )
            or 0
        )
    visitor_remaining = max(0, settings.visitor_daily_cents - int(totals.visitor))
    site_daily_remaining = max(0, settings.daily_cents - int(totals.day))
    site_monthly_remaining = max(0, settings.monthly_cents - int(totals.month))
    min_session_cents = xmax_session_cents(settings.min_seconds, settings.cents_per_minute)
    can_start_min_session = (
        settings.available
        and active_sessions < settings.max_active
        and visitor_remaining >= min_session_cents
        and site_daily_remaining >= min_session_cents
        and site_monthly_remaining >= min_session_cents
    )
    return {
        "timezone": BUDGET_ZONE.key,
        "next_daily_reset": tomorrow.isoformat(),
        "active_sessions": active_sessions,
        "max_active": settings.max_active,
        "visitor_daily_cents": settings.visitor_daily_cents,
        "visitor_spent_cents": int(totals.visitor),
        "visitor_remaining_cents": visitor_remaining,
        "site_daily_remaining_cents": site_daily_remaining,
        "site_monthly_remaining_cents": site_monthly_remaining,
        "min_session_cents": min_session_cents,
        "min_session_credits": int(math.ceil(settings.min_seconds * settings.credits_per_second)),
        "can_start_min_session": can_start_min_session,
    }


def status_snapshot_xmax(settings: XmaxSettings, visitor: str = "", *, now=None):
    return _subcent_status_snapshot("xmax", settings, visitor, now=now)


def status_snapshot_reactor(settings: ReactorSettings, visitor: str = "", *, now=None):
    return _subcent_status_snapshot("reactor", settings, visitor, now=now)


def diagnose_settings() -> dict:
    try:
        cfg = load_settings()
    except Exception as exc:
        return {
            "enabled": False,
            "available": False,
            "source": "error",
            "model": MODEL,
            "origin_configured": False,
            "origin_https": False,
            "require_access_code": True,
            "error": type(exc).__name__,
        }
    return {
        "enabled": cfg.enabled,
        "available": cfg.available,
        "source": cfg.source,
        "model": MODEL,
        "origin_configured": bool(cfg.origin),
        "origin_https": cfg.origin.startswith("https://"),
        "require_access_code": cfg.require_access_code,
    }


def diagnose_xmax_settings() -> dict:
    try:
        cfg = load_xmax_settings()
    except Exception as exc:
        return {
            "enabled": False,
            "available": False,
            "source": "error",
            "environment": "global",
            "model": "x2.1",
            "origin_configured": False,
            "origin_https": False,
            "require_access_code": True,
            "error": type(exc).__name__,
        }
    return {
        "enabled": cfg.enabled,
        "available": cfg.available,
        "source": cfg.source,
        "environment": cfg.environment,
        "model": cfg.default_model,
        "allowed_models": list(cfg.allowed_models),
        "origin_configured": bool(cfg.origin),
        "origin_https": cfg.origin.startswith("https://"),
        "require_access_code": cfg.require_access_code,
    }


def diagnose_reactor_settings() -> dict:
    try:
        cfg = load_reactor_settings()
    except Exception as exc:
        return {
            "enabled": False,
            "available": False,
            "source": "error",
            "model": reactor_client.REACTOR_DEFAULT_MODEL,
            "allowed_models": list(reactor_client.REACTOR_MODELS),
            "origin_configured": False,
            "origin_https": False,
            "require_access_code": True,
            "error": type(exc).__name__,
        }
    return {
        "enabled": cfg.enabled,
        "available": cfg.available,
        "source": cfg.source,
        "model": cfg.default_model,
        "allowed_models": list(cfg.allowed_models),
        "origin_configured": bool(cfg.origin),
        "origin_https": cfg.origin.startswith("https://"),
        "require_access_code": cfg.require_access_code,
    }


def usage_report(settings, *, provider_key: str = "decart"):
    now = time.time()
    day, _, tomorrow = _calendar(now)
    sessions, _ = get_session_factory()
    with sessions() as db:
        totals = _totals(db, now, provider_key=provider_key)
        recent = db.scalars(
            select(SessionRecord)
            .where(SessionRecord.provider_key == provider_key)
            .order_by(SessionRecord.created_at.desc())
            .limit(25)
        ).all()
        return {
            "provider_key": provider_key,
            "currency": "USD",
            "unit": "cent",
            "timezone": BUDGET_ZONE.key,
            "day": day,
            "next_daily_reset": tomorrow.isoformat(),
            "daily": {"limit": settings.daily_cents, "accounted": totals.day, "provider_confirmed": totals.confirmed_day},
            "monthly": {"limit": settings.monthly_cents, "accounted": totals.month, "provider_confirmed": totals.confirmed_month},
            "recent": [
                receipt(row, now=now) | {
                    "provider_session_id": row.provider_session_id,
                    "created_at": datetime.fromtimestamp(row.created_at, BUDGET_ZONE).isoformat(),
                    "ended_at": datetime.fromtimestamp(row.ended_at, BUDGET_ZONE).isoformat() if row.ended_at else None,
                }
                for row in recent
            ],
        }


if __name__ == "__main__":
    print(json.dumps(usage_report(load_settings()), indent=2))
