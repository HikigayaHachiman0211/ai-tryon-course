from __future__ import annotations

import copy
import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.auth import get_current_admin
from app.database import AIAPIProvider, AIFeatureConfig, AIAPITestLog, AdminUser, get_db
from app.deepseek_models import DEEPSEEK_TEXT_MODELS, normalize_deepseek_model
from app.mimo_models import MIMO_TEXT_MODELS, normalize_mimo_model
from app.opencode_go import (
    OPENCODE_GO_MODELS,
    OPENCODE_GO_USER_AGENT,
    call_opencode_go_async,
    detect_opencode_go_protocol,
    parse_opencode_go_models_response,
    resolve_opencode_go_models_url,
)
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
    if p.provider_key == "mimo":
        model = normalize_mimo_model(model)
    elif p.provider_key == "deepseek":
        model = normalize_deepseek_model(model)
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
    elif p.provider_key == "opencode_go":
        import time

        protocol = detect_opencode_go_protocol(model)
        try:
            start = time.time()
            resp = await call_opencode_go_async(
                api_key=api_key,
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                base_url=base_url,
                temperature=None,
                max_tokens=16,
                timeout=p.timeout_seconds or 30,
            )
            latency_ms = round((time.time() - start) * 1000, 1)
            status_code = resp.status_code
            if resp.status_code == 200:
                success = True
                error_message = f"OK ({protocol})"
            else:
                error_message = sanitize_error_message(resp.text[:300]) or f"HTTP {resp.status_code}"
        except Exception as exc:
            error_message = sanitize_error_message(str(exc))
    elif p.provider_key == "01router":
        from app.routers.video_config import test_config
        checked = await test_config(admin=admin, db=db)
        success = checked["success"]
        latency_ms = checked["latency_ms"]
        status_code = checked["status_code"]
        error_message = checked["message"]
    elif p.provider_key == "decart":
        from app.routers.realtime_tryon import test_config as test_realtime_config

        checked = await test_realtime_config(admin=admin, db=db)
        success = checked["success"]
        latency_ms = checked["latency_ms"]
        status_code = checked["status_code"]
        error_message = checked["message"]
    elif p.provider_key == "xmax":
        from app.routers.realtime_tryon import test_xmax_config

        checked = await test_xmax_config(admin=admin, db=db)
        success = checked["success"]
        latency_ms = checked["latency_ms"]
        status_code = checked["status_code"]
        error_message = checked["message"]
    elif p.provider_key == "reactor":
        from app.routers.realtime_tryon import test_reactor_config

        checked = await test_reactor_config(admin=admin, db=db)
        success = checked["success"]
        latency_ms = checked["latency_ms"]
        status_code = checked["status_code"]
        error_message = checked["message"]
    elif p.provider_key == "totokens":
        import time

        relay_url = _validate_totokens_base_url(base_url or "https://totokens.cc")
        root = relay_url[:-3] if relay_url.endswith("/v1") else relay_url
        try:
            start = time.time()
            async with httpx.AsyncClient(timeout=p.timeout_seconds or 30) as client:
                resp = await client.get(f"{root}/v1/models", headers={"Authorization": f"Bearer {api_key}"})
            latency_ms = round((time.time() - start) * 1000, 1)
            status_code = resp.status_code
            if resp.status_code == 200:
                success = True
                error_message = "连接成功"
            else:
                error_message = f"HTTP {resp.status_code}"
        except Exception as exc:
            error_message = sanitize_error_message(str(exc))
    elif p.category in ("asr", "tts", "voice_clone", "tryon"):
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
        if p.provider_key == "mimo":
            # MiMo V2.6 defaults to thinking, so a five-token ping may never finish.
            payload.pop("max_tokens")
            payload["max_completion_tokens"] = 64
            payload["thinking"] = {"type": "disabled"}
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


_BUILTIN_PROVIDER_MODELS: dict[str, tuple[str, ...]] = {
    "mimo": MIMO_TEXT_MODELS,
    "gemini": (
        "gemini-4-hydrogen",
        "gemini-4-argon",
        "gemini-4-carbon",
        "gemini-3.8-flash",
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite-preview",
        "gemini-3.1-flash-image-preview",
        "gemini-3-pro-image-preview",
        "gemini-2.5-flash",
    ),
    "totokens": (
        "gemini-3.1-flash-image",
        "gpt-image-2",
        "chatgpt-image-latest",
        "gpt-image-1.5",
        "gpt-image-1",
    ),
    "deepseek": DEEPSEEK_TEXT_MODELS,
    "opencode_go": OPENCODE_GO_MODELS,
}

_ENDPOINT_SUFFIXES: tuple[str, ...] = (
    "/v1beta/models",
    "/v1/images/generations",
    "/v1/images/edits",
    "/v1/chat/completions",
    "/v1/responses",
    "/v1/models",
    "/chat/completions",
    "/responses",
    "/models",
)


def _strip_endpoint_suffix(base_url: str, suffixes: tuple[str, ...]) -> str:
    cleaned = base_url.strip().rstrip("/")
    lower = cleaned.lower()
    for suffix in suffixes:
        if lower.endswith(suffix):
            return cleaned[: -len(suffix)].rstrip("/")
    return cleaned


def _build_sync_models_request(p: AIAPIProvider, api_key: str, base_url: str) -> tuple[list[str], dict[str, str]]:
    """Build candidate models URLs and auth headers for a provider's model-sync request."""
    headers: dict[str, str] = {
        "User-Agent": OPENCODE_GO_USER_AGENT,
        "Accept": "application/json",
    }
    if p.provider_key == "opencode_go":
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return [resolve_opencode_go_models_url(base_url)], headers

    if p.provider_key == "gemini":
        root = _strip_endpoint_suffix(base_url, ("/v1beta/models", "/v1beta", "/v1"))
        headers["x-goog-api-key"] = api_key
        return [f"{root}/v1beta/models"], headers

    if p.provider_key == "totokens":
        relay = _validate_totokens_base_url(base_url)
        root = _strip_endpoint_suffix(
            relay,
            ("/v1/images/generations", "/v1/images/edits", "/v1/models", "/v1"),
        )
        headers["Authorization"] = f"Bearer {api_key}"
        return [f"{root}/v1/models"], headers

    cleaned = _strip_endpoint_suffix(base_url, _ENDPOINT_SUFFIXES)
    header_name = (p.auth_header_name or "api-key").strip()
    if p.auth_type == "api_key_header" and header_name.lower() != "authorization":
        headers[header_name] = api_key
    else:
        headers["Authorization"] = f"Bearer {api_key}"

    if cleaned.lower().endswith("/v1"):
        urls = [f"{cleaned}/models"]
    else:
        urls = [f"{cleaned}/v1/models", f"{cleaned}/models"]
    return list(dict.fromkeys(urls)), headers


def _extract_remote_model_ids(provider_key: str, body: Any) -> list[str]:
    """Parse model IDs from OpenAI, Gemini, OpenCode Go, or relay /models payloads."""
    if provider_key == "opencode_go":
        return parse_opencode_go_models_response(body)
    if provider_key == "gemini":
        items = body.get("models") if isinstance(body, dict) else []
        out = [
            str(m.get("name") or "").replace("models/", "").strip()
            for m in (items or [])
            if isinstance(m, dict) and m.get("name")
        ]
        return list(dict.fromkeys(m for m in out if m))

    raw_items: Any = []
    if isinstance(body, list):
        raw_items = body
    elif isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, dict) and isinstance(data.get("models"), list):
            raw_items = data["models"]
        elif isinstance(data, list):
            raw_items = data
        elif isinstance(body.get("models"), list):
            raw_items = body["models"]

    discovered: list[str] = []
    for item in raw_items or []:
        if isinstance(item, str) and item.strip():
            discovered.append(item.strip())
        elif isinstance(item, dict):
            model_id = str(item.get("id") or item.get("name") or "").strip()
            if model_id:
                discovered.append(model_id)
    return list(dict.fromkeys(discovered))


@router.post("/providers/{provider_id}/sync-models")
async def sync_provider_models(
    provider_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Fetch live available model IDs or backfill built-in catalog when key is unset."""
    p = db.get(AIAPIProvider, provider_id)
    if not p:
        raise HTTPException(404, "Provider not found")

    api_key = ""
    if p.api_key_encrypted:
        try:
            api_key = decrypt_secret(p.api_key_encrypted)
        except Exception as exc:
            raise HTTPException(400, detail=f"API Key 解密失败: {sanitize_error_message(str(exc))}")

    if not api_key and p.provider_key != "opencode_go":
        builtin = _BUILTIN_PROVIDER_MODELS.get(p.provider_key)
        if not builtin:
            raise HTTPException(400, detail="请先配置 API Key 后再从远端同步模型")
        existing = [str(m).strip() for m in (p.model_options or []) if str(m).strip()]
        p.model_options = list(dict.fromkeys([*builtin, *existing]))
        p.updated_at = _now_beijing()
        p.updated_by = admin.username
        db.commit()
        db.refresh(p)
        return {
            "provider_key": p.provider_key,
            "synced_count": len(builtin),
            "model_options": p.model_options or [],
            "source": "builtin",
        }

    base_url = (p.base_url or "").rstrip("/")
    if not base_url:
        raise HTTPException(400, detail="Base URL not configured")

    parsed = urlsplit(base_url)
    if parsed.scheme.lower() not in ("https", "http"):
        raise HTTPException(400, detail="Invalid Base URL scheme")

    urls, headers = _build_sync_models_request(p, api_key, base_url)
    body: Any = None
    last_error = ""
    try:
        async with httpx.AsyncClient(timeout=p.timeout_seconds or 30, follow_redirects=True) as client:
            for idx, url in enumerate(urls):
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    try:
                        body = resp.json()
                    except ValueError as exc:
                        raise HTTPException(
                            400,
                            detail=f"拉取模型列表失败: 远端响应不是有效的 JSON ({sanitize_error_message(str(exc))})",
                        )
                    last_error = ""
                    break
                last_error = f"HTTP {resp.status_code} {sanitize_error_message(resp.text[:200])}".strip()
                # Only try secondary candidate path on 404; fail fast on auth/rate errors.
                if resp.status_code != 404 or idx == len(urls) - 1:
                    raise HTTPException(400, detail=f"拉取模型列表失败: {last_error}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, detail=f"拉取模型列表失败: {sanitize_error_message(str(exc))}")

    discovered = _extract_remote_model_ids(p.provider_key, body)
    if not discovered:
        raise HTTPException(400, detail="远端未返回任何可用模型")

    merged = list(dict.fromkeys([*discovered, *(p.model_options or [])]))
    p.model_options = merged
    p.updated_at = _now_beijing()
    p.updated_by = admin.username
    db.commit()
    db.refresh(p)
    return {
        "provider_key": p.provider_key,
        "synced_count": len(discovered),
        "model_options": p.model_options or [],
        "source": "remote",
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

_TOTOKENS_PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_VALID_TOTOKENS_SCOPES: tuple[str, ...] = ("gemini", "gpt_1k", "gpt_2k4k", "gpt_all", "custom")
_BUILTIN_TOTOKENS_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "id": "totokens_gemini",
        "scope": "gemini",
        "label": "ToTokens Gemini 生图",
        "builtin": True,
        "enabled": True,
        "default_model": "gemini-3.1-flash-image",
        "models": ["gemini-3.1-flash-image", "gemini-3-pro-image-preview"],
        "timeout_seconds": 120,
    },
    {
        "id": "totokens_gpt_1k",
        "scope": "gpt_1k",
        "label": "ToTokens GPT Image 1K",
        "builtin": True,
        "enabled": True,
        "default_model": "gpt-image-2",
        "models": ["gpt-image-2", "chatgpt-image-latest", "gpt-image-1.5", "gpt-image-1"],
        "timeout_seconds": 120,
    },
    {
        "id": "totokens_gpt_2k4k",
        "scope": "gpt_2k4k",
        "label": "ToTokens GPT Image 2K/4K",
        "builtin": True,
        "enabled": True,
        "default_model": "gpt-image-2",
        "models": ["gpt-image-2"],
        "timeout_seconds": 120,
    },
)
_BUILTIN_TOTOKENS_BY_ID: dict[str, dict[str, Any]] = {
    item["id"]: item for item in _BUILTIN_TOTOKENS_PROFILES
}


class TotokensAPIProfileUpdate(BaseModel):
    id: str
    scope: Literal["gemini", "gpt_1k", "gpt_2k4k", "gpt_all", "custom"] | None = None
    label: str | None = None
    enabled: bool | None = None
    base_url: str | None = None
    api_key: str | None = None  # None/empty/whitespace = preserve existing key
    clear_api_key: bool = False
    default_model: str | None = None
    models: list[str] | None = None
    timeout_seconds: int | None = None
    delete: bool = False


class TryonConfigUpdateRequest(BaseModel):
    enabled: bool | None = None
    provider_key: str | None = None
    base_url: str | None = None
    api_key: str | None = None  # None/empty/whitespace = don't update
    clear_api_key: bool = False
    flash_model: str | None = None
    pro_model: str | None = None
    timeout_seconds: int | None = None
    retry_count: int | None = None
    totokens_apis: list[TotokensAPIProfileUpdate] | None = None


_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


def _validate_tryon_model_id(value: str, label: str) -> str:
    model = value.strip()
    if not model:
        raise HTTPException(400, detail=f"{label}模型 ID 不能为空")
    if not _MODEL_ID_RE.fullmatch(model):
        raise HTTPException(400, detail=f"{label}模型 ID 格式无效")
    return model


def _validate_totokens_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    try:
        parsed = urlsplit(base_url)
        valid = (parsed.scheme == "https" and parsed.hostname and not parsed.username and
                 not parsed.password and not parsed.query and not parsed.fragment)
        _ = parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(400, detail="中转站地址必须是有效的 HTTPS 地址")
    return base_url


def _get_tryon_provider(db: Session, provider_key: str = "gemini") -> AIAPIProvider | None:
    if provider_key not in {"gemini", "totokens"}:
        raise HTTPException(400, "不支持的试衣服务提供商")
    return db.query(AIAPIProvider).filter_by(provider_key=provider_key).first()


def _get_tryon_feature(db: Session) -> AIFeatureConfig | None:
    return db.query(AIFeatureConfig).filter_by(feature_key="tryon").first()


def _clean_model_list(models: list[str] | None, fallback: list[str] | None = None) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    source = models if models is not None else (fallback or [])
    for item in source:
        text = str(item or "").strip()
        if not text:
            continue
        validated = _validate_tryon_model_id(text, "")
        if validated not in seen:
            seen.add(validated)
            cleaned.append(validated)
    return cleaned


def _merge_totokens_profiles_raw(
    config: dict[str, Any],
    *,
    relay_base_url: str = "https://totokens.cc",
    relay_timeout: int = 120,
) -> list[dict[str, Any]]:
    raw_saved = config.get("totokens_apis") if isinstance(config.get("totokens_apis"), list) else []
    saved_by_id: dict[str, dict[str, Any]] = {}
    custom_saved: list[dict[str, Any]] = []
    for item in raw_saved:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or "").strip()
        if not pid:
            continue
        if pid in _BUILTIN_TOTOKENS_BY_ID:
            saved_by_id[pid] = item
        else:
            custom_saved.append(item)

    def _build_entry(base_tpl: dict[str, Any], saved: dict[str, Any]) -> dict[str, Any]:
        pid = str(saved.get("id") or base_tpl.get("id") or "").strip()
        scope = str(saved.get("scope") or base_tpl.get("scope") or "custom").strip().lower()
        if scope not in _VALID_TOTOKENS_SCOPES:
            scope = "custom"
        raw_models = saved.get("models") if isinstance(saved.get("models"), list) else list(base_tpl.get("models") or [])
        models = list(dict.fromkeys([str(m or "").strip() for m in raw_models if str(m or "").strip()]))
        default_model = str(saved.get("default_model") or base_tpl.get("default_model") or (models[0] if models else "")).strip()
        if default_model and default_model not in models:
            models = [default_model, *models]
        return {
            "id": pid,
            "scope": scope,
            "label": str(saved.get("label") or base_tpl.get("label") or pid).strip(),
            "builtin": bool(pid in _BUILTIN_TOTOKENS_BY_ID),
            "enabled": bool(saved["enabled"]) if "enabled" in saved else bool(base_tpl.get("enabled", True)),
            "base_url": str(saved.get("base_url") or relay_base_url or "https://totokens.cc").strip() or "https://totokens.cc",
            "api_key_encrypted": saved.get("api_key_encrypted"),
            "default_model": default_model,
            "models": models,
            "timeout_seconds": int(saved.get("timeout_seconds") or base_tpl.get("timeout_seconds") or relay_timeout or 120),
            "last_test_status": saved.get("last_test_status"),
            "last_test_message": saved.get("last_test_message"),
            "last_test_at": saved.get("last_test_at"),
        }

    merged = [_build_entry(tpl, saved_by_id.get(tpl["id"], {})) for tpl in _BUILTIN_TOTOKENS_PROFILES]
    for extra in custom_saved:
        merged.append(_build_entry({"builtin": False, "enabled": True, "models": []}, extra))
    return merged


def _serialize_totokens_profiles(
    config: dict[str, Any],
    *,
    relay_base_url: str = "https://totokens.cc",
    relay_timeout: int = 120,
) -> list[dict[str, Any]]:
    """Serialize ToTokens API profiles for admin responses without keys or masks."""
    out: list[dict[str, Any]] = []
    for item in _merge_totokens_profiles_raw(config, relay_base_url=relay_base_url, relay_timeout=relay_timeout):
        enc = item.get("api_key_encrypted")
        has_key = bool(enc)
        key_status = "ok"
        if has_key:
            try:
                decrypt_secret(enc)
            except Exception:
                key_status = "decrypt_failed"
        out.append({
            "id": item["id"],
            "scope": item["scope"],
            "label": item["label"],
            "builtin": item["builtin"],
            "enabled": item["enabled"],
            "base_url": item["base_url"],
            "has_api_key": has_key,
            "key_status": key_status,
            "default_model": item["default_model"],
            "models": list(item["models"]),
            "timeout_seconds": item["timeout_seconds"],
            "last_test_status": item.get("last_test_status"),
            "last_test_message": item.get("last_test_message"),
            "last_test_at": item.get("last_test_at"),
        })
    return out


def _totokens_companion_summary(db: Session, config: dict[str, Any]) -> dict[str, Any]:
    relay = db.query(AIAPIProvider).filter_by(provider_key="totokens").first()
    relay_base_url = (relay.base_url or "https://totokens.cc") if relay else "https://totokens.cc"
    relay_timeout = (relay.timeout_seconds or 120) if relay else 120
    relay_has_legacy_key = False
    if relay and relay.api_key_encrypted:
        try:
            decrypt_secret(relay.api_key_encrypted)
            relay_has_legacy_key = True
        except Exception:
            relay_has_legacy_key = False

    profiles = _serialize_totokens_profiles(config, relay_base_url=relay_base_url, relay_timeout=relay_timeout)
    configured_profiles = [
        p for p in profiles if p["enabled"] and p["has_api_key"] and p["key_status"] == "ok"
    ]
    configured_scopes = list(dict.fromkeys([p["scope"] for p in configured_profiles]))

    return {
        "totokens_enabled": bool(relay and relay.enabled),
        "totokens_has_api_key": bool(relay_has_legacy_key or configured_profiles),
        "totokens_base_url": relay_base_url,
        "totokens_chatgpt_model": str(config.get("totokens_chatgpt_model") or config.get("totokens_pro_model") or "gpt-image-2").strip(),
        "totokens_configured_count": len(configured_profiles),
        "totokens_configured_scopes": configured_scopes,
        "totokens_apis": profiles,
    }


def _build_tryon_response_payload(
    db: Session,
    feature: AIFeatureConfig,
    provider: AIAPIProvider,
    selected: str,
) -> dict[str, Any]:
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
        "provider_key": selected,
        "active_provider_key": feature.default_provider or "gemini",
        "base_url": provider.base_url or "",
        "provider_enabled": provider.enabled,
        "has_api_key": has_key,
        "key_status": key_status,
        "flash_model": config.get("totokens_flash_model", "gemini-3.1-flash-image") if selected == "totokens" else config.get("flash_model", ""),
        "pro_model": config.get("totokens_pro_model", "gpt-image-2") if selected == "totokens" else config.get("pro_model", ""),
        "timeout_seconds": provider.timeout_seconds,
        "retry_count": provider.retry_count,
        "updated_at": feature.updated_at.isoformat() if feature.updated_at else None,
        "updated_by": feature.updated_by,
        "last_test_status": provider.last_test_status,
        "last_test_message": provider.last_test_message,
        "last_test_at": provider.last_test_at.isoformat() if provider.last_test_at else None,
        **_totokens_companion_summary(db, config),
    }


@router.get("/tryon")
def get_tryon_config(provider_key: str | None = None, admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Get tryon-specific configuration. No key or mask is returned."""
    feature = _get_tryon_feature(db)
    if not feature:
        raise HTTPException(404, "Tryon feature not found")
    selected = provider_key or feature.default_provider or "gemini"
    provider = _get_tryon_provider(db, selected)
    if not provider:
        raise HTTPException(404, "Tryon provider not found")
    return _build_tryon_response_payload(db, feature, provider, selected)


@router.put("/tryon")
def update_tryon_config(
    body: TryonConfigUpdateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Update tryon configuration. Provider and Feature updated in one transaction."""
    feature = _get_tryon_feature(db)
    if not feature:
        raise HTTPException(404, "Tryon feature not found")
    previous_provider = feature.default_provider or "gemini"
    selected = body.provider_key or feature.default_provider or "gemini"
    provider = _get_tryon_provider(db, selected)
    if not provider:
        raise HTTPException(404, "Tryon provider not found")

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

    if selected == "totokens" and body.base_url is not None:
        provider.base_url = _validate_totokens_base_url(body.base_url)

    # Update feature config cleanly using deep copy so SQLAlchemy tracks nested JSON changes
    if body.enabled is not None:
        feature.enabled = body.enabled
    config = copy.deepcopy(dict(feature.config or {}))

    if body.flash_model is not None:
        config["totokens_flash_model" if selected == "totokens" else "flash_model"] = _validate_tryon_model_id(body.flash_model, "Flash ")
    if body.pro_model is not None:
        validated_pro = _validate_tryon_model_id(body.pro_model, "Pro ")
        config["totokens_pro_model" if selected == "totokens" else "pro_model"] = validated_pro
        if selected == "totokens":
            config["totokens_chatgpt_model"] = validated_pro

    if body.totokens_apis is not None:
        relay_provider = provider if selected == "totokens" else db.query(AIAPIProvider).filter_by(provider_key="totokens").first()
        relay_base = (relay_provider.base_url or "https://totokens.cc") if relay_provider else "https://totokens.cc"
        relay_timeout = (relay_provider.timeout_seconds or 120) if relay_provider else 120
        existing_profiles = _merge_totokens_profiles_raw(config, relay_base_url=relay_base, relay_timeout=relay_timeout)
        profiles_by_id: dict[str, dict[str, Any]] = {p["id"]: p for p in existing_profiles}
        custom_order = [p["id"] for p in existing_profiles if not p["builtin"]]

        for patch in body.totokens_apis:
            pid = (patch.id or "").strip()
            if not _TOTOKENS_PROFILE_ID_RE.fullmatch(pid):
                raise HTTPException(400, detail=f"无效的 ToTokens API 配置 ID：{pid}")
            is_builtin = pid in _BUILTIN_TOTOKENS_BY_ID
            if patch.delete:
                if is_builtin:
                    raise HTTPException(400, detail="默认 ToTokens 分组配置不可删除")
                profiles_by_id.pop(pid, None)
                if pid in custom_order:
                    custom_order.remove(pid)
                continue

            cur = copy.deepcopy(profiles_by_id.get(pid) or {
                "id": pid,
                "scope": patch.scope or "custom",
                "label": (patch.label or pid).strip(),
                "builtin": is_builtin,
                "enabled": True,
                "base_url": relay_base,
                "api_key_encrypted": None,
                "default_model": "",
                "models": [],
                "timeout_seconds": relay_timeout,
                "last_test_status": None,
                "last_test_message": None,
                "last_test_at": None,
            })
            if not is_builtin and patch.scope is not None:
                cur["scope"] = patch.scope
            if patch.label is not None:
                cleaned_label = patch.label.strip()
                if not cleaned_label:
                    raise HTTPException(400, detail="ToTokens API 名称不能为空")
                cur["label"] = cleaned_label[:80]
            if patch.enabled is not None:
                cur["enabled"] = bool(patch.enabled)
            if patch.base_url is not None and patch.base_url.strip():
                cur["base_url"] = _validate_totokens_base_url(patch.base_url)
            if patch.timeout_seconds is not None:
                if not 10 <= patch.timeout_seconds <= 300:
                    raise HTTPException(400, detail="ToTokens API 超时秒数必须在 10 到 300 之间")
                cur["timeout_seconds"] = patch.timeout_seconds
            if patch.models is not None:
                cur["models"] = _clean_model_list(patch.models)
            if patch.default_model is not None and patch.default_model.strip():
                validated_default = _validate_tryon_model_id(patch.default_model, f"{cur['label']} ")
                cur["default_model"] = validated_default
                if validated_default not in cur["models"]:
                    cur["models"] = [validated_default, *cur["models"]]
            elif cur["default_model"] and cur["models"] and cur["default_model"] not in cur["models"]:
                cur["default_model"] = cur["models"][0]
            elif not cur["default_model"] and cur["models"]:
                cur["default_model"] = cur["models"][0]

            if patch.clear_api_key:
                cur["api_key_encrypted"] = None
            elif patch.api_key and patch.api_key.strip():
                try:
                    cur["api_key_encrypted"] = encrypt_secret(patch.api_key.strip())
                except RuntimeError as exc:
                    raise HTTPException(400, detail=f"无法加密 ToTokens API Key: {exc}")

            profiles_by_id[pid] = cur
            if not is_builtin and pid not in custom_order:
                custom_order.append(pid)

        ordered_ids = [tpl["id"] for tpl in _BUILTIN_TOTOKENS_PROFILES if tpl["id"] in profiles_by_id] + [
            cid for cid in custom_order if cid in profiles_by_id
        ]
        config["totokens_apis"] = [profiles_by_id[item_id] for item_id in ordered_ids]

    if selected != previous_provider:
        if previous_provider == "gemini":
            config["_gemini_default_model"] = feature.default_model
            config["_gemini_fallback_order"] = feature.fallback_order
        feature.default_provider = selected
        if selected == "totokens":
            feature.default_model = config.get("totokens_flash_model") or "gemini-3.1-flash-image"
            feature.fallback_order = ["totokens"]
        else:
            feature.default_model = config.get("_gemini_default_model") or config.get("flash_model")
            feature.fallback_order = config.get("_gemini_fallback_order") or ["gemini"]
    if body.flash_model is not None:
        feature.default_model = config["totokens_flash_model" if selected == "totokens" else "flash_model"]
    if selected == "totokens":
        feature.fallback_order = ["totokens"]
    feature.config = config
    flag_modified(feature, "config")

    now = _now_beijing()
    provider.updated_at = now
    provider.updated_by = admin.username
    feature.updated_at = now
    feature.updated_by = admin.username

    # Validate: if enabled, must have at least one valid decryptable key
    if feature.enabled:
        if not provider.enabled:
            db.rollback()
            raise HTTPException(
                400,
                detail="试衣 Provider 当前已停用，请先在 Provider 管理中启用",
            )
        has_legacy = bool(provider.api_key_encrypted)
        if has_legacy:
            try:
                decrypt_secret(provider.api_key_encrypted)
            except Exception:
                db.rollback()
                raise HTTPException(400, detail="API Key 无法解密，请重新保存 Key 后再启用")

        has_valid_profile_key = False
        if selected == "totokens":
            for item in config.get("totokens_apis") or []:
                if not isinstance(item, dict) or not item.get("enabled"):
                    continue
                enc = item.get("api_key_encrypted")
                if enc:
                    try:
                        decrypt_secret(enc)
                        has_valid_profile_key = True
                    except Exception:
                        db.rollback()
                        raise HTTPException(400, detail="ToTokens API Key 无法解密，请重新保存 Key 后再启用")
        if not (has_legacy or has_valid_profile_key):
            db.rollback()
            raise HTTPException(400, detail="启用试衣功能时必须配置 API Key")

    db.commit()
    db.refresh(provider)
    db.refresh(feature)
    return _build_tryon_response_payload(db, feature, provider, selected)


async def _probe_totokens_connection(
    *,
    base_url: str,
    api_key: str,
    timeout_seconds: int,
    expected_models: list[str],
) -> tuple[bool, float, int, str, list[str]]:
    validated = _validate_totokens_base_url(base_url or "https://totokens.cc")
    root = validated[:-3] if validated.endswith("/v1") else validated
    test_url = f"{root}/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    success = False
    latency_ms = 0.0
    status_code = 0
    error_message = ""
    matched_models: list[str] = []

    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=max(10, min(int(timeout_seconds or 30), 300))) as client:
            resp = await client.get(test_url, headers=headers)
        latency_ms = round((time.time() - start) * 1000, 1)
        status_code = resp.status_code
        if resp.status_code == 200:
            success = True
            error_message = "连接成功"
            try:
                body = resp.json()
                model_names = [m.get("id", "") for m in (body.get("data") or []) if isinstance(m, dict)]
                for expected in expected_models:
                    if expected and any(expected in name for name in model_names):
                        matched_models.append(expected)
            except Exception:
                pass
        else:
            error_message = f"HTTP {resp.status_code}"
    except Exception as exc:
        error_message = sanitize_error_message(str(exc))

    return success, latency_ms, status_code, error_message, matched_models


@router.post("/tryon/test")
async def test_tryon_config(
    provider_key: str | None = None,
    profile_id: str | None = None,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Check provider or specific ToTokens API key without generating an image."""
    feature = _get_tryon_feature(db)
    if not feature:
        raise HTTPException(404, "Tryon feature not found")
    selected = profile_id and "totokens" or provider_key or feature.default_provider or "gemini"
    provider = _get_tryon_provider(db, selected)
    if not provider:
        raise HTTPException(404, "Tryon provider not found")

    config = copy.deepcopy(dict(feature.config or {}))

    # Per-profile test when profile_id is requested
    if profile_id:
        profiles = _merge_totokens_profiles_raw(
            config,
            relay_base_url=provider.base_url or "https://totokens.cc",
            relay_timeout=provider.timeout_seconds or 120,
        )
        target = next((p for p in profiles if p["id"] == profile_id.strip()), None)
        if not target:
            raise HTTPException(404, detail="指定的 ToTokens API 配置不存在")
        api_key = ""
        try:
            api_key = decrypt_secret(target["api_key_encrypted"]) if target.get("api_key_encrypted") else ""
        except Exception as exc:
            logger.warning("Decrypt failed for ToTokens profile %s: %s", profile_id, exc)
        if not api_key:
            now_iso = _now_beijing().isoformat()
            target["last_test_status"] = "failed"
            target["last_test_message"] = "API Key 未配置或解密失败"
            target["last_test_at"] = now_iso
            config["totokens_apis"] = profiles
            feature.config = config
            flag_modified(feature, "config")
            db.add(AIAPITestLog(
                provider_key=f"totokens:{target['id']}",
                test_type="tryon_config",
                success=False,
                latency_ms=0,
                status_code=0,
                error_message_sanitized="API Key 未配置或解密失败",
                created_by=admin.username,
            ))
            db.commit()
            raise HTTPException(400, detail="API Key 未配置或解密失败")

        expected_models = [target.get("default_model", ""), *(target.get("models") or [])]
        success, latency_ms, status_code, error_message, matched_models = await _probe_totokens_connection(
            base_url=target.get("base_url") or provider.base_url or "https://totokens.cc",
            api_key=api_key,
            timeout_seconds=target.get("timeout_seconds") or provider.timeout_seconds or 30,
            expected_models=expected_models,
        )
        target["last_test_status"] = "success" if success else "failed"
        target["last_test_message"] = error_message
        target["last_test_at"] = _now_beijing().isoformat()
        config["totokens_apis"] = profiles
        feature.config = config
        flag_modified(feature, "config")
        db.add(AIAPITestLog(
            provider_key=f"totokens:{target['id']}",
            test_type="tryon_config",
            success=success,
            latency_ms=latency_ms,
            status_code=status_code,
            error_message_sanitized=error_message,
            created_by=admin.username,
        ))
        db.commit()
        return {
            "success": success,
            "latency_ms": latency_ms,
            "status_code": status_code,
            "message": error_message,
            "profile_id": target["id"],
            "model_check": {
                "flash_found": bool(matched_models) and target["scope"] == "gemini",
                "pro_found": bool(matched_models) and target["scope"] != "gemini",
            },
            "models_matched": matched_models,
        }

    # Decrypt legacy/provider-level key (or test configured multi-API profiles if legacy key absent on ToTokens)
    api_key = ""
    try:
        api_key = decrypt_secret(provider.api_key_encrypted) if provider.api_key_encrypted else ""
    except Exception as exc:
        logger.warning("Decrypt failed for tryon test: %s", exc)

    if not api_key and selected == "totokens":
        profiles = _merge_totokens_profiles_raw(
            config,
            relay_base_url=provider.base_url or "https://totokens.cc",
            relay_timeout=provider.timeout_seconds or 120,
        )
        configured_entries: list[tuple[dict[str, Any], str]] = []
        for entry in profiles:
            if entry.get("enabled") and entry.get("api_key_encrypted"):
                try:
                    plain = decrypt_secret(entry["api_key_encrypted"])
                    if plain:
                        configured_entries.append((entry, plain))
                except Exception:
                    pass
        if configured_entries:
            results: list[dict[str, Any]] = []
            all_ok = True
            total_latency = 0.0
            last_code = 200
            flash_found = False
            pro_found = False
            for entry, entry_key in configured_entries:
                ok, lat, sc, msg, matched = await _probe_totokens_connection(
                    base_url=entry.get("base_url") or provider.base_url or "https://totokens.cc",
                    api_key=entry_key,
                    timeout_seconds=entry.get("timeout_seconds") or provider.timeout_seconds or 30,
                    expected_models=[entry.get("default_model", ""), *(entry.get("models") or [])],
                )
                entry["last_test_status"] = "success" if ok else "failed"
                entry["last_test_message"] = msg
                entry["last_test_at"] = _now_beijing().isoformat()
                all_ok = all_ok and ok
                total_latency = max(total_latency, lat)
                last_code = sc
                if entry["scope"] == "gemini" and matched:
                    flash_found = True
                if entry["scope"] != "gemini" and matched:
                    pro_found = True
                results.append({"profile_id": entry["id"], "label": entry["label"], "success": ok, "status_code": sc, "latency_ms": lat, "message": msg})
            config["totokens_apis"] = profiles
            feature.config = config
            flag_modified(feature, "config")
            summary_msg = "连接成功" if all_ok else "; ".join(f"{r['label']}: {r['message']}" for r in results if not r["success"])
            _save_tryon_test_result(db, provider, all_ok, total_latency, last_code, summary_msg, admin.username)
            return {
                "success": all_ok,
                "latency_ms": total_latency,
                "status_code": last_code,
                "message": summary_msg,
                "model_check": {"flash_found": flash_found, "pro_found": pro_found},
                "profile_results": results,
            }

    if not api_key:
        error_msg = "API Key 未配置或解密失败"
        _save_tryon_test_result(db, provider, False, 0, 0, error_msg, admin.username)
        raise HTTPException(400, detail=error_msg)

    flash_model = config.get("totokens_flash_model", "gemini-3.1-flash-image") if selected == "totokens" else config.get("flash_model", "")
    pro_model = config.get("totokens_pro_model", "gpt-image-2") if selected == "totokens" else config.get("pro_model", "")

    base_url = (provider.base_url or ("https://totokens.cc" if selected == "totokens" else "https://generativelanguage.googleapis.com")).rstrip("/")
    if selected == "totokens":
        base_url = _validate_totokens_base_url(base_url)
        root = base_url[:-3] if base_url.endswith("/v1") else base_url
        test_url = f"{root}/v1/models"
        headers = {"Authorization": f"Bearer {api_key}"}
    else:
        test_url = f"{base_url}/v1beta/models"
        headers = {"x-goog-api-key": api_key}

    success = False
    latency_ms = 0.0
    status_code = 0
    error_message = ""
    model_check = {"flash_found": False, "pro_found": False}

    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=provider.timeout_seconds or 30) as client:
            resp = await client.get(test_url, headers=headers)
        latency_ms = round((time.time() - start) * 1000, 1)
        status_code = resp.status_code

        if resp.status_code == 200:
            success = True
            error_message = "连接成功"
            try:
                body = resp.json()
                models = body.get("data", []) if selected == "totokens" else body.get("models", [])
                model_names = [m.get("id", "") if selected == "totokens" else m.get("name", "") for m in models]
                if flash_model:
                    model_check["flash_found"] = any(flash_model in name for name in model_names)
                if pro_model:
                    model_check["pro_found"] = any(pro_model in name for name in model_names)
            except Exception:
                pass  # Model check is best-effort
        else:
            error_message = f"HTTP {resp.status_code}" if selected == "totokens" else sanitize_error_message(resp.text[:300])
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
        provider_key=provider.provider_key,
        test_type="tryon_config",
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
