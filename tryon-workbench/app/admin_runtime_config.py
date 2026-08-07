"""Runtime AI configuration for try-on station — reads from admin DB.

Resolution order:
  1. Admin database ai_api_providers (gemini) + ai_feature_configs (tryon)
  2. Environment variables (GEMINI_API_KEY, TRYON_FLASH_MODEL, TRYON_PRO_MODEL)
  3. Last-known-good cached config
  4. 503 unavailable

DB URL resolution order:
  1. AI_CONFIG_DATABASE_URL (explicit)
  2. DATABASE_URL (shared)
  3. Local dev fallback: admin/backend/admin_local.db

Uses SQLAlchemy Core with pool_pre_ping=True.
Config is cached for config_cache_seconds (default 15s) to allow hot-reload
without restarting the try-on service.
"""
from __future__ import annotations

import base64
import hashlib
import json as _json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path constants for local dev fallback
# ---------------------------------------------------------------------------
_CLOUD_ROOT = Path(__file__).resolve().parent.parent  # PJ111ForGemini/Cloud/
_PROJECT_ROOT = _CLOUD_ROOT.parent.parent  # Project4.15-AI-Try-on/
_LOCAL_ADMIN_DB = _PROJECT_ROOT / "Project4.15-AI-Try-on-with-frontend" / "admin" / "backend" / "admin_local.db"


# ---------------------------------------------------------------------------
# Inline decrypt (compatible with admin secret_crypto.py)
# ---------------------------------------------------------------------------
_fernet = None
_fernet_init_attempted = False


def _is_production() -> bool:
    app_env = os.getenv("APP_ENV", "").strip().lower()
    if app_env in ("production", "prod"):
        return True
    if app_env == "development":
        return False
    env = os.getenv("ENV", "").strip().lower()
    if env in ("production", "prod"):
        return True
    if os.getenv("K_SERVICE"):
        return True
    return False


def _get_fernet():
    global _fernet, _fernet_init_attempted
    if _fernet_init_attempted:
        return _fernet
    _fernet_init_attempted = True

    key = os.getenv("FERNET_SECRET_KEY", "").strip()
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet

        if len(key) != 44 or not key.endswith("="):
            key = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
        _fernet = Fernet(key)
        return _fernet
    except Exception as exc:
        logger.warning("Failed to init Fernet for tryon runtime config: %s", exc)
        return None


def _decrypt_secret(value: str) -> str:
    """Decrypt a secret encrypted by admin secret_crypto.py."""
    if not value:
        return ""
    if value.startswith("fernet:"):
        f = _get_fernet()
        if f is None:
            raise RuntimeError("Fernet key unavailable — cannot decrypt")
        return f.decrypt(value[7:].encode("ascii")).decode("utf-8")
    if value.startswith("b64:"):
        if _is_production():
            raise RuntimeError("Cannot decrypt b64-encoded secret in production")
        return base64.urlsafe_b64decode(value[4:].encode("ascii")).decode("utf-8")
    raise ValueError(f"Unknown secret format (prefix={value[:8]}...)")


# ---------------------------------------------------------------------------
# DB URL resolution
# ---------------------------------------------------------------------------
def _resolve_db_url() -> tuple[str | None, str]:
    url = os.getenv("AI_CONFIG_DATABASE_URL", "").strip()
    if url:
        return url, "ai_config_database_url"

    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        return url, "database_url"

    if not _is_production() and _LOCAL_ADMIN_DB.exists():
        return f"sqlite:///{_LOCAL_ADMIN_DB.as_posix()}", "local_admin_db"

    return None, "unavailable"


# ---------------------------------------------------------------------------
# Engine cache
# ---------------------------------------------------------------------------
_engine = None
_engine_url: str | None = None


def _get_engine():
    global _engine, _engine_url
    url, _ = _resolve_db_url()
    if not url:
        return None
    if _engine is not None and _engine_url == url:
        return _engine

    try:
        from sqlalchemy import create_engine
    except ImportError as exc:
        raise RuntimeError(
            "试衣服务缺少数据库运行依赖 sqlalchemy，请重新安装 requirements.txt"
        ) from exc

    connect_args: dict[str, Any] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    _engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    _engine_url = url
    return _engine


# ---------------------------------------------------------------------------
# Config cache
# ---------------------------------------------------------------------------
_cache_lock = threading.Lock()
_cached_config: dict[str, Any] | None = None
_cache_timestamp: float = 0
_DEFAULT_CACHE_TTL = 15  # seconds


def _read_config_from_db() -> dict[str, Any] | None:
    """Read tryon config from admin database.

    Returns None only when the database itself is unavailable. An accessible
    database with missing, disabled, or undecryptable configuration is
    authoritative and must not be bypassed by environment fallback.
    """
    engine = _get_engine()
    if engine is None:
        return None

    try:
        from sqlalchemy import MetaData, Table, select

        metadata = MetaData()
        providers = Table("ai_api_providers", metadata, autoload_with=engine)
        features = Table("ai_feature_configs", metadata, autoload_with=engine)

        # Read provider (include disabled — we need to report disabled state)
        prov_stmt = (
            select(
                providers.c.api_key_encrypted,
                providers.c.enabled,
                providers.c.timeout_seconds,
                providers.c.retry_count,
                providers.c.updated_at,
            )
            .where(providers.c.provider_key == "gemini")
        )

        # Read feature (include disabled)
        feat_stmt = (
            select(
                features.c.enabled,
                features.c.config,
                features.c.updated_at,
                features.c.default_model,
            )
            .where(features.c.feature_key == "tryon")
        )

        with engine.connect() as conn:
            prov_row = conn.execute(prov_stmt).fetchone()
            feat_row = conn.execute(feat_stmt).fetchone()

        if not prov_row or not feat_row:
            return {
                "enabled": False,
                "api_key": "",
                "flash_model": "",
                "pro_model": "",
                "timeout_seconds": 60,
                "retry_count": 1,
                "config_cache_seconds": _DEFAULT_CACHE_TTL,
                "source": "admin_db",
                "updated_at": None,
                "config_error": "missing_admin_config",
            }

        # Decrypt API key
        api_key = ""
        encrypted = prov_row[0]
        if encrypted:
            try:
                api_key = _decrypt_secret(encrypted)
            except Exception as exc:
                logger.warning("Cannot decrypt gemini key for tryon: %s", exc)

        # Parse feature config
        feat_config = feat_row[1]
        if isinstance(feat_config, str):
            try:
                feat_config = _json.loads(feat_config)
            except Exception:
                feat_config = {}
        if not isinstance(feat_config, dict):
            feat_config = {}

        try:
            cache_ttl = int(feat_config.get("config_cache_seconds", _DEFAULT_CACHE_TTL))
        except (TypeError, ValueError):
            cache_ttl = _DEFAULT_CACHE_TTL
        cache_ttl = max(1, min(300, cache_ttl))
        provider_enabled = bool(prov_row[1])
        feature_enabled = bool(feat_row[0])
        flash_model = str(
            feat_config.get("flash_model") or feat_row[3] or ""
        ).strip()
        pro_model = str(feat_config.get("pro_model") or "").strip()

        return {
            "enabled": provider_enabled and feature_enabled,
            "api_key": api_key,
            "flash_model": flash_model,
            "pro_model": pro_model,
            "timeout_seconds": int(prov_row[2] or 60),
            "retry_count": int(prov_row[3] or 1),
            "config_cache_seconds": cache_ttl,
            "source": "admin_db",
            "updated_at": feat_row[2].isoformat() if feat_row[2] else None,
            "config_error": (
                "provider_disabled"
                if not provider_enabled
                else "feature_disabled"
                if not feature_enabled
                else "api_key_unavailable"
                if not api_key
                else ""
            ),
        }

    except Exception as exc:
        logger.warning("Failed to read tryon config from DB: %s", exc)
        return None


def _read_config_from_env() -> dict[str, Any] | None:
    """Read tryon config from environment variables (disaster fallback)."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    return {
        "enabled": True,
        "api_key": api_key,
        "flash_model": os.getenv("TRYON_FLASH_MODEL", "gemini-3.1-flash-image-preview").strip(),
        "pro_model": os.getenv("TRYON_PRO_MODEL", "gemini-3-pro-image-preview").strip(),
        "timeout_seconds": 60,
        "retry_count": 1,
        "config_cache_seconds": _DEFAULT_CACHE_TTL,
        "source": "env_fallback",
        "updated_at": None,
    }


def resolve_tryon_runtime_config() -> dict[str, Any]:
    """Resolve tryon runtime config with caching.

    Returns dict with keys: enabled, api_key, flash_model, pro_model,
    timeout_seconds, retry_count, source, updated_at.

    Raises RuntimeError with 503-compatible message if no config is available.
    """
    global _cached_config, _cache_timestamp

    now = time.time()

    # Check cache
    with _cache_lock:
        if _cached_config is not None:
            ttl = _cached_config.get("config_cache_seconds", _DEFAULT_CACHE_TTL)
            if now - _cache_timestamp < ttl:
                return _cached_config

    # Try DB first
    db_config = _read_config_from_db()
    if db_config is not None:
        with _cache_lock:
            _cached_config = db_config
            _cache_timestamp = now
        return db_config

    # Try env fallback
    env_config = _read_config_from_env()
    if env_config is not None:
        with _cache_lock:
            _cached_config = env_config
            _cache_timestamp = now
        return env_config

    # Last resort: use last-known-good if available
    with _cache_lock:
        if _cached_config is not None:
            logger.warning("Using last-known-good tryon config (DB and env unavailable)")
            return {**_cached_config, "source": "last_known_good"}

    # Truly unavailable
    raise RuntimeError("试衣服务配置不可用：数据库和环境变量均无法提供配置")


def get_tryon_runtime_status() -> dict[str, Any]:
    """Get non-sensitive runtime status for /api/runtime-status endpoint.

    Never returns API keys, masked keys, or internal details.
    """
    try:
        config = resolve_tryon_runtime_config()
        models = []
        if config.get("flash_model"):
            models.append("flash")
        if config.get("pro_model"):
            models.append("pro")
        return {
            "tryon_enabled": config.get("enabled", False),
            "configured": bool(config.get("api_key")),
            "available_models": models,
            "config_source": config.get("source", "unknown"),
        }
    except Exception as exc:
        logger.warning("Tryon runtime config status unavailable: %s", exc)
        return {
            "tryon_enabled": False,
            "configured": False,
            "available_models": [],
            "config_source": "unavailable",
        }
