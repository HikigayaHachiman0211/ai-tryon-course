from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import AIAPIProvider, AIFeatureConfig, AIAPITestLog, AdminUser, get_db
from app.services.secret_crypto import (
    decrypt_secret,
    mask_secret,
    sanitize_error_message,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai-config", tags=["ai-config"])


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class ProviderCreateRequest(BaseModel):
    provider_key: str
    display_name: str
    category: str = "llm"
    enabled: bool = True
    is_default: bool = False
    base_url: str | None = None
    api_key: str | None = None  # plaintext, will be encrypted
    auth_type: str = "api_key_header"
    auth_header_name: str | None = None
    default_model: str | None = None
    model_options: list[str] | None = None
    timeout_seconds: int = 30
    retry_count: int = 1
    rate_limit_per_minute: int | None = None
    daily_quota_limit: int | None = None
    cost_note: str | None = None
    notes: str | None = None


class ProviderUpdateRequest(BaseModel):
    display_name: str | None = None
    category: str | None = None
    enabled: bool | None = None
    is_default: bool | None = None
    base_url: str | None = None
    api_key: str | None = None  # None/empty/whitespace = don't update
    clear_api_key: bool = False  # must be True explicitly to clear the key
    auth_type: str | None = None
    auth_header_name: str | None = None
    default_model: str | None = None
    model_options: list[str] | None = None
    timeout_seconds: int | None = None
    retry_count: int | None = None
    rate_limit_per_minute: int | None = None
    daily_quota_limit: int | None = None
    cost_note: str | None = None
    notes: str | None = None


class FeatureUpdateRequest(BaseModel):
    enabled: bool | None = None
    default_provider: str | None = None
    fallback_order: list[str] | None = None
    default_model: str | None = None
    config: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_provider(p: AIAPIProvider) -> dict:
    has_key = bool(p.api_key_encrypted)
    key_masked = ""
    key_status = "ok"

    if has_key:
        try:
            plain = decrypt_secret(p.api_key_encrypted)
            key_masked = mask_secret(plain)
        except Exception as exc:
            logger.warning("Decrypt failed for provider %s: %s", p.provider_key, exc)
            key_masked = "****"
            key_status = "decrypt_failed"

    result = {
        "id": p.id,
        "provider_key": p.provider_key,
        "display_name": p.display_name,
        "category": p.category,
        "enabled": p.enabled,
        "is_default": p.is_default,
        "base_url": p.base_url,
        "api_key_masked": key_masked,
        "has_api_key": has_key,
        "auth_type": p.auth_type,
        "auth_header_name": p.auth_header_name,
        "default_model": p.default_model,
        "model_options": p.model_options,
        "timeout_seconds": p.timeout_seconds,
        "retry_count": p.retry_count,
        "rate_limit_per_minute": p.rate_limit_per_minute,
        "daily_quota_limit": p.daily_quota_limit,
        "cost_note": p.cost_note,
        "notes": p.notes,
        "last_test_status": p.last_test_status,
        "last_test_message": p.last_test_message,
        "last_test_at": p.last_test_at.isoformat() if p.last_test_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "updated_by": p.updated_by,
    }
    if key_status != "ok":
        result["key_status"] = key_status
    return result


def _serialize_feature(f: AIFeatureConfig) -> dict:
    return {
        "id": f.id,
        "feature_key": f.feature_key,
        "enabled": f.enabled,
        "default_provider": f.default_provider,
        "fallback_order": f.fallback_order,
        "default_model": f.default_model,
        "config": f.config,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
        "updated_by": f.updated_by,
    }


def _now_beijing():
    return datetime.now(ZoneInfo("Asia/Shanghai"))


# ---------------------------------------------------------------------------
# Provider CRUD
# ---------------------------------------------------------------------------

@router.get("/providers")
def list_providers(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    providers = db.query(AIAPIProvider).order_by(AIAPIProvider.id).all()
    return [_serialize_provider(p) for p in providers]


@router.post("/providers")
def create_provider(
    body: ProviderCreateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    existing = db.query(AIAPIProvider).filter_by(provider_key=body.provider_key).first()
    if existing:
        raise HTTPException(400, f"provider_key '{body.provider_key}' already exists")

    from app.services.secret_crypto import encrypt_secret

    encrypted_key = None
    if body.api_key:
        try:
            encrypted_key = encrypt_secret(body.api_key)
        except RuntimeError as exc:
            raise HTTPException(400, detail=f"无法加密 API Key: {exc}")

    p = AIAPIProvider(
        provider_key=body.provider_key,
        display_name=body.display_name,
        category=body.category,
        enabled=body.enabled,
        is_default=body.is_default,
        base_url=body.base_url,
        api_key_encrypted=encrypted_key,
        auth_type=body.auth_type,
        auth_header_name=body.auth_header_name,
        default_model=body.default_model,
        model_options=body.model_options,
        timeout_seconds=body.timeout_seconds,
        retry_count=body.retry_count,
        rate_limit_per_minute=body.rate_limit_per_minute,
        daily_quota_limit=body.daily_quota_limit,
        cost_note=body.cost_note,
        notes=body.notes,
        updated_by=admin.username,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _serialize_provider(p)


@router.put("/providers/{provider_id}")
def update_provider(
    provider_id: int,
    body: ProviderUpdateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    p = db.get(AIAPIProvider, provider_id)
    if not p:
        raise HTTPException(404, "Provider not found")

    from app.services.secret_crypto import encrypt_secret

    data = body.model_dump(exclude_unset=True)
    api_key_value = data.pop("api_key", None)
    clear_api_key = data.pop("clear_api_key", False)

    for k, v in data.items():
        setattr(p, k, v)

    # Only update api_key if a non-empty value is provided, or clear_api_key=True
    if clear_api_key:
        p.api_key_encrypted = None
    elif api_key_value and api_key_value.strip():
        try:
            p.api_key_encrypted = encrypt_secret(api_key_value.strip())
        except RuntimeError as exc:
            raise HTTPException(400, detail=f"无法加密 API Key: {exc}")
    # else: empty/None/whitespace → keep existing key

    p.updated_at = _now_beijing()
    p.updated_by = admin.username
    db.commit()
    db.refresh(p)
    return _serialize_provider(p)


@router.delete("/providers/{provider_id}")
def delete_provider(
    provider_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    p = db.get(AIAPIProvider, provider_id)
    if not p:
        raise HTTPException(404, "Provider not found")
    # Always soft-disable — never hard delete to preserve config history
    p.enabled = False
    p.updated_at = _now_beijing()
    p.updated_by = admin.username
    db.commit()
    return {"status": "disabled"}


# ---------------------------------------------------------------------------
# Provider test
# ---------------------------------------------------------------------------

@router.post("/providers/{provider_id}/test")
async def test_provider(
    provider_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    p = db.get(AIAPIProvider, provider_id)
    if not p:
        raise HTTPException(404, "Provider not found")

    # Decrypt API key — catch failures gracefully
    api_key = ""
    try:
        api_key = decrypt_secret(p.api_key_encrypted) if p.api_key_encrypted else ""
    except Exception as exc:
        logger.warning("Decrypt failed for provider %s test: %s", p.provider_key, exc)

    base_url = (p.base_url or "").rstrip("/")
    model = p.default_model or ""
    success = False
    latency_ms = 0.0
    status_code = 0
    error_code = ""
    error_message = ""

    if not api_key and p.api_key_encrypted:
        error_message = "API Key 解密失败，请重新保存 Key"
    elif not base_url:
        error_message = "Base URL not configured"
    elif not api_key:
        error_message = "API Key not configured"
    elif p.category in ("asr", "tts", "voice_clone"):
        # Config completeness check only for non-LLM categories
        success = True
        error_message = "Config completeness check passed (no live test for this category)"
    else:
        # Live test: send a minimal chat/completions request
        import time

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if p.auth_type == "bearer":
            headers["Authorization"] = f"Bearer {api_key}"
        elif p.auth_type == "api_key_header":
            header_name = p.auth_header_name or "api-key"
            headers[header_name] = api_key

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
            "stream": False,
        }
        url = f"{base_url}/chat/completions"

        try:
            start = time.time()
            async with httpx.AsyncClient(timeout=p.timeout_seconds or 30) as client:
                resp = await client.post(url, json=payload, headers=headers)
            latency_ms = round((time.time() - start) * 1000, 1)
            status_code = resp.status_code
            if resp.status_code == 200:
                success = True
                error_message = "OK"
            else:
                error_message = sanitize_error_message(resp.text[:300])
        except Exception as exc:
            error_message = sanitize_error_message(str(exc))

    # Save test log
    log = AIAPITestLog(
        provider_key=p.provider_key,
        test_type="connection",
        success=success,
        latency_ms=latency_ms,
        status_code=status_code,
        error_code=error_code,
        error_message_sanitized=error_message,
        created_by=admin.username,
    )
    db.add(log)

    p.last_test_status = "success" if success else "failed"
    p.last_test_message = error_message
    p.last_test_at = _now_beijing()
    db.commit()

    return {
        "success": success,
        "latency_ms": latency_ms,
        "status_code": status_code,
        "message": error_message,
    }


# ---------------------------------------------------------------------------
# Feature config
# ---------------------------------------------------------------------------

@router.get("/features")
def list_features(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    features = db.query(AIFeatureConfig).order_by(AIFeatureConfig.id).all()
    return [_serialize_feature(f) for f in features]


@router.put("/features/{feature_key}")
def update_feature(
    feature_key: str,
    body: FeatureUpdateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    f = db.query(AIFeatureConfig).filter_by(feature_key=feature_key).first()
    if not f:
        raise HTTPException(404, f"Feature '{feature_key}' not found")

    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(f, k, v)
    f.updated_at = _now_beijing()
    f.updated_by = admin.username
    db.commit()
    db.refresh(f)
    return _serialize_feature(f)


# ---------------------------------------------------------------------------
# Tryon-specific management endpoints
# ---------------------------------------------------------------------------

class TryonConfigUpdateRequest(BaseModel):
    enabled: bool | None = None
    api_key: str | None = None  # None/empty/whitespace = don't update
    clear_api_key: bool = False
    flash_model: str | None = None
    pro_model: str | None = None
    timeout_seconds: int | None = None
    retry_count: int | None = None


_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


def _validate_tryon_model_id(value: str, label: str) -> str:
    model = value.strip()
    if not model:
        raise HTTPException(400, detail=f"{label}模型 ID 不能为空")
    if not _MODEL_ID_RE.fullmatch(model):
        raise HTTPException(400, detail=f"{label}模型 ID 格式无效")
    return model


def _get_tryon_provider(db: Session) -> AIAPIProvider | None:
    return db.query(AIAPIProvider).filter_by(provider_key="gemini").first()


def _get_tryon_feature(db: Session) -> AIFeatureConfig | None:
    return db.query(AIFeatureConfig).filter_by(feature_key="tryon").first()


@router.get("/tryon")
def get_tryon_config(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Get tryon-specific configuration. No key or mask is returned."""
    provider = _get_tryon_provider(db)
    feature = _get_tryon_feature(db)

    if not provider:
        raise HTTPException(404, "Gemini provider not found")
    if not feature:
        raise HTTPException(404, "Tryon feature not found")

    has_key = bool(provider.api_key_encrypted)
    key_status = "ok"
    if has_key:
        try:
            decrypt_secret(provider.api_key_encrypted)
        except Exception:
            key_status = "decrypt_failed"

    config = feature.config or {}
    return {
        "feature_key": "tryon",
        "enabled": feature.enabled,
        "provider_key": "gemini",
        "provider_enabled": provider.enabled,
        "has_api_key": has_key,
        "key_status": key_status,
        "flash_model": config.get("flash_model", ""),
        "pro_model": config.get("pro_model", ""),
        "timeout_seconds": provider.timeout_seconds,
        "retry_count": provider.retry_count,
        "updated_at": feature.updated_at.isoformat() if feature.updated_at else None,
        "updated_by": feature.updated_by,
        "last_test_status": provider.last_test_status,
        "last_test_message": provider.last_test_message,
        "last_test_at": provider.last_test_at.isoformat() if provider.last_test_at else None,
    }


@router.put("/tryon")
def update_tryon_config(
    body: TryonConfigUpdateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Update tryon configuration. Provider and Feature updated in one transaction."""
    provider = _get_tryon_provider(db)
    feature = _get_tryon_feature(db)

    if not provider:
        raise HTTPException(404, "Gemini provider not found")
    if not feature:
        raise HTTPException(404, "Tryon feature not found")

    from app.services.secret_crypto import encrypt_secret

    if body.clear_api_key:
        provider.api_key_encrypted = None
    elif body.api_key and body.api_key.strip():
        try:
            provider.api_key_encrypted = encrypt_secret(body.api_key.strip())
        except RuntimeError as exc:
            raise HTTPException(400, detail=f"无法加密 API Key: {exc}")

    if body.timeout_seconds is not None:
        if not 10 <= body.timeout_seconds <= 300:
            raise HTTPException(400, detail="超时秒数必须在 10 到 300 之间")
        provider.timeout_seconds = body.timeout_seconds
    if body.retry_count is not None:
        if not 0 <= body.retry_count <= 5:
            raise HTTPException(400, detail="重试次数必须在 0 到 5 之间")
        provider.retry_count = body.retry_count

    # Update feature config
    if body.enabled is not None:
        feature.enabled = body.enabled

    config = dict(feature.config or {})
    if body.flash_model is not None:
        config["flash_model"] = _validate_tryon_model_id(body.flash_model, "Flash ")
    if body.pro_model is not None:
        config["pro_model"] = _validate_tryon_model_id(body.pro_model, "Pro ")
    feature.config = config

    now = _now_beijing()
    provider.updated_at = now
    provider.updated_by = admin.username
    feature.updated_at = now
    feature.updated_by = admin.username

    # Validate: if enabled, must have a key
    if feature.enabled:
        if not provider.enabled:
            db.rollback()
            raise HTTPException(
                400,
                detail="Gemini Provider 当前已停用，请先在 Provider 管理中启用后再开启试衣功能",
            )
        if not provider.api_key_encrypted:
            db.rollback()
            raise HTTPException(400, detail="启用试衣功能时必须配置 API Key")
        try:
            decrypt_secret(provider.api_key_encrypted)
        except Exception:
            db.rollback()
            raise HTTPException(400, detail="API Key 无法解密，请重新保存 Key 后再启用")

    db.commit()
    db.refresh(provider)
    db.refresh(feature)

    has_key = bool(provider.api_key_encrypted)
    key_status = "ok"
    if has_key:
        try:
            decrypt_secret(provider.api_key_encrypted)
        except Exception:
            key_status = "decrypt_failed"

    return {
        "feature_key": "tryon",
        "enabled": feature.enabled,
        "provider_key": "gemini",
        "provider_enabled": provider.enabled,
        "has_api_key": has_key,
        "key_status": key_status,
        "flash_model": (feature.config or {}).get("flash_model", ""),
        "pro_model": (feature.config or {}).get("pro_model", ""),
        "timeout_seconds": provider.timeout_seconds,
        "retry_count": provider.retry_count,
        "updated_at": feature.updated_at.isoformat() if feature.updated_at else None,
        "updated_by": feature.updated_by,
    }


@router.post("/tryon/test")
async def test_tryon_config(
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Test Gemini connectivity for tryon. Uses low-cost model list API, not image generation."""
    provider = _get_tryon_provider(db)
    feature = _get_tryon_feature(db)

    if not provider:
        raise HTTPException(404, "Gemini provider not found")
    if not feature:
        raise HTTPException(404, "Tryon feature not found")

    # Decrypt key
    api_key = ""
    try:
        api_key = decrypt_secret(provider.api_key_encrypted) if provider.api_key_encrypted else ""
    except Exception as exc:
        logger.warning("Decrypt failed for tryon test: %s", exc)

    if not api_key:
        error_msg = "API Key 未配置或解密失败"
        _save_tryon_test_result(db, provider, False, 0, 0, error_msg, admin.username)
        raise HTTPException(400, detail=error_msg)

    config = feature.config or {}
    flash_model = config.get("flash_model", "")
    pro_model = config.get("pro_model", "")

    # Test using Gemini models list API (low cost, no image generation)
    import time

    base_url = (provider.base_url or "https://generativelanguage.googleapis.com").rstrip("/")
    test_url = f"{base_url}/v1beta/models?key={api_key}"

    success = False
    latency_ms = 0.0
    status_code = 0
    error_message = ""
    model_check = {"flash_found": False, "pro_found": False}

    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=provider.timeout_seconds or 30) as client:
            resp = await client.get(test_url)
        latency_ms = round((time.time() - start) * 1000, 1)
        status_code = resp.status_code

        if resp.status_code == 200:
            success = True
            error_message = "连接成功"
            # Check if configured models exist in response
            try:
                body = resp.json()
                models = body.get("models", [])
                model_names = [m.get("name", "") for m in models]
                if flash_model:
                    model_check["flash_found"] = any(flash_model in name for name in model_names)
                if pro_model:
                    model_check["pro_found"] = any(pro_model in name for name in model_names)
            except Exception:
                pass  # Model check is best-effort
        else:
            error_message = sanitize_error_message(resp.text[:300])
    except Exception as exc:
        error_message = sanitize_error_message(str(exc))

    _save_tryon_test_result(db, provider, success, latency_ms, status_code, error_message, admin.username)

    return {
        "success": success,
        "latency_ms": latency_ms,
        "status_code": status_code,
        "message": error_message,
        "model_check": model_check,
    }


def _save_tryon_test_result(
    db: Session,
    provider: AIAPIProvider,
    success: bool,
    latency_ms: float,
    status_code: int,
    error_message: str,
    username: str,
):
    """Save tryon test log and update provider test status."""
    log = AIAPITestLog(
        provider_key="gemini",
        test_type="tryon_gemini_config",
        success=success,
        latency_ms=latency_ms,
        status_code=status_code,
        error_message_sanitized=error_message,
        created_by=username,
    )
    db.add(log)
    provider.last_test_status = "success" if success else "failed"
    provider.last_test_message = error_message
    provider.last_test_at = _now_beijing()
    db.commit()


# ---------------------------------------------------------------------------
# Public runtime (no auth, no secrets)
# ---------------------------------------------------------------------------

@router.get("/public-runtime")
def public_runtime(db: Session = Depends(get_db)):
    """Non-sensitive runtime config for main site. No auth required.

    Returns only: provider_key, display_name, category, is_default,
                  feature_key, enabled, default_provider, fallback_order, default_model.
    Does NOT return: base_url, api_key_masked, has_api_key, notes, cost_note, last_test_message.
    """
    providers = db.query(AIAPIProvider).filter_by(enabled=True).all()
    features = db.query(AIFeatureConfig).all()
    return {
        "providers": [
            {
                "provider_key": p.provider_key,
                "display_name": p.display_name,
                "category": p.category,
                "is_default": p.is_default,
            }
            for p in providers
        ],
        "features": [
            {
                "feature_key": f.feature_key,
                "enabled": f.enabled,
                "default_provider": f.default_provider,
                "fallback_order": f.fallback_order,
                "default_model": f.default_model,
            }
            for f in features
        ],
    }
