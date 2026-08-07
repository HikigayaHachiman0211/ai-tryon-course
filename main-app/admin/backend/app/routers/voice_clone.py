"""Admin voice clone management router.

Security:
- All endpoints require admin authentication.
- Upload validates real audio file headers, not just Content-Type.
- Clone is NOT a placeholder — returns VOICE_CLONE_PROVIDER_NOT_IMPLEMENTED if
  MiMo VoiceClone API is not configured.
- Only profiles with status=ready AND provider_voice_id set can be published.
- Upload directory is configurable, defaults to data/uploads/voice_clones.
"""
from __future__ import annotations

import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import AIAPIProvider, AdminUser, VoiceCloneProfile, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice-clones", tags=["voice-clones"])

# Upload constraints
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".wav", ".mp3"}

# Upload directory — configurable via env, defaults to data/uploads
_UPLOAD_DIR = os.environ.get(
    "VOICE_CLONE_UPLOAD_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "uploads", "voice_clones"),
)


def _ensure_upload_dir():
    os.makedirs(_UPLOAD_DIR, exist_ok=True)


def _validate_audio_header(data: bytes, filename: str) -> str | None:
    """Validate real audio file header bytes.

    Returns None if valid, error message if invalid.
    Checks WAV RIFF/WAVE header and MP3 ID3 or frame sync header.
    Does NOT trust Content-Type — reads actual bytes.
    """
    if len(data) < 12:
        return "文件过小，不是有效的音频文件。"

    lower_name = filename.lower()
    is_wav_ext = lower_name.endswith(".wav")
    is_mp3_ext = lower_name.endswith(".mp3")

    if not is_wav_ext and not is_mp3_ext:
        return f"不支持的文件扩展名。仅支持: {', '.join(ALLOWED_EXTENSIONS)}"

    # Check WAV header: RIFF....WAVE
    has_wav_header = data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    # Check MP3 header: ID3 tag or MPEG frame sync (0xFF 0xE0+)
    has_mp3_header = (data[:3] == b"ID3") or (len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0)

    if is_wav_ext and not has_wav_header:
        return "文件扩展名是 .wav 但文件头不是 RIFF/WAVE 格式。请上传真实的 WAV 文件。"
    if is_mp3_ext and not has_mp3_header:
        return "文件扩展名是 .mp3 但文件头不是有效的 MP3 格式。请上传真实的 MP3 文件。"

    # Cross-check: extension says wav but header is mp3, or vice versa
    if is_wav_ext and has_mp3_header and not has_wav_header:
        return "文件扩展名是 .wav 但内容是 MP3 格式。请使用正确的文件扩展名。"
    if is_mp3_ext and has_wav_header and not has_mp3_header:
        return "文件扩展名是 .mp3 但内容是 WAV 格式。请使用正确的文件扩展名。"

    # If neither header matches, reject
    if not has_wav_header and not has_mp3_header:
        return "无法识别音频格式。文件头既不是 WAV (RIFF/WAVE) 也不是 MP3 (ID3/frame sync)。"

    return None


@router.get("")
def list_voice_clones(
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """List all voice clone profiles. Requires admin auth."""
    profiles = db.query(VoiceCloneProfile).order_by(VoiceCloneProfile.created_at.desc()).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "gender": p.gender,
            "language": p.language,
            "provider_key": p.provider_key,
            "provider_voice_id": p.provider_voice_id,
            "status": p.status,
            "enabled": p.enabled,
            "is_published": p.is_published,
            "error_message": p.error_message_sanitized,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            "created_by": p.created_by,
            "updated_by": p.updated_by,
        }
        for p in profiles
    ]


@router.post("")
def create_voice_clone(
    name: str = Form(...),
    description: str = Form(default=""),
    gender: str = Form(default="female"),
    language: str = Form(default="zh"),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Create a new voice clone profile (draft). Requires admin auth."""
    profile = VoiceCloneProfile(
        name=name,
        description=description,
        gender=gender,
        language=language,
        status="draft",
        enabled=True,
        is_published=False,
        created_by=admin.username,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return {"id": profile.id, "status": profile.status}


@router.post("/{profile_id}/upload")
async def upload_reference_audio(
    profile_id: int,
    audio: UploadFile = File(..., description="参考音频 (wav/mp3)"),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Upload reference audio for a voice clone profile.

    Validates real file header bytes, not just Content-Type.
    Requires admin auth.
    """
    profile = db.query(VoiceCloneProfile).get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Read file content
    data = await audio.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="音频文件过大，上限 10MB。")

    # Validate real file header — do NOT trust Content-Type
    filename = audio.filename or "audio.wav"
    header_error = _validate_audio_header(data, filename)
    if header_error:
        raise HTTPException(status_code=400, detail=header_error)

    # Save to upload directory
    _ensure_upload_dir()
    ext = os.path.splitext(filename)[1].lower() or ".wav"
    safe_filename = f"{profile_id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(_UPLOAD_DIR, safe_filename)
    with open(filepath, "wb") as f:
        f.write(data)

    profile.source_audio_path = filepath
    profile.updated_by = admin.username
    db.commit()

    return {"ok": True, "filename": safe_filename}


@router.put("/{profile_id}")
def update_voice_clone(
    profile_id: int,
    name: str | None = Form(default=None),
    description: str | None = Form(default=None),
    gender: str | None = Form(default=None),
    language: str | None = Form(default=None),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Update voice clone profile metadata. Requires admin auth."""
    profile = db.query(VoiceCloneProfile).get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if name is not None:
        profile.name = name
    if description is not None:
        profile.description = description
    if gender is not None:
        profile.gender = gender
    if language is not None:
        profile.language = language
    profile.updated_by = admin.username
    db.commit()

    return {"ok": True}


@router.post("/{profile_id}/clone")
def trigger_clone(
    profile_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Trigger voice cloning.

    If MiMo VoiceClone API is not configured, returns
    VOICE_CLONE_PROVIDER_NOT_IMPLEMENTED and keeps status as draft/failed.
    Only marks ready when a real provider_voice_id is returned.
    """
    profile = db.query(VoiceCloneProfile).get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if not profile.source_audio_path:
        raise HTTPException(status_code=400, detail="请先上传参考音频。")

    # Check if mimo_voice_clone provider is configured with an API key
    provider = db.query(AIAPIProvider).filter_by(provider_key="mimo_voice_clone").first()
    if not provider or not provider.enabled or not provider.api_key_encrypted:
        profile.status = "failed"
        profile.error_message_sanitized = "声音克隆服务未配置。请联系管理员在 AI 模型/API 管理中配置 mimo_voice_clone Provider 的 API Key。"
        profile.updated_by = admin.username
        db.commit()
        return {
            "ok": False,
            "status": "failed",
            "error_code": "VOICE_CLONE_PROVIDER_NOT_CONFIGURED",
            "message": "声音克隆服务未配置。请先在 AI 模型/API 管理页面配置 mimo_voice_clone Provider 的 API Key，然后再尝试克隆。",
        }

    # TODO: When MiMo VoiceClone API is officially available, implement real call here.
    # Expected flow:
    #   1. Read and decrypt provider.api_key_encrypted
    #   2. Upload profile.source_audio_path to MiMo VoiceClone endpoint
    #   3. Poll for completion
    #   4. Save returned provider_voice_id
    #   5. Set status = "ready"
    #
    # For now, return NOT_IMPLEMENTED — do NOT create fake provider_voice_id.
    profile.status = "failed"
    profile.error_message_sanitized = "MiMo VoiceClone API 尚未正式接入。当前仅支持上传参考音频和配置草稿，不能执行克隆。"
    profile.updated_by = admin.username
    db.commit()
    return {
        "ok": False,
        "status": "failed",
        "error_code": "VOICE_CLONE_PROVIDER_NOT_IMPLEMENTED",
        "message": "MiMo VoiceClone API 尚未正式接入。当前仅支持上传参考音频和配置草稿，不能执行克隆操作。API 接入后此功能将自动可用。",
    }


@router.post("/{profile_id}/publish")
def publish_voice_clone(
    profile_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Publish a voice clone — makes it available on the main site.

    Requires status=ready AND provider_voice_id to be set.
    """
    profile = db.query(VoiceCloneProfile).get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if profile.status != "ready":
        raise HTTPException(status_code=400, detail=f"只能发布状态为 ready 的音色，当前状态: {profile.status}")

    if not profile.provider_voice_id:
        raise HTTPException(status_code=400, detail="provider_voice_id 为空，无法发布。请先完成克隆。")

    profile.is_published = True
    profile.enabled = True
    profile.updated_by = admin.username
    db.commit()

    return {"ok": True, "is_published": True}


@router.post("/{profile_id}/unpublish")
def unpublish_voice_clone(
    profile_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Unpublish a voice clone — hides it from the main site."""
    profile = db.query(VoiceCloneProfile).get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile.is_published = False
    profile.updated_by = admin.username
    db.commit()

    return {"ok": True, "is_published": False}


@router.delete("/{profile_id}")
def delete_voice_clone(
    profile_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Disable (soft delete) a voice clone profile."""
    profile = db.query(VoiceCloneProfile).get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile.enabled = False
    profile.is_published = False
    profile.updated_by = admin.username
    db.commit()

    return {"ok": True}
