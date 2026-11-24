"""Server-only 01Router connection settings, shared with the admin configuration."""
from __future__ import annotations

import json
import os
import threading
import time

from app.admin_runtime_config import _decrypt_secret, _get_engine

LIVE_BASE_URL = "https://01router.com/api/v1"
SANDBOX_BASE_URL = "https://01router.com/api/sandbox/v1"
_cache = None
_cached_at = 0.0
_lock = threading.Lock()


def normalize_base_url(value: str) -> str:
    cleaned = str(value or LIVE_BASE_URL).strip().rstrip("/")
    if cleaned not in {LIVE_BASE_URL, SANDBOX_BASE_URL}:
        raise ValueError("01Router Base URL must be the official live or sandbox API URL")
    return cleaned


def _read_video_config():
    engine = _get_engine()
    if engine is None:
        return None
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            provider = conn.execute(text("SELECT enabled, api_key_encrypted, base_url, timeout_seconds, rate_limit_per_minute, daily_quota_limit FROM ai_api_providers WHERE provider_key='01router'")).mappings().first()
            feature = conn.execute(text("SELECT enabled, config FROM ai_feature_configs WHERE feature_key='tryon_video'")).mappings().first()
    except Exception:
        return None
    if provider is None and feature is None:
        return None
    options = (feature or {}).get("config") or {}
    if isinstance(options, str):
        options = json.loads(options)
    cfg = dict(options)
    cfg.update({"enabled": bool(provider and provider["enabled"] and feature and feature["enabled"]),
                "base_url": (provider or {}).get("base_url") or LIVE_BASE_URL,
                "timeout_seconds": (provider or {}).get("timeout_seconds") or 60,
                "rate_limit_per_minute": (provider or {}).get("rate_limit_per_minute") or 3,
                "daily_quota_limit": (provider or {}).get("daily_quota_limit") or 20,
                "api_key": "", "source": "admin_db"})
    if provider and provider["api_key_encrypted"]:
        try:
            cfg["api_key"] = _decrypt_secret(provider["api_key_encrypted"])
        except Exception:
            cfg["enabled"] = False
    return cfg


def clear_config_cache():
    global _cache, _cached_at
    with _lock:
        _cache, _cached_at = None, 0.0


def resolve_video_config():
    global _cache, _cached_at
    with _lock:
        if _cache is not None and time.monotonic() - _cached_at < 15:
            return dict(_cache)
        cfg = _read_video_config()
        if cfg is None:
            cfg = {"enabled": os.getenv("ROUTER01_ENABLED", "true").lower() in {"true", "1", "yes"},
                   "base_url": os.getenv("ROUTER01_BASE_URL", LIVE_BASE_URL),
                   "api_key": os.getenv("ROUTER01_API_KEY", "").strip(),
                   "project_id": os.getenv("ROUTER01_PROJECT_ID", "").strip(),
                   "timeout_seconds": 60, "rate_limit_per_minute": 3, "daily_quota_limit": 20,
                   "source": "environment"}
        cfg["base_url"] = normalize_base_url(cfg.get("base_url"))
        cfg["project_id"] = str(cfg.get("project_id") or "").strip()
        _cache, _cached_at = dict(cfg), time.monotonic()
        return cfg
