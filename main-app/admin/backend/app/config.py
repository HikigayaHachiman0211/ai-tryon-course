from __future__ import annotations

import os
import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings

# Local development gets a process-local JWT key so no reusable secret is
# committed to source control. Production validation rejects this ephemeral
# value and requires an injected JWT_SECRET_KEY.
_EPHEMERAL_DEV_JWT_SECRET = secrets.token_urlsafe(48)
_DEFAULT_ADMIN_PASSWORD = ""
_DEFAULT_INGEST_KEY = ""


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./admin_local.db"
    GCS_BUCKET_NAME: str = ""
    JWT_SECRET_KEY: str = _EPHEMERAL_DEV_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24
    ADMIN_INIT_USERNAME: str = "admin"
    ADMIN_INIT_PASSWORD: str = _DEFAULT_ADMIN_PASSWORD
    MAIN_SITE_URL: str = "http://localhost:8000"
    TRYON_WORKBENCH_URL: str = ""
    PUBLIC_IMAGE_BASE_URL: str = ""
    CORS_ALLOW_ORIGINS: str = "*"
    GEMINI_API_KEY: str = ""
    INGEST_SECRET_KEY: str = _DEFAULT_INGEST_KEY
    APP_ENV: str = "development"
    FERNET_SECRET_KEY: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def is_production() -> bool:
    """True when running in a production environment.

    Mirrors secret_crypto._is_production(): Cloud Run (K_SERVICE set) or
    APP_ENV/ENV equal to 'production' or 'prod'.
    """
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


def validate_production_settings(settings: Settings) -> list[str]:
    """Return a list of security issues found in settings.

    Returns an empty list in dev mode or when all settings are safe.
    Never prints or logs secret values.
    """
    if not is_production():
        return []

    issues: list[str] = []
    if settings.JWT_SECRET_KEY == _EPHEMERAL_DEV_JWT_SECRET or len(settings.JWT_SECRET_KEY) < 32:
        issues.append(
            "JWT_SECRET_KEY is missing, ephemeral, or too short (<32 chars) — "
            "admin tokens can be forged. Set a strong secret in JWT_SECRET_KEY."
        )
    if not settings.ADMIN_INIT_PASSWORD or len(settings.ADMIN_INIT_PASSWORD) < 12:
        issues.append(
            "ADMIN_INIT_PASSWORD is missing or too short (<12 chars) — "
            "set a strong initial administrator password."
        )
    if settings.CORS_ALLOW_ORIGINS.strip() == "*":
        issues.append(
            "CORS_ALLOW_ORIGINS='*' in production — restricting to same-origin. "
            "Set CORS_ALLOW_ORIGINS to the real admin frontend URL."
        )
    if not settings.INGEST_SECRET_KEY or len(settings.INGEST_SECRET_KEY) < 32:
        issues.append(
            "INGEST_SECRET_KEY is missing or too short (<32 chars) — anyone can write fake analytics. "
            "Set a strong secret in INGEST_SECRET_KEY."
        )
    if not settings.FERNET_SECRET_KEY:
        issues.append(
            "FERNET_SECRET_KEY is missing — stored provider API keys cannot be encrypted safely. "
            "Set FERNET_SECRET_KEY before enabling provider configuration."
        )
    return issues
