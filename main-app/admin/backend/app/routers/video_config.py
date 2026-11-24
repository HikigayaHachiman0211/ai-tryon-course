"""01Router video connection management. Connection tests never generate media."""
import time
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import AdminUser, AIAPIProvider, AIFeatureConfig, get_db
from app.services.secret_crypto import encrypt_secret, decrypt_secret

LIVE_BASE_URL = "https://01router.com/api/v1"
SANDBOX_BASE_URL = "https://01router.com/api/sandbox/v1"
router = APIRouter(prefix="/api/ai-config/video", tags=["ai-video-config"])


class VideoConfigUpdate(BaseModel):
    enabled: bool | None = None
    base_url: Literal["https://01router.com/api/v1", "https://01router.com/api/sandbox/v1"] | None = None
    api_key: str | None = Field(default=None, max_length=1024)
    clear_api_key: bool = False
    project_id: str | None = Field(default=None, max_length=160, pattern=r"^[A-Za-z0-9_-]*$")
    timeout_seconds: int | None = Field(default=None, ge=10, le=120)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=1000)
    daily_quota_limit: int | None = Field(default=None, ge=1, le=100000)


def _rows(db):
    return (db.query(AIAPIProvider).filter_by(provider_key="01router").first(),
            db.query(AIFeatureConfig).filter_by(feature_key="tryon_video").first())


@router.get("")
def get_config(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    provider, feature = _rows(db)
    return {"enabled": bool(provider and provider.enabled and feature and feature.enabled),
            "base_url": (provider.base_url if provider else None) or LIVE_BASE_URL,
            "has_api_key": bool(provider and provider.api_key_encrypted),
            "project_id": str((feature.config or {}).get("project_id") or "") if feature else "",
            "timeout_seconds": (provider.timeout_seconds if provider else None) or 60,
            "rate_limit_per_minute": (provider.rate_limit_per_minute if provider else None) or 3,
            "daily_quota_limit": (provider.daily_quota_limit if provider else None) or 20}


@router.put("")
def update_config(body: VideoConfigUpdate, admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    provider, feature = _rows(db)
    if provider is None:
        provider = AIAPIProvider(provider_key="01router", display_name="01Router Video", category="video", enabled=True,
                                 base_url=LIVE_BASE_URL, auth_type="bearer", timeout_seconds=60, retry_count=0,
                                 rate_limit_per_minute=3, daily_quota_limit=20)
        db.add(provider)
    if feature is None:
        feature = AIFeatureConfig(feature_key="tryon_video", enabled=True, default_provider="01router", config={})
        db.add(feature)
    if body.enabled is not None:
        provider.enabled = feature.enabled = body.enabled
    for field in ("base_url", "timeout_seconds", "rate_limit_per_minute", "daily_quota_limit"):
        value = getattr(body, field)
        if value is not None:
            setattr(provider, field, value)
    if body.clear_api_key:
        provider.api_key_encrypted = None
    elif body.api_key and body.api_key.strip():
        provider.api_key_encrypted = encrypt_secret(body.api_key.strip())
    if body.project_id is not None:
        feature.config = {**(feature.config or {}), "project_id": body.project_id.strip()}
    provider.retry_count = 0
    provider.updated_by = feature.updated_by = admin.username
    db.commit()
    return get_config(admin=admin, db=db)


@router.post("/test")
async def test_config(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    provider, feature = _rows(db)
    if not provider or not provider.api_key_encrypted:
        raise HTTPException(400, "Configure the 01Router API key first")
    base = provider.base_url or LIVE_BASE_URL
    if base not in {LIVE_BASE_URL, SANDBOX_BASE_URL}:
        raise HTTPException(400, "Use the official 01Router API URL")
    try:
        key = decrypt_secret(provider.api_key_encrypted)
    except Exception:
        raise HTTPException(400, "The saved API key cannot be decrypted; save it again")
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=provider.timeout_seconds or 60, follow_redirects=False) as client:
            response = await client.get(base + "/generations", params={"limit": 1}, headers={"Authorization": f"Bearer {key}"})
        status = response.status_code
        success = status == 200
    except httpx.RequestError:
        status, success = 0, False
    return {"success": success, "status_code": status, "latency_ms": round((time.monotonic() - start) * 1000),
            "message": "OK" if success else f"01Router connection failed (HTTP {status})"}
