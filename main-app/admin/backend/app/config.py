from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./admin_local.db"
    GCS_BUCKET_NAME: str = ""
    JWT_SECRET_KEY: str = "replace-with-a-32-character-secret"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24
    ADMIN_INIT_USERNAME: str = "admin"
    ADMIN_INIT_PASSWORD: str = "replace-with-admin-password"
    MAIN_SITE_URL: str = "http://localhost:8000"
    TRYON_WORKBENCH_URL: str = ""
    PUBLIC_IMAGE_BASE_URL: str = ""
    CORS_ALLOW_ORIGINS: str = "*"
    GEMINI_API_KEY: str = ""
    INGEST_SECRET_KEY: str = "replace-with-ingest-secret"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
