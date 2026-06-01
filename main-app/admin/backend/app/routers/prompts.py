from __future__ import annotations

import difflib
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_admin
from app.config import get_settings
from app.database import PromptConfig, PromptVersion, AdminUser, get_db
from app.routers import to_beijing_str

router = APIRouter(prefix="/api/admin/prompts", tags=["prompts"])


class PromptUpdateRequest(BaseModel):
    content: str | None = None
    variables: list[str] | None = None
    model_name: str | None = None
    temperature: float | None = None
    is_active: bool | None = None
    display_name: str | None = None


class PromptTestRequest(BaseModel):
    test_params: dict = {}


@router.get("")
def list_prompts(admin=Depends(get_current_admin), db=Depends(get_db)):
    prompts = db.query(PromptConfig).order_by(PromptConfig.id).all()
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
    p = db.get(PromptConfig, prompt_id)
    if not p:
        raise HTTPException(404, "Prompt 不存在")

    settings = get_settings()
    if not settings.GEMINI_API_KEY:
        raise HTTPException(400, "未配置 GEMINI_API_KEY")

    # Substitute variables
    content = p.content
    for key, value in body.test_params.items():
        content = content.replace(f"{{{key}}}", str(value))

    # Call Gemini API
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{p.model_name}:generateContent?key={settings.GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": content}]}],
        "generationConfig": {"temperature": p.temperature},
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                return {"success": False, "error": f"Gemini API 返回 {resp.status_code}: {resp.text[:500]}"}
            data = resp.json()
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return {"success": True, "output": text, "prompt_used": content}
    except Exception as e:
        return {"success": False, "error": str(e)}


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


def _serialize(p: PromptConfig) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "display_name": p.display_name,
        "content": p.content,
        "variables": p.variables,
        "model_name": p.model_name,
        "temperature": p.temperature,
        "is_active": p.is_active,
        "version": p.version,
        "updated_at": to_beijing_str(p.updated_at),
        "updated_by": p.updated_by,
    }
