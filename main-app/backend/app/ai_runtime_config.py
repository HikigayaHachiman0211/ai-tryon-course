"""Runtime AI configuration — reads from admin DB via SQLAlchemy Core, falls back to env vars.

Resolution order for provider/model/key:
  1. Request-level override (passed by caller)
  2. Admin database ai_api_providers / ai_feature_configs
  3. Environment variables
  4. Code defaults
  5. Rule fallback

DB URL resolution order:
  1. AI_CONFIG_DATABASE_URL (explicit)
  2. DATABASE_URL (shared)
  3. Local dev fallback: <project_root>/admin/backend/admin_local.db

Uses SQLAlchemy Core Table reflection with `.is_(True)` for boolean filtering,
which works on both PostgreSQL (Google Cloud SQL) and SQLite.  The engine is
cached at module level and only recreated when the DB URL changes.

All DB reads are wrapped in try/except — a broken DB or missing table must
never crash recommendation.
"""
from __future__ import annotations

import base64
import hashlib
import json as _json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path constants for local dev fallback
# ---------------------------------------------------------------------------

_BACKEND_APP_ROOT = Path(__file__).resolve().parent  # backend/app/
_BACKEND_ROOT = _BACKEND_APP_ROOT.parent             # backend/
_PROJECT_ROOT = _BACKEND_ROOT.parent                 # Project4.15-AI-Try-on-with-frontend/
_LOCAL_ADMIN_DB = _PROJECT_ROOT / "admin" / "backend" / "admin_local.db"


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
        logger.warning("Failed to init Fernet for runtime config decrypt: %s", exc)
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
# DB URL resolution — shared logic
# ---------------------------------------------------------------------------

def resolve_ai_config_database_url() -> tuple[str | None, str]:
    """Resolve the AI config database URL with local dev fallback.

    Returns (url, source) where source is one of:
      - "ai_config_database_url"  — from explicit env var
      - "database_url"            — from shared DATABASE_URL
      - "local_admin_db"          — from local admin/backend/admin_local.db
      - "unavailable"             — no DB found
    """
    # 1. Explicit AI config DB URL
    url = os.getenv("AI_CONFIG_DATABASE_URL", "").strip()
    if url:
        return url, "ai_config_database_url"

    # 2. Shared DATABASE_URL (but NOT the main product DB in local dev)
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        return url, "database_url"

    # 3. Local dev fallback: admin/backend/admin_local.db
    if not _is_production() and _LOCAL_ADMIN_DB.exists():
        sqlite_url = f"sqlite:///{_LOCAL_ADMIN_DB.as_posix()}"
        return sqlite_url, "local_admin_db"

    return None, "unavailable"


# ---------------------------------------------------------------------------
# Engine cache — one engine per DB URL
# ---------------------------------------------------------------------------

_engine = None
_engine_url: str | None = None
_engine_source: str = "unavailable"


def _get_engine():
    """Get or create a cached SQLAlchemy engine for the AI config database."""
    global _engine, _engine_url, _engine_source

    url, source = resolve_ai_config_database_url()
    if not url:
        return None

    # Return cached engine if URL hasn't changed
    if _engine is not None and _engine_url == url:
        return _engine

    from sqlalchemy import create_engine

    connect_args: dict[str, Any] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    _engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    _engine_url = url
    _engine_source = source
    return _engine


# ---------------------------------------------------------------------------
# DB helpers — SQLAlchemy Core with boolean-safe filtering
# ---------------------------------------------------------------------------

def _query_provider(provider_key: str) -> dict[str, Any] | None:
    """Read a single provider from ai_api_providers via SQLAlchemy Core.

    Returns None only when the DB is unavailable or the row does not exist.
    When the row exists but enabled=False the dict is returned with
    ``enabled=False`` and ``api_key=""`` so callers can distinguish
    "explicitly disabled" from "not configured".
    """
    engine = _get_engine()
    if engine is None:
        return None
    try:
        from sqlalchemy import MetaData, Table, select

        metadata = MetaData()
        providers = Table("ai_api_providers", metadata, autoload_with=engine)
        stmt = (
            select(
                providers.c.provider_key,
                providers.c.base_url,
                providers.c.api_key_encrypted,
                providers.c.auth_type,
                providers.c.auth_header_name,
                providers.c.default_model,
                providers.c.enabled,
            )
            .where(providers.c.provider_key == provider_key)
            # No enabled filter — callers must check the 'enabled' field.
        )
        with engine.connect() as conn:
            row = conn.execute(stmt).fetchone()
            if not row:
                return None

            is_enabled = bool(row[6]) if row[6] is not None else True

            api_key = ""
            if is_enabled:
                encrypted = row[2]
                if encrypted:
                    try:
                        api_key = _decrypt_secret(encrypted)
                    except Exception as exc:
                        logger.warning(
                            "Cannot decrypt key for provider %s: %s", provider_key, exc
                        )
                        api_key = ""

            return {
                "base_url": (row[1] or "").rstrip("/"),
                "default_model": row[5] or "",
                "api_key": api_key,
                "auth_type": row[3] or "api_key_header",
                "auth_header_name": row[4] or "",
                "enabled": is_enabled,
            }
    except Exception as exc:
        logger.debug("DB provider query failed for %s: %s", provider_key, exc)
        return None


def _query_provider_raw(provider_key: str) -> dict[str, Any] | None:
    """Read a single provider WITHOUT decrypting — for diagnostics."""
    engine = _get_engine()
    if engine is None:
        return None
    try:
        from sqlalchemy import MetaData, Table, select

        metadata = MetaData()
        providers = Table("ai_api_providers", metadata, autoload_with=engine)
        stmt = (
            select(
                providers.c.provider_key,
                providers.c.enabled,
                providers.c.api_key_encrypted,
                providers.c.default_model,
                providers.c.auth_type,
                providers.c.auth_header_name,
            )
            .where(providers.c.provider_key == provider_key)
        )
        with engine.connect() as conn:
            row = conn.execute(stmt).fetchone()
            if not row:
                return None

            has_key = bool(row[2])
            decrypt_ok = False
            if has_key:
                try:
                    _decrypt_secret(row[2])
                    decrypt_ok = True
                except Exception:
                    decrypt_ok = False

            return {
                "enabled": bool(row[1]) if row[1] is not None else False,
                "has_api_key": has_key,
                "decrypt_ok": decrypt_ok,
                "default_model": row[3] or "",
                "auth_type": row[4] or "",
                "auth_header_name": row[5] or "",
            }
    except Exception as exc:
        logger.debug("DB provider raw query failed for %s: %s", provider_key, exc)
        return None


def _query_feature(feature_key: str, include_disabled: bool = False) -> dict[str, Any] | None:
    """Read a single feature from ai_feature_configs via SQLAlchemy Core.

    By default only returns enabled features (backward compatible).
    Pass include_disabled=True to also return disabled features — needed
    for voice config to correctly report disabled state instead of falling
    through to code defaults.
    """
    engine = _get_engine()
    if engine is None:
        return None
    try:
        from sqlalchemy import MetaData, Table, select

        metadata = MetaData()
        features = Table("ai_feature_configs", metadata, autoload_with=engine)
        conditions = [features.c.feature_key == feature_key]
        if not include_disabled:
            conditions.append(features.c.enabled.is_(True))
        stmt = (
            select(
                features.c.feature_key,
                features.c.default_provider,
                features.c.fallback_order,
                features.c.default_model,
                features.c.config,
                features.c.enabled,
            )
            .where(*conditions)
        )
        with engine.connect() as conn:
            row = conn.execute(stmt).fetchone()
            if not row:
                return None

            fallback = row[2]
            if isinstance(fallback, str):
                try:
                    fallback = _json.loads(fallback)
                except Exception:
                    fallback = []

            config = row[4]
            if isinstance(config, str):
                try:
                    config = _json.loads(config)
                except Exception:
                    config = {}

            return {
                "feature_key": row[0] or "",
                "default_provider": row[1] or "",
                "fallback_order": fallback or [],
                "default_model": row[3] or "",
                "config": config or {},
                "enabled": bool(row[5]) if row[5] is not None else True,
            }
    except Exception as exc:
        logger.debug("DB feature query failed for %s: %s", feature_key, exc)
        return None


def _query_feature_raw(feature_key: str) -> dict[str, Any] | None:
    """Read a single feature WITHOUT filtering enabled — for diagnostics."""
    engine = _get_engine()
    if engine is None:
        return None
    try:
        from sqlalchemy import MetaData, Table, select

        metadata = MetaData()
        features = Table("ai_feature_configs", metadata, autoload_with=engine)
        stmt = (
            select(
                features.c.feature_key,
                features.c.enabled,
                features.c.default_provider,
                features.c.fallback_order,
            )
            .where(features.c.feature_key == feature_key)
        )
        with engine.connect() as conn:
            row = conn.execute(stmt).fetchone()
            if not row:
                return None

            fallback = row[3]
            if isinstance(fallback, str):
                try:
                    fallback = _json.loads(fallback)
                except Exception:
                    fallback = []

            return {
                "enabled": bool(row[1]) if row[1] is not None else False,
                "default_provider": row[2] or "",
                "fallback_order": fallback or [],
            }
    except Exception as exc:
        logger.debug("DB feature raw query failed for %s: %s", feature_key, exc)
        return None


# ---------------------------------------------------------------------------
# Code defaults (step 4)
# ---------------------------------------------------------------------------

_PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "mimo": {
        "base_url": "https://api.xiaomimimo.com/v1",
        "default_model": "mimo-v2.5",
        "auth_type": "api_key_header",
        "auth_header_name": "api-key",
        "env_key_var": "MIMO_API_KEY",
        "env_base_var": "MIMO_API_BASE",
    },
    "mimo_asr": {
        "base_url": "https://api.xiaomimimo.com/v1",
        "default_model": "mimo-v2.5-asr",
        "auth_type": "api_key_header",
        "auth_header_name": "api-key",
        "env_key_var": "MIMO_API_KEY",
        "env_base_var": "MIMO_API_BASE",
    },
    "mimo_tts": {
        "base_url": "https://api.xiaomimimo.com/v1",
        "default_model": "mimo-v2.5-tts",
        "auth_type": "api_key_header",
        "auth_header_name": "api-key",
        "env_key_var": "MIMO_API_KEY",
        "env_base_var": "MIMO_API_BASE",
    },
    "gemini": {
        "base_url": "",
        "default_model": "gemini-3.1-flash-lite-preview",
        "auth_type": "query_key",
        "auth_header_name": "",
        "env_key_var": "GEMINI_API_KEY",
        "env_base_var": "",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-v4-flash",
        "auth_type": "bearer",
        "auth_header_name": "Authorization",
        "env_key_var": "DEEPSEEK_API_KEY",
        "env_base_var": "",
    },
}

_FEATURE_DEFAULTS: dict[str, dict[str, Any]] = {
    "recommendation": {
        "default_provider": "mimo",
        "fallback_order": ["mimo", "gemini", "deepseek", "rule"],
    },
    "vision_analysis": {
        "default_provider": "mimo",
        "fallback_order": ["mimo", "gemini"],
    },
    "assistant_chat": {
        "default_provider": "mimo",
        "fallback_order": ["mimo", "deepseek", "rule"],
    },
    "voice_asr": {
        "default_provider": "mimo_asr",
        "fallback_order": ["mimo_asr"],
        "default_model": "mimo-v2.5-asr",
    },
    "voice_tts": {
        "default_provider": "mimo_tts",
        "fallback_order": ["mimo_tts"],
        "default_model": "mimo-v2.5-tts",
    },
    "voice_clone": {
        "default_provider": "mimo_voice_clone",
        "fallback_order": ["mimo_voice_clone"],
        "default_model": "mimo-v2.5-tts-voiceclone",
    },
}


# ---------------------------------------------------------------------------
# Text-feature guard constants
# ---------------------------------------------------------------------------

# Features that perform text/profile inference — must never receive an
# image-generation Gemini model (e.g. gemini-*-image-*).
_TEXT_FEATURES: frozenset[str] = frozenset({
    "recommendation",
    "vision_analysis",
    "assistant_chat",
})


# ---------------------------------------------------------------------------
# Public auth-header helper
# ---------------------------------------------------------------------------

def build_auth_headers(cfg: dict[str, Any]) -> dict[str, str]:
    """Build HTTP auth headers from a resolved provider-config dict.

    Supports three auth styles:
      bearer           → Authorization: Bearer <key>
      api_key_header   → <auth_header_name or 'api-key'>: <key>
      query_key        → no auth header (key goes in URL query params)

    Always includes Content-Type: application/json.
    """
    headers: dict[str, str] = {"Content-Type": "application/json"}
    api_key = cfg.get("api_key", "")
    auth_type = (cfg.get("auth_type") or "").strip().lower()
    header_name = (cfg.get("auth_header_name") or "").strip()

    if auth_type == "bearer" or header_name.lower() == "authorization":
        headers["Authorization"] = f"Bearer {api_key}"
    elif auth_type == "query_key":
        pass  # key goes in URL params, not headers
    else:
        headers[header_name or "api-key"] = api_key
    return headers


# ---------------------------------------------------------------------------
# Diagnostic helpers
# ---------------------------------------------------------------------------

def get_diagnostics() -> dict[str, Any]:
    """Return non-sensitive diagnostics about the AI runtime config state.

    Never returns API keys, masked keys, or full error messages.
    """
    _, db_url_source = resolve_ai_config_database_url()
    engine = _get_engine()
    db_available = engine is not None

    # Check tables
    tables: dict[str, bool] = {}
    if db_available:
        for table_name in ("ai_api_providers", "ai_feature_configs", "prompt_configs"):
            try:
                from sqlalchemy import MetaData, Table
                metadata = MetaData()
                Table(table_name, metadata, autoload_with=engine)
                tables[table_name] = True
            except Exception:
                tables[table_name] = False

    # Check providers
    providers: dict[str, dict[str, Any]] = {}
    for pk in ("mimo", "mimo_asr", "mimo_tts", "mimo_voice_clone", "gemini", "deepseek"):
        raw = _query_provider_raw(pk)
        if raw:
            providers[pk] = raw
        else:
            providers[pk] = {
                "enabled": False,
                "has_api_key": False,
                "decrypt_ok": False,
                "default_model": "",
                "auth_type": "",
                "auth_header_name": "",
            }

    # Check features
    features: dict[str, dict[str, Any]] = {}
    for fk in ("recommendation", "vision_analysis", "assistant_chat", "voice_asr", "voice_tts", "voice_clone"):
        raw = _query_feature_raw(fk)
        if raw:
            features[fk] = raw
        else:
            default = _FEATURE_DEFAULTS.get(fk, {})
            features[fk] = {
                "enabled": False,
                "default_provider": default.get("default_provider", ""),
                "fallback_order": default.get("fallback_order", []),
            }

    return {
        "db_url_source": db_url_source,
        "db_available": db_available,
        "tables": tables,
        "providers": providers,
        "features": features,
    }


def get_provider_failure_reason(provider_key: str) -> str:
    """Return a non-sensitive diagnostic reason why a provider is unavailable."""
    _, db_url_source = resolve_ai_config_database_url()
    engine = _get_engine()

    if engine is None:
        if db_url_source == "unavailable":
            return f"{provider_key}: AI_CONFIG_DATABASE_URL 未设置，且未找到本地 admin_local.db"
        return f"{provider_key}: 数据库连接失败 ({db_url_source})"

    # Check if table exists
    try:
        from sqlalchemy import MetaData, Table
        metadata = MetaData()
        Table("ai_api_providers", metadata, autoload_with=engine)
    except Exception:
        return f"{provider_key}: ai_api_providers 表不存在"

    # Check if provider exists
    raw = _query_provider_raw(provider_key)
    if not raw:
        return f"{provider_key}: 未在 ai_api_providers 中配置"

    if not raw.get("enabled"):
        return f"{provider_key}: provider 未启用 (enabled=false)"

    if not raw.get("has_api_key"):
        return f"{provider_key}: API Key 未配置"

    if not raw.get("decrypt_ok"):
        return f"{provider_key}: API Key 解密失败"

    return f"{provider_key}: 配置正常，可能是 API 调用失败"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_provider_config(
    provider_key: str,
    *,
    request_api_key: str | None = None,
    request_model: str | None = None,
    request_base_url: str | None = None,
    feature_key: str | None = None,
) -> dict[str, Any]:
    """Resolve full provider config with 5-level fallback.

    Resolution order:
      1. request_api_key / request_model / request_base_url overrides
      2. Admin DB row (enabled rows only; disabled row is *authoritative* — no env fallback)
      3. Environment variables (only when DB row is absent or DB is unreachable)
      4. Code defaults

    feature_key is used to apply the Gemini image-model guard: text features
    (recommendation, vision_analysis, assistant_chat) must not receive a model
    whose name contains '-image' (image-generation models).

    Returns dict: api_key, base_url, default_model, auth_type, auth_header_name,
                  source, db_url_source, failure_reason.
    """
    defaults = _PROVIDER_DEFAULTS.get(provider_key, {})
    env_key_var = defaults.get("env_key_var", "")
    env_base_var = defaults.get("env_base_var", "")

    # Step 1: request override (api_key, model, base_url only — not auth fields)
    api_key = (request_api_key or "").strip()
    model = (request_model or "").strip()
    base_url = (request_base_url or "").strip()

    # Start with code defaults for auth
    auth_type = defaults.get("auth_type", "api_key_header")
    auth_header_name = defaults.get("auth_header_name", "")

    # Step 2: admin DB
    _, db_url_source = resolve_ai_config_database_url()
    db_cfg = _query_provider(provider_key)

    if db_cfg is not None:
        if not db_cfg.get("enabled", True):
            # Row exists but provider is explicitly disabled by admin.
            # env fallback is intentionally NOT applied — disabled means disabled.
            return {
                "api_key": "",
                "base_url": defaults.get("base_url", ""),
                "default_model": defaults.get("default_model", ""),
                "auth_type": auth_type,
                "auth_header_name": auth_header_name,
                "source": "admin_db",
                "db_url_source": db_url_source,
                "failure_reason": f"{provider_key}: provider 已在后台禁用 (enabled=false)",
            }

        # Row exists and is enabled — apply DB values to any fields not already set.
        if not api_key:
            api_key = db_cfg.get("api_key", "")
        if not model:
            model = db_cfg.get("default_model", "")
        if not base_url:
            base_url = db_cfg.get("base_url", "")
        # Auth fields: DB takes priority over code defaults
        db_auth = db_cfg.get("auth_type", "")
        if db_auth:
            auth_type = db_auth
        db_header = db_cfg.get("auth_header_name", "")
        if db_header:
            auth_header_name = db_header

    # Step 3: environment variables (only reached when DB row is absent/unreachable)
    if not api_key and env_key_var:
        api_key = os.getenv(env_key_var, "").strip()
    if not base_url and env_base_var:
        base_url = os.getenv(env_base_var, "").strip()

    # Step 4: code defaults (only for fields still empty)
    if not model:
        model = defaults.get("default_model", "")
    if not base_url:
        base_url = defaults.get("base_url", "")

    # Gemini image-model guard: text/chat features must not use image-gen models.
    # Image-generation Gemini models (e.g. gemini-*-image-preview) cannot process
    # chat or produce JSON profile output — they cause empty/malformed responses.
    if (
        feature_key in _TEXT_FEATURES
        and provider_key == "gemini"
        and "-image" in model.lower()
    ):
        logger.warning(
            "Gemini model '%s' contains '-image' for text feature '%s'; "
            "substituting code-default text model",
            model, feature_key,
        )
        model = _PROVIDER_DEFAULTS.get("gemini", {}).get(
            "default_model", "gemini-3.1-flash-lite-preview"
        )

    # Determine source label for logging (no secrets)
    source = "code_default"
    if request_api_key:
        source = "request_override"
    elif db_cfg is not None and db_cfg.get("api_key"):
        source = "admin_db"
    elif api_key and env_key_var:
        source = "env_var"

    failure_reason = ""
    if not api_key:
        failure_reason = get_provider_failure_reason(provider_key)

    return {
        "api_key": api_key,
        "base_url": base_url,
        "default_model": model,
        "auth_type": auth_type,
        "auth_header_name": auth_header_name,
        "source": source,
        "db_url_source": db_url_source,
        "failure_reason": failure_reason,
    }


def resolve_feature_config(feature_key: str, include_disabled: bool = False) -> dict[str, Any]:
    """Resolve feature config: DB → code defaults.

    Pass include_disabled=True to read disabled features from DB.
    This is essential for voice features — a disabled voice_asr/tts feature
    must be detected so the main site can report it as disabled rather than
    silently falling through to code defaults.
    """
    db_feat = _query_feature(feature_key, include_disabled=include_disabled)
    if db_feat:
        return db_feat
    return _FEATURE_DEFAULTS.get(feature_key, {})


def resolve_effective_provider(
    feature_key: str,
    *,
    request_provider: str | None = None,
) -> tuple[str, list[str]]:
    """Return (effective_provider, fallback_chain) for a feature.

    Rule B: if the feature is explicitly disabled in admin DB (enabled=False),
    returns ("rule", ["rule"]) regardless of request_provider — disabled means
    no AI for this feature.

    If request_provider is set and the feature is enabled, it goes first in
    the chain.  Otherwise the DB/code default_provider is first.
    'rule' in the chain means "stop AI and use rule fallback".
    """
    # include_disabled=True so we detect features explicitly disabled by admin.
    feat = resolve_feature_config(feature_key, include_disabled=True)

    # Rule B: explicitly disabled feature → rule-only chain
    if feat and feat.get("enabled") is False:
        return "rule", ["rule"]

    fallback = list(feat.get("fallback_order", []))
    if request_provider and request_provider.strip():
        pk = request_provider.strip().lower()
        chain = [pk] + [p for p in fallback if p != pk]
        return pk, chain
    default_pk = feat.get("default_provider", "mimo")
    return default_pk, fallback
