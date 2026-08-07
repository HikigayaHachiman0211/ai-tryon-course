from __future__ import annotations

import difflib
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_admin
from app.config import get_settings
from app.database import PromptConfig, PromptVersion, AdminUser, get_db
from app.routers import to_beijing_str


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
    category: str | None = None,
    prompt_type: str | None = None,
    is_active: bool | None = None,
    keyword: str | None = None,
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
    prompts = query.order_by(PromptConfig.id).all()
    return [_serialize(p) for p in prompts]


@router.get("/{prompt_id}")
def get_prompt(prompt_id: int, admin=Depends(get_current_admin), db=Depends(get_db)):
    p = db.get(PromptConfig, prompt_id)
    if not p:
        raise HTTPException(404, "Prompt 不存在")
    return _serialize(p)


@router.put("/{prompt_id}")
def update_prompt(
    prompt_id: int,
    body: PromptUpdateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db=Depends(get_db),
):
    p = db.get(PromptConfig, prompt_id)
    if not p:
        raise HTTPException(404, "Prompt 不存在")

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
    return _serialize(p)


@router.post("/{prompt_id}/test")
async def test_prompt(
    prompt_id: int,
    body: PromptTestRequest,
    admin=Depends(get_current_admin),
    db=Depends(get_db),
):
    """Test a prompt by calling the configured LLM provider.

    Uses the prompt's model_name to determine which provider to call.
    All errors are sanitized before returning to the frontend.
    """
    p = db.get(PromptConfig, prompt_id)
    if not p:
        raise HTTPException(404, "Prompt 不存在")

    # Substitute variables
    content = p.content
    for key, value in body.test_params.items():
        content = content.replace(f"{{{key}}}", str(value))

    # Determine provider from model_name
    model_name = (p.model_name or "").strip().lower()
    if model_name.startswith("mimo"):
        provider_key = "mimo"
    elif model_name.startswith("deepseek"):
        provider_key = "deepseek"
    else:
        provider_key = "gemini"

    # Resolve provider config from DB (via admin database directly)
    api_key = ""
    base_url = ""
    auth_type = "api_key_header"
    auth_header_name = "api-key"
    try:
        from app.database import AIAPIProvider
        provider_row = db.query(AIAPIProvider).filter_by(provider_key=provider_key, enabled=True).first()
        if provider_row:
            if provider_row.api_key_encrypted:
                from app.services.secret_crypto import decrypt_secret
                api_key = decrypt_secret(provider_row.api_key_encrypted)
            base_url = (provider_row.base_url or "").rstrip("/")
            auth_type = provider_row.auth_type or auth_type
            auth_header_name = provider_row.auth_header_name or auth_header_name
    except Exception:
        pass

    if not api_key:
        raise HTTPException(400, f"未配置 {provider_key} 的 API Key，请先在 AI 模型管理页面配置")

    # Build request based on provider type
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            if provider_key == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{p.model_name}:generateContent"
                payload = {
                    "contents": [{"parts": [{"text": content}]}],
                    "generationConfig": {"temperature": p.temperature},
                }
                resp = await client.post(url, params={"key": api_key}, json=payload)
                if resp.status_code != 200:
                    return {"success": False, "error": f"API 返回 HTTP {resp.status_code}"}
                data = resp.json()
                text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                return {"success": True, "output": text, "prompt_used": content}

            elif provider_key in ("mimo", "deepseek"):
                if not base_url:
                    base_url = "https://api.xiaomimimo.com/v1" if provider_key == "mimo" else "https://api.deepseek.com"
                url = f"{base_url}/chat/completions"
                headers = {"Content-Type": "application/json"}
                if auth_type == "bearer" or auth_header_name.lower() == "authorization":
                    headers["Authorization"] = f"Bearer {api_key}"
                else:
                    headers["api-key"] = api_key
                payload = {
                    "model": p.model_name,
                    "messages": [
                        {"role": "system", "content": "你是一个专业的 AI 助手。"},
                        {"role": "user", "content": content},
                    ],
                    "temperature": p.temperature,
                    "max_completion_tokens": 1024,
                    "stream": False,
                }
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code != 200:
                    return {"success": False, "error": f"API 返回 HTTP {resp.status_code}"}
                data = resp.json()
                choices = data.get("choices", [])
                text = choices[0].get("message", {}).get("content", "") if choices else ""
                return {"success": True, "output": text, "prompt_used": content}

            else:
                return {"success": False, "error": f"不支持的模型类型: {provider_key}"}

    except httpx.TimeoutException:
        return {"success": False, "error": "API 调用超时（30秒），请检查网络或稍后重试"}
    except httpx.ConnectError:
        return {"success": False, "error": "无法连接到 API 服务器，请检查网络配置"}
    except Exception as e:
        return {"success": False, "error": _sanitize_error(str(e))}


@router.get("/{prompt_id}/versions")
def get_versions(prompt_id: int, admin=Depends(get_current_admin), db=Depends(get_db)):
    p = db.get(PromptConfig, prompt_id)
    if not p:
        raise HTTPException(404, "Prompt 不存在")
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
    admin=Depends(get_current_admin),
    db=Depends(get_db),
):
    p = db.get(PromptConfig, prompt_id)
    if not p:
        raise HTTPException(404, "Prompt 不存在")

    def _get_content(version: int) -> str:
        if version == p.version:
            return p.content
        rec = db.query(PromptVersion).filter_by(prompt_config_id=prompt_id, version=version).first()
        if not rec:
            raise HTTPException(404, f"版本 {version} 不存在")
        return rec.content

    content_a = _get_content(v1)
    content_b = _get_content(v2)

    diff = list(difflib.unified_diff(
        content_a.splitlines(keepends=True),
        content_b.splitlines(keepends=True),
        fromfile=f"v{v1}",
        tofile=f"v{v2}",
    ))

    return {"v1": v1, "v2": v2, "diff": "".join(diff)}


@router.post("/{prompt_id}/restore-default")
def restore_default(
    prompt_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Restore prompt content to its default_content."""
    p = db.get(PromptConfig, prompt_id)
    if not p:
        raise HTTPException(404, "Prompt 不存在")
    if not p.default_content:
        raise HTTPException(400, "该 Prompt 没有默认内容可恢复")

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
    return _serialize(p)


@router.post("/preview")
def preview_prompt(
    body: PromptPreviewRequest,
    admin=Depends(get_current_admin),
):
    """Preview a prompt with variable substitution (no model call)."""
    content = body.content
    for key, value in body.variables.items():
        content = content.replace(f"{{{key}}}", str(value))
    return {"preview": content}


def _serialize(p: PromptConfig) -> dict:
    return {
        "id": p.id,
        "name": p.name,
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
