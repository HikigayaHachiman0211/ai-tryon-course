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
_CLOUD_ROOT = Path(__file__).resolve().parent.parent  # tryon-workbench/
_PROJECT_ROOT = _CLOUD_ROOT.parent
_LOCAL_ADMIN_DB = _PROJECT_ROOT / "main-app" / "admin" / "backend" / "admin_local.db"


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


def _encrypt_secret(value: str) -> str:
    """Encrypt a secret string using the same contract as admin secret_crypto.py."""
    if not value:
        return ""
    f = _get_fernet()
    if f is not None:
        return "fernet:" + f.encrypt(value.encode("utf-8")).decode("ascii")
    if _is_production():
        raise RuntimeError(
            "Cannot encrypt secret: FERNET_SECRET_KEY is not set in production."
        )
    return "b64:" + base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")


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


from app.tryon_options import build_runtime_providers_catalog


def _parse_model_options_value(raw_opts: Any) -> list[str]:
    if isinstance(raw_opts, str):
        try:
            raw_opts = _json.loads(raw_opts)
        except Exception:
            raw_opts = []
    if not isinstance(raw_opts, list):
        return []
    return [str(item).strip() for item in raw_opts if str(item or "").strip()]


def _parse_provider_row(
    row: Any,
    *,
    fallback_key: str,
    default_base_url: str,
    default_timeout: int,
    has_default_model_col: bool,
    has_model_options_col: bool,
) -> dict[str, Any]:
    if row is None:
        return {
            "provider_key": fallback_key,
            "enabled": False,
            "configured": False,
            "api_key": "",
            "base_url": default_base_url,
            "timeout_seconds": default_timeout,
            "retry_count": 1,
            "default_model": "",
            "models": [],
        }

    api_key = ""
    encrypted = row[1]
    if encrypted:
        try:
            api_key = _decrypt_secret(encrypted)
        except Exception as exc:
            logger.warning("Cannot decrypt %s provider key: %s", fallback_key, exc)

    idx_default = 7 if has_default_model_col else None
    idx_opts = 7 + (1 if has_default_model_col else 0)
    default_model = str(row[idx_default] or "").strip() if idx_default is not None and len(row) > idx_default else ""
    models = _parse_model_options_value(row[idx_opts]) if has_model_options_col and len(row) > idx_opts else []
    if default_model and default_model not in models:
        models.insert(0, default_model)

    enabled = bool(row[2])
    base_url = str(row[6] or default_base_url).strip() or default_base_url
    timeout_val = max(10, min(int(row[3] or default_timeout), 300))
    retry_val = int(row[4] if row[4] is not None else 1)
    return {
        "provider_key": str(row[0] or fallback_key).strip() or fallback_key,
        "enabled": enabled,
        "configured": bool(enabled and api_key),
        "api_key": api_key,
        "base_url": base_url,
        "timeout_seconds": timeout_val,
        "retry_count": retry_val,
        "default_model": default_model,
        "models": models,
    }


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

        # Read feature (include disabled)
        feat_stmt = (
            select(
                features.c.enabled,
                features.c.config,
                features.c.updated_at,
                features.c.default_model,
                features.c.default_provider,
            )
            .where(features.c.feature_key == "tryon")
        )

        with engine.connect() as conn:
            feat_row = conn.execute(feat_stmt).fetchone()
            provider_key = str(feat_row[4] or "gemini").strip() if feat_row else "gemini"
            if provider_key not in {"gemini", "totokens"}:
                provider_key = "unsupported"
            prov_cols = [
                providers.c.provider_key,
                providers.c.api_key_encrypted,
                providers.c.enabled,
                providers.c.timeout_seconds,
                providers.c.retry_count,
                providers.c.updated_at,
                providers.c.base_url,
            ]
            has_default_model_col = "default_model" in providers.c
            has_model_options_col = "model_options" in providers.c
            if has_default_model_col:
                prov_cols.append(providers.c.default_model)
            if has_model_options_col:
                prov_cols.append(providers.c.model_options)
            wanted_keys = ["gemini", "totokens"]
            if provider_key not in wanted_keys and provider_key != "unsupported":
                wanted_keys.append(provider_key)
            prov_stmt = select(*prov_cols).where(providers.c.provider_key.in_(wanted_keys))
            rows_by_key = {row[0]: row for row in conn.execute(prov_stmt).fetchall()}
            prov_row = rows_by_key.get(provider_key)
            gemini_row = rows_by_key.get("gemini")
            relay_row = rows_by_key.get("totokens")

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

        gemini_entry = _parse_provider_row(
            gemini_row,
            fallback_key="gemini",
            default_base_url="",
            default_timeout=60,
            has_default_model_col=has_default_model_col,
            has_model_options_col=has_model_options_col,
        )
        relay_entry = _parse_provider_row(
            relay_row,
            fallback_key="totokens",
            default_base_url="https://totokens.cc",
            default_timeout=120,
            has_default_model_col=has_default_model_col,
            has_model_options_col=has_model_options_col,
        )
        primary_entry = relay_entry if provider_key == "totokens" else gemini_entry
        api_key = primary_entry["api_key"]

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
        provider_enabled = bool(primary_entry["enabled"])
        feature_enabled = bool(feat_row[0])
        if provider_key == "totokens":
            flash_model = str(feat_config.get("totokens_flash_model") or "gemini-3.1-flash-image").strip()
            pro_model = str(feat_config.get("totokens_pro_model") or "gpt-image-2").strip()
        else:
            flash_model = str(feat_config.get("flash_model") or feat_row[3] or "").strip()
            pro_model = str(feat_config.get("pro_model") or "").strip()

        # Resolve ToTokens relay availability alongside primary provider (legacy key + multi-API profiles)
        from app.tryon_options import extract_totokens_profiles

        relay_api_key = relay_entry["api_key"]
        relay_enabled = bool(relay_entry["enabled"])
        relay_base_url = str(relay_entry["base_url"] or "https://totokens.cc").strip() or "https://totokens.cc"
        relay_timeout_seconds = int(relay_entry["timeout_seconds"] or 120)

        decrypted_apis: list[dict[str, Any]] = []
        raw_totokens_apis = feat_config.get("totokens_apis")
        if isinstance(raw_totokens_apis, list):
            for entry in raw_totokens_apis:
                if not isinstance(entry, dict):
                    continue
                item = dict(entry)
                enc_key = item.pop("api_key_encrypted", None)
                plain_key = ""
                if enc_key:
                    try:
                        plain_key = _decrypt_secret(enc_key)
                    except Exception as exc:
                        logger.warning("Cannot decrypt ToTokens profile %s key: %s", item.get("id"), exc)
                item["api_key"] = plain_key
                decrypted_apis.append(item)

        totokens_apis_internal = extract_totokens_profiles({
            "totokens_apis_internal": decrypted_apis,
            "providers_internal": {"totokens": relay_entry},
        })
        any_profile_key = any(bool(p.get("enabled") and p.get("api_key")) for p in totokens_apis_internal)
        merged_relay_models = list(relay_entry["models"])
        for prof in totokens_apis_internal:
            for cand in [prof.get("default_model", ""), *(prof.get("models") or [])]:
                clean_m = str(cand or "").strip()
                if clean_m and clean_m not in merged_relay_models:
                    merged_relay_models.append(clean_m)
        relay_entry["models"] = merged_relay_models
        relay_entry["api_profiles"] = totokens_apis_internal
        relay_entry["configured"] = bool(relay_enabled and (relay_api_key or any_profile_key))

        relay_default_gpt = ""
        for cand in relay_entry["models"]:
            low = cand.lower()
            if "gpt" in low or "chatgpt" in low:
                relay_default_gpt = cand
                break

        chatgpt_model = str(
            feat_config.get("totokens_chatgpt_model")
            or feat_config.get("totokens_pro_model")
            or relay_default_gpt
            or "gpt-image-2"
        ).strip()
        relay_configured = bool(feature_enabled and relay_enabled and (relay_api_key or any_profile_key))
        gemini_configured = bool(feature_enabled and gemini_entry["configured"])
        any_provider_active = bool(provider_enabled or relay_configured or gemini_configured)

        return {
            "enabled": feature_enabled and any_provider_active,
            "feature_enabled": feature_enabled,
            "provider_enabled": provider_enabled,
            "provider_key": provider_key,
            "base_url": str(primary_entry["base_url"] or "").strip(),
            "api_key": api_key,
            "flash_model": flash_model,
            "pro_model": pro_model,
            "timeout_seconds": int(prov_row[3] or 60),
            "retry_count": int(prov_row[4] if prov_row[4] is not None else 1),
            "relay_enabled": relay_enabled,
            "relay_configured": relay_configured,
            "relay_base_url": relay_base_url,
            "relay_api_key": relay_api_key,
            "relay_timeout_seconds": relay_timeout_seconds,
            "chatgpt_model": chatgpt_model,
            "totokens_apis_internal": totokens_apis_internal,
            "providers_internal": {
                "gemini": gemini_entry,
                "totokens": relay_entry,
            },
            "config_cache_seconds": cache_ttl,
            "source": "admin_db",
            "updated_at": feat_row[2].isoformat() if feat_row[2] else None,
            "config_error": (
                "feature_disabled"
                if not feature_enabled
                else "provider_disabled"
                if not any_provider_active
                else "api_key_unavailable"
                if (not api_key and not relay_configured and not gemini_configured)
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

    flash_model = os.getenv("TRYON_FLASH_MODEL", "gemini-3.1-flash-image-preview").strip()
    pro_model = os.getenv("TRYON_PRO_MODEL", "gemini-3-pro-image-preview").strip()
    return {
        "enabled": True,
        "provider_key": "gemini",
        "provider_enabled": True,
        "api_key": api_key,
        "flash_model": flash_model,
        "pro_model": pro_model,
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
        has_relay_meta = any(
            key in config
            for key in ("provider_key", "relay_enabled", "relay_configured", "chatgpt_model", "providers_internal", "totokens_apis_internal")
        )
        models = []
        if config.get("flash_model"):
            models.append("flash")
        if config.get("pro_model"):
            models.append("pro")
        status: dict[str, Any] = {
            "tryon_enabled": config.get("enabled", False),
            "configured": bool(config.get("api_key")),
            "available_models": models,
            "config_source": config.get("source", "unknown"),
        }
        if not has_relay_meta:
            return status

        provider_key = str(config.get("provider_key") or "gemini").strip()
        any_profile_key = any(
            bool(p.get("enabled") and (p.get("api_key") or p.get("configured")))
            for p in (config.get("totokens_apis_internal") or [])
            if isinstance(p, dict)
        )
        relay_configured = bool(config.get("relay_configured")) or (
            provider_key == "totokens" and (bool(config.get("api_key")) or any_profile_key)
        )
        relay_enabled = bool(config.get("relay_enabled")) or (
            provider_key == "totokens" and bool(config.get("enabled"))
        )
        chatgpt_model = str(
            config.get("chatgpt_model")
            or (config.get("pro_model") if provider_key == "totokens" else "")
            or "gpt-image-2"
        ).strip()
        primary_configured = bool(config.get("api_key")) and config.get("provider_enabled", True)

        if provider_key == "totokens":
            pro_raw = str(config.get("pro_model") or "").strip().lower()
            pro_is_gpt = "gpt" in pro_raw or "chatgpt" in pro_raw
            ui_models = []
            if config.get("flash_model"):
                ui_models.append("flash")
            if config.get("pro_model") and not pro_is_gpt:
                ui_models.append("pro")
            if relay_configured and chatgpt_model:
                ui_models.append("chatgpt")
            status["available_models"] = ui_models
            status["model_labels"] = {
                "flash": config.get("flash_model", ""),
                "pro": config.get("pro_model", ""),
                "chatgpt": chatgpt_model,
            }
        else:
            ui_models = []
            if primary_configured and config.get("flash_model"):
                ui_models.append("flash")
            if primary_configured and config.get("pro_model"):
                ui_models.append("pro")
            if relay_configured and chatgpt_model:
                ui_models.append("chatgpt")
            status["available_models"] = ui_models
            status["model_labels"] = {
                "flash": config.get("flash_model", ""),
                "pro": config.get("pro_model", ""),
                "chatgpt": chatgpt_model,
            }

        catalog = build_runtime_providers_catalog(config)
        any_configured = any(bool(item.get("configured")) for item in catalog.get("providers") or [])

        status["provider_key"] = provider_key
        status["configured"] = primary_configured or relay_configured or any_configured
        status["relay_enabled"] = relay_enabled
        status["relay_configured"] = relay_configured
        status["chatgpt_configured"] = relay_configured
        status["chatgpt_model"] = chatgpt_model
        status.update(catalog)
        return status
    except Exception as exc:
        logger.warning("Tryon runtime config status unavailable: %s", exc)
        return {
            "tryon_enabled": False,
            "configured": False,
            "available_models": [],
            "config_source": "unavailable",
        }
