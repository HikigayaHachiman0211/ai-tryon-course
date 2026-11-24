from __future__ import annotations

import difflib
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.auth import get_current_admin
from app.config import get_settings
from app.database import PromptConfig, PromptVersion, AdminUser, get_db
from app.deepseek_models import DEEPSEEK_TEXT_MODELS, normalize_deepseek_model
from app.mimo_models import normalize_mimo_model
from app.opencode_go import (
    DEFAULT_OPENCODE_GO_BASE_URL,
    OPENCODE_GO_MODELS,
    call_opencode_go_async,
    extract_opencode_go_text,
    detect_opencode_go_protocol,
)
from app.routers import to_beijing_str
from app.i18n.locale import request_locale
from app.i18n.messages import error_message


def _sanitize_error(text: str) -> str:
    """Strip API keys, tokens, base64 from error messages before returning to frontend."""
    text = re.sub(r"Authorization\s*[:=]\s*Bearer\s+\S+", "Authorization: Bearer [REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"api[_-]?key\s*[:=]\s*\S+", "api-key=[REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"\?key=\S+", "?key=[REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"Bearer\s+\S+", "Bearer [REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"data:[a-z]+/[a-z]+;base64,[A-Za-z0-9+/=]{40,}", "data:[REDACTED]", text, flags=re.IGNORECASE)
    if len(text) > 500:
        text = text[:500] + "..."
    return text

router = APIRouter(prefix="/api/admin/prompts", tags=["prompts"])


class PromptUpdateRequest(BaseModel):
    content: str | None = None
    variables: list[str] | None = None
    model_name: str | None = None
    temperature: float | None = None
    is_active: bool | None = None
    display_name: str | None = None
    description: str | None = None
    category: str | None = None
    prompt_type: str | None = None


class PromptTestRequest(BaseModel):
    test_params: dict = {}


class PromptPreviewRequest(BaseModel):
    content: str = ""
    variables: dict = {}


@router.get("")
def list_prompts(
    request: Request,
    category: str | None = None,
    prompt_type: str | None = None,
    is_active: bool | None = None,
    keyword: str | None = None,
    locale: str | None = Query(default=None),
    admin=Depends(get_current_admin),
    db=Depends(get_db),
):
    query = db.query(PromptConfig)
    if category:
        query = query.filter(PromptConfig.category == category)
    if prompt_type:
        query = query.filter(PromptConfig.prompt_type == prompt_type)
    if is_active is not None:
        query = query.filter(PromptConfig.is_active == is_active)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            (PromptConfig.name.ilike(like))
            | (PromptConfig.display_name.ilike(like))
            | (PromptConfig.description.ilike(like))
        )
    requested_locale = request_locale(request, explicit=locale)
    prompts = query.order_by(PromptConfig.id).all()
    # Keep one row per stable prompt name. Prefer the requested locale and
    # fall back to the Chinese compatibility row only when a translation row
    # is unavailable.
    selected: dict[str, PromptConfig] = {}
    for prompt in prompts:
        if prompt.name not in selected or (
            prompt.locale == requested_locale
            and selected[prompt.name].locale != requested_locale
        ):
            selected[prompt.name] = prompt
    return [_serialize(p, requested_locale=requested_locale) for p in selected.values()]


@router.get("/{prompt_id}")
def get_prompt(prompt_id: int, request: Request, admin=Depends(get_current_admin), db=Depends(get_db)):
    p = db.get(PromptConfig, prompt_id)
    if not p:
        raise HTTPException(404, {"code": "PROMPT_NOT_FOUND"})
    return _serialize(p, requested_locale=request_locale(request))


@router.put("/{prompt_id}")
def update_prompt(
    prompt_id: int,
    body: PromptUpdateRequest,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db=Depends(get_db),
):
    p = db.get(PromptConfig, prompt_id)
    if not p:
        raise HTTPException(404, {"code": "PROMPT_NOT_FOUND"})

    # Save current version to history before updating
    if body.content is not None and body.content != p.content:
        version_record = PromptVersion(
            prompt_config_id=p.id,
            version=p.version,
            content=p.content,
            variables=p.variables,
            model_name=p.model_name,
            temperature=p.temperature,
            updated_at=p.updated_at,
            updated_by=p.updated_by,
        )
        db.add(version_record)
        p.version += 1

    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(p, k, v)
    p.updated_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    p.updated_by = admin.username
    db.commit()
    db.refresh(p)
    return _serialize(p, requested_locale=request_locale(request))


@router.post("/{prompt_id}/test")
async def test_prompt(
    prompt_id: int,
    body: PromptTestRequest,
    request: Request,
    admin=Depends(get_current_admin),
    db=Depends(get_db),
):
    """Test a prompt by calling the configured LLM provider.

    Uses the prompt's model_name to determine which provider to call.
    All errors are sanitized before returning to the frontend.
    """
    p = db.get(PromptConfig, prompt_id)
    if not p:
        raise HTTPException(404, {"code": "PROMPT_NOT_FOUND"})
    locale = request_locale(request)

    # Substitute variables
    content = p.content
    for key, value in body.test_params.items():
        content = content.replace(f"{{{key}}}", str(value))

    # Determine provider from model_name (supports optional "opencode_go:<model>" prefix)
    raw_model = (p.model_name or "").strip()
    lower_model = raw_model.lower()
    explicit_opencode = False
    if lower_model.startswith(("opencode_go:", "opencode-go:")):
        raw_model = raw_model.split(":", 1)[1].strip()
        lower_model = raw_model.lower()
        explicit_opencode = True

    if explicit_opencode:
        provider_key = "opencode_go"
    elif lower_model.startswith("mimo"):
        provider_key = "mimo"
    elif lower_model in DEEPSEEK_TEXT_MODELS or lower_model in ("deepseek-chat", "deepseek-reasoner", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp"):
        provider_key = "deepseek"
    elif lower_model in OPENCODE_GO_MODELS and not lower_model.startswith("gemini-"):
        provider_key = "opencode_go"
    elif lower_model.startswith("deepseek"):
        provider_key = "deepseek"
    else:
        provider_key = "gemini"

    def _load_provider_cfg(pk: str):
        from app.database import AIAPIProvider
        row = db.query(AIAPIProvider).filter_by(provider_key=pk, enabled=True).first()
        key_val = ""
        url_val = ""
        a_type = "api_key_header"
        a_hdr = "api-key"
        if row:
            if row.api_key_encrypted:
                from app.services.secret_crypto import decrypt_secret
                key_val = decrypt_secret(row.api_key_encrypted)
            url_val = (row.base_url or "").rstrip("/")
            a_type = row.auth_type or a_type
            a_hdr = row.auth_header_name or a_hdr
        return key_val, url_val, a_type, a_hdr

    # Resolve provider config from DB (fallback to opencode_go if direct key absent and model is supported in Go)
    api_key = ""
    base_url = ""
    auth_type = "api_key_header"
    auth_header_name = "api-key"
    try:
        api_key, base_url, auth_type, auth_header_name = _load_provider_cfg(provider_key)
        if not api_key and provider_key in ("gemini", "mimo", "deepseek") and lower_model in OPENCODE_GO_MODELS:
            go_key, go_url, go_type, go_hdr = _load_provider_cfg("opencode_go")
            if go_key:
                provider_key = "opencode_go"
                api_key, base_url, auth_type, auth_header_name = go_key, go_url, go_type, go_hdr
    except Exception:
        pass

    if not api_key:
        raise HTTPException(400, {"code": "PROMPT_PROVIDER_NOT_CONFIGURED", "provider": provider_key})

    # Build request based on provider type
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            if provider_key == "opencode_go":
                resp = await call_opencode_go_async(
                    api_key=api_key,
                    model=raw_model,
                    messages=[{"role": "user", "content": content}],
                    base_url=base_url or DEFAULT_OPENCODE_GO_BASE_URL,
                    system_prompt="你是一个专业的 AI 助手。",
                    temperature=p.temperature,
                    max_tokens=1500,
                    timeout=30,
                )
                if resp.status_code != 200:
                    return {"success": False, "code": "PROMPT_PROVIDER_ERROR", "error": error_message("PROMPT_PROVIDER_ERROR", locale), "locale": locale}
                text = extract_opencode_go_text(detect_opencode_go_protocol(raw_model), resp.json())
                return {"success": True, "output": text, "prompt_used": content, "locale": locale}

            if provider_key == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{raw_model}:generateContent"
                payload = {
                    "contents": [{"parts": [{"text": content}]}],
                    "generationConfig": {"temperature": p.temperature},
                }
                resp = await client.post(url, params={"key": api_key}, json=payload)
                if resp.status_code != 200:
                    return {"success": False, "code": "PROMPT_PROVIDER_ERROR", "error": error_message("PROMPT_PROVIDER_ERROR", locale), "locale": locale}
                data = resp.json()
                text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                return {"success": True, "output": text, "prompt_used": content, "locale": locale}

            elif provider_key in ("mimo", "deepseek"):
                if not base_url:
                    base_url = "https://api.xiaomimimo.com/v1" if provider_key == "mimo" else "https://api.deepseek.com"
                url = f"{base_url}/chat/completions"
                headers = {"Content-Type": "application/json"}
                if auth_type == "bearer" or auth_header_name.lower() == "authorization":
                    headers["Authorization"] = f"Bearer {api_key}"
                else:
                    headers["api-key"] = api_key
                effective_model = (
                    normalize_mimo_model(raw_model)
                    if provider_key == "mimo"
                    else normalize_deepseek_model(raw_model)
                )
                payload = {
                    "model": effective_model,
                    "messages": [
                        {"role": "system", "content": "你是一个专业的 AI 助手。"},
                        {"role": "user", "content": content},
                    ],
                    "temperature": p.temperature,
                    "max_completion_tokens": 4096 if provider_key == "mimo" else 1024,
                    "stream": False,
                }
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code != 200:
                    return {"success": False, "code": "PROMPT_PROVIDER_ERROR", "error": error_message("PROMPT_PROVIDER_ERROR", locale), "locale": locale}
                data = resp.json()
                choices = data.get("choices", [])
                text = choices[0].get("message", {}).get("content", "") if choices else ""
                return {"success": True, "output": text, "prompt_used": content, "locale": locale}

            else:
                return {"success": False, "code": "PROMPT_UNSUPPORTED_MODEL", "error": error_message("PROMPT_UNSUPPORTED_MODEL", locale), "locale": locale}

    except httpx.TimeoutException:
        return {"success": False, "code": "PROMPT_TIMEOUT", "error": error_message("PROMPT_TIMEOUT", locale), "locale": locale}
    except httpx.ConnectError:
        return {"success": False, "code": "PROMPT_PROVIDER_UNREACHABLE", "error": error_message("PROMPT_PROVIDER_UNREACHABLE", locale), "locale": locale}
    except Exception as e:
        return {"success": False, "code": "PROMPT_PROVIDER_ERROR", "error": error_message("PROMPT_PROVIDER_ERROR", locale), "locale": locale}


@router.get("/{prompt_id}/versions")
def get_versions(prompt_id: int, request: Request, admin=Depends(get_current_admin), db=Depends(get_db)):
    p = db.get(PromptConfig, prompt_id)
    if not p:
        raise HTTPException(404, {"code": "PROMPT_NOT_FOUND"})
    versions = (
        db.query(PromptVersion)
        .filter_by(prompt_config_id=prompt_id)
        .order_by(PromptVersion.version.desc())
        .all()
    )
    # Include current version
    result = [{
        "version": p.version,
        "content": p.content,
        "model_name": p.model_name,
        "temperature": p.temperature,
        "updated_at": to_beijing_str(p.updated_at),
        "updated_by": p.updated_by,
        "is_current": True,
    }]
    for v in versions:
        result.append({
            "version": v.version,
            "content": v.content,
            "model_name": v.model_name,
            "temperature": v.temperature,
            "updated_at": to_beijing_str(v.updated_at),
            "updated_by": v.updated_by,
            "is_current": False,
        })
    return result


@router.get("/{prompt_id}/diff")
def diff_versions(
    prompt_id: int,
    v1: int,
    v2: int,
    request: Request,
    admin=Depends(get_current_admin),
    db=Depends(get_db),
):
    p = db.get(PromptConfig, prompt_id)
    if not p:
        raise HTTPException(404, {"code": "PROMPT_NOT_FOUND"})

    def _get_content(version: int) -> str:
        if version == p.version:
            return p.content
        rec = db.query(PromptVersion).filter_by(prompt_config_id=prompt_id, version=version).first()
        if not rec:
            raise HTTPException(404, {"code": "PROMPT_VERSION_NOT_FOUND"})
        return rec.content

    content_a = _get_content(v1)
    content_b = _get_content(v2)

    diff = list(difflib.unified_diff(
        content_a.splitlines(keepends=True),
        content_b.splitlines(keepends=True),
        fromfile=f"v{v1}",
        tofile=f"v{v2}",
    ))

    return {"v1": v1, "v2": v2, "diff": "".join(diff), "locale": request_locale(request)}


@router.post("/{prompt_id}/restore-default")
def restore_default(
    prompt_id: int,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Restore prompt content to its default_content."""
    p = db.get(PromptConfig, prompt_id)
    if not p:
        raise HTTPException(404, {"code": "PROMPT_NOT_FOUND"})
    if not p.default_content:
        raise HTTPException(400, {"code": "PROMPT_DEFAULT_NOT_FOUND"})

    # Save current version to history
    version_record = PromptVersion(
        prompt_config_id=p.id,
        version=p.version,
        content=p.content,
        variables=p.variables,
        model_name=p.model_name,
        temperature=p.temperature,
        updated_at=p.updated_at,
        updated_by=p.updated_by,
    )
    db.add(version_record)
    p.version += 1
    p.content = p.default_content
    p.updated_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    p.updated_by = admin.username
    db.commit()
    db.refresh(p)
    return _serialize(p, requested_locale=request_locale(request))


@router.post("/preview")
def preview_prompt(
    body: PromptPreviewRequest,
    request: Request,
    admin=Depends(get_current_admin),
):
    """Preview a prompt with variable substitution (no model call)."""
    content = body.content
    for key, value in body.variables.items():
        content = content.replace(f"{{{key}}}", str(value))
    return {"preview": content, "locale": request_locale(request)}


def _serialize(p: PromptConfig, *, requested_locale: str | None = None) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "locale": p.locale or "zh-CN",
        "requested_locale": requested_locale or p.locale or "zh-CN",
        "display_name": p.display_name,
        "description": p.description or "",
        "category": p.category or "",
        "prompt_type": p.prompt_type or "",
        "content": p.content,
        "default_content": p.default_content or "",
        "variables": p.variables,
        "model_name": p.model_name,
        "temperature": p.temperature,
        "is_active": p.is_active,
        "version": p.version,
        "updated_at": to_beijing_str(p.updated_at),
        "updated_by": p.updated_by or "",
    }
