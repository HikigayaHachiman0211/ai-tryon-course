"""Voice API router — ASR, TTS, voice config, voice catalog.

All endpoints are prefixed under /api/assistant/voice/ or /api/assistant/.
Reuses the existing ai_runtime_config and prompt_loader for config/prompt resolution.
"""
from __future__ import annotations

import logging
import os
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette import status

from app.ai_runtime_config import resolve_feature_config, resolve_provider_config
from app.assistant.voice.audio_utils import (
    ALLOWED_MIME_TYPES,
    detect_audio_mime,
    maybe_normalize_asr_text,
    validate_asr_audio,
)
from app.assistant.voice.mimo_asr import call_mimo_asr
from app.assistant.voice.mimo_tts import call_mimo_tts
from app.assistant.voice.schemas import (
    ASRResponse,
    TTSRequest,
    TTSResponse,
    VoiceCatalogItem,
    VoicePublicConfig,
)
from app.assistant.voice.voice_catalog import (
    AVAILABLE_VOICE_NAMES,
    DEFAULT_VOICE,
    get_all_catalog_items,
    get_published_clone_voices,
    resolve_voice,
)
from app.assistant.voice.voice_rate_limit import check_rate_limit
from app.prompt_loader import load_active_prompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assistant", tags=["assistant-voice"])

# Temp directory for TTS audio files
_TTS_TEMP_DIR = Path(tempfile.gettempdir()) / "ai_tryon_tts_audio"
_TTS_TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Max age for temp audio files (10 minutes)
_AUDIO_MAX_AGE_SECONDS = 600

# Max raw audio bytes before we reject without reading fully into memory.
# Matches audio_utils.MAX_BASE64_BYTES (10 MB base64 ≈ 7.5 MB raw).
_MAX_AUDIO_RAW_BYTES = 7_864_320  # ~7.5 MB

# Fallback style prompt
_TTS_STYLE_FALLBACK = (
    "你是一个亲切自然的羽绒服 AI 导购助手。语气温和、清晰、不过度夸张，像在帮用户挑选适合的冬季外套。"
)


def _cleanup_old_audio_files() -> None:
    """Remove TTS audio files older than _AUDIO_MAX_AGE_SECONDS."""
    try:
        now = time.time()
        for f in _TTS_TEMP_DIR.iterdir():
            if f.is_file() and (now - f.stat().st_mtime) > _AUDIO_MAX_AGE_SECONDS:
                f.unlink(missing_ok=True)
    except Exception as exc:
        logger.debug("Audio cleanup error: %s", exc)


_FEATURE_TO_MODEL_KEYWORD: dict[str, str] = {
    "voice_asr": "asr",
    "voice_tts": "tts",
    "voice_clone": "clone",
}


def _resolve_voice_provider_config(
    feature_key: str,
    provider_key: str,
    forced_default_model: str,
) -> tuple[dict, str | None]:
    """Resolve voice provider config with safe model isolation.

    Strategy:
    1. Check feature config (include_disabled=True) — if disabled, return error.
    2. Read specialized provider (mimo_asr / mimo_tts).
    3. If specialized provider has no API key, borrow key/auth from shared 'mimo'.
    4. Model is NEVER borrowed from shared 'mimo' — always use:
       feature.default_model > specialized provider.default_model > forced_default_model.
    5. Validate model name contains expected keyword.

    Returns (config_dict, error_reason_or_none).
    """
    # Step 1: Check feature config — include_disabled=True so we detect disabled features
    feat = resolve_feature_config(feature_key, include_disabled=True)
    if feat and feat.get("enabled") is False:
        return {}, f"{feature_key} 功能已在后台禁用。"

    # Step 2: Read specialized provider
    cfg = resolve_provider_config(provider_key)

    # Step 3: Borrow shared key if specialized has none
    if not cfg.get("api_key"):
        shared = resolve_provider_config("mimo")
        cfg["api_key"] = shared.get("api_key", "")
        cfg["base_url"] = shared.get("base_url", cfg.get("base_url", ""))
        cfg["auth_type"] = shared.get("auth_type", cfg.get("auth_type", ""))
        cfg["auth_header_name"] = shared.get("auth_header_name", cfg.get("auth_header_name", ""))
        # Do NOT copy shared.default_model — keep specialized model

    # Step 4: Resolve model — never from shared 'mimo'
    model = ""
    if feat and feat.get("default_model"):
        model = feat["default_model"]
    if not model and cfg.get("default_model"):
        model = cfg["default_model"]
    if not model:
        model = forced_default_model
    cfg["default_model"] = model

    # Step 5: Validate model name — explicit keyword mapping
    expected_keyword = _FEATURE_TO_MODEL_KEYWORD.get(feature_key, "")
    if expected_keyword and expected_keyword not in model.lower():
        error_code = {
            "voice_asr": "ASR_MODEL_MISCONFIGURED",
            "voice_tts": "TTS_MODEL_MISCONFIGURED",
            "voice_clone": "CLONE_MODEL_MISCONFIGURED",
        }.get(feature_key, "VOICE_MODEL_MISCONFIGURED")
        return {}, f"模型配置错误: {feature_key} 的模型 '{model}' 不包含 '{expected_keyword}'。"

    return cfg, None


def _check_asr_enabled() -> tuple[bool, str]:
    """Check if ASR is available. Returns (enabled, reason_if_disabled)."""
    cfg, err = _resolve_voice_provider_config("voice_asr", "mimo_asr", "mimo-v2.5-asr")
    if err:
        return False, err
    if not cfg.get("api_key"):
        return False, "语音识别暂不可用，请改用文字输入。"
    return True, ""


def _check_tts_enabled() -> tuple[bool, str]:
    """Check if TTS is available. Returns (enabled, reason_if_disabled)."""
    cfg, err = _resolve_voice_provider_config("voice_tts", "mimo_tts", "mimo-v2.5-tts")
    if err:
        return False, err
    if not cfg.get("api_key"):
        return False, "语音播报暂不可用，文字回复仍可查看。"
    return True, ""


# ---------------------------------------------------------------------------
# GET /api/assistant/voice/config/public
# ---------------------------------------------------------------------------
@router.get("/voice/config/public", response_model=VoicePublicConfig)
def get_voice_public_config() -> VoicePublicConfig:
    """Return non-sensitive voice configuration to the main site frontend.

    Never returns API keys, decrypted secrets, or clone sample URLs.
    Includes disabled reasons from backend feature config.
    """
    asr_ok, asr_reason = _check_asr_enabled()
    tts_ok, tts_reason = _check_tts_enabled()

    # Check voice_clone feature — include_disabled=True so we detect disabled state
    clone_feat = resolve_feature_config("voice_clone", include_disabled=True)
    clone_feat_enabled = clone_feat.get("enabled", False) if clone_feat else False

    # Only return clone voices if feature is enabled
    clone_voices = get_published_clone_voices() if clone_feat_enabled else []
    clone_enabled = clone_feat_enabled and len(clone_voices) > 0

    return VoicePublicConfig(
        asr_enabled=asr_ok,
        tts_enabled=tts_ok,
        voice_clone_enabled=clone_enabled,
        asr_disabled_reason=asr_reason or "",
        tts_disabled_reason=tts_reason or "",
        default_voice=DEFAULT_VOICE,
        available_voices=AVAILABLE_VOICE_NAMES,
        published_clone_voices=[
            {"id": v["id"], "name": v["name"], "description": v.get("description", "")}
            for v in clone_voices
        ],
    )


# ---------------------------------------------------------------------------
# GET /api/assistant/voice/catalog/public
# ---------------------------------------------------------------------------
@router.get("/voice/catalog/public", response_model=list[VoiceCatalogItem])
def get_voice_catalog_public() -> list[VoiceCatalogItem]:
    """Return all available voices (presets + published clones).

    Never returns unpublished, disabled, or raw sample audio.
    """
    items = get_all_catalog_items()
    return [VoiceCatalogItem(**item) for item in items]


# ---------------------------------------------------------------------------
# POST /api/assistant/asr
# ---------------------------------------------------------------------------
@router.post("/asr", response_model=ASRResponse)
async def asr_recognize(
    audio: UploadFile = File(..., description="音频文件 (wav/mp3)"),
    session_id: str = Form(default=""),
    language: str = Form(default="zh"),
    format: str | None = Form(default=None),
) -> ASRResponse:
    """Speech-to-text endpoint. Accepts wav/mp3 audio, returns recognized text.

    Reused by both normal voice input and phone call mode.
    """
    # Validate language
    _ALLOWED_LANGUAGES = {"zh", "en", "auto"}
    if language not in _ALLOWED_LANGUAGES:
        return ASRResponse(
            success=False,
            error={"code": "INVALID_LANGUAGE", "message": f"不支持的语言: {language}。支持: zh, en, auto。"},
            language=language,
        )

    # Rate limit
    allowed, msg = check_rate_limit(session_id, "asr")
    if not allowed:
        return ASRResponse(
            success=False,
            error={"code": "RATE_LIMITED", "message": msg},
            language=language,
        )

    # Detect format
    filename = audio.filename or "audio.wav"
    content_type = audio.content_type
    mime_type = detect_audio_mime(filename, content_type) or format_to_mime(format)

    if not mime_type:
        return ASRResponse(
            success=False,
            error={
                "code": "UNSUPPORTED_FORMAT",
                "message": "当前浏览器录音格式暂不支持，请切换浏览器或使用文字输入。",
            },
            language=language,
        )

    # Pre-check: reject oversized uploads before loading into memory.
    # Seek the spooled temp file to measure size without fully reading it.
    try:
        f = audio.file
        f.seek(0, 2)
        spooled_size = f.tell()
        f.seek(0)
        if spooled_size > _MAX_AUDIO_RAW_BYTES:
            return ASRResponse(
                success=False,
                error={
                    "code": "FILE_TOO_LARGE",
                    "message": f"音频文件过大（约 {spooled_size // (1024 * 1024)}MB），上限约 7.5MB。",
                },
                language=language,
            )
    except Exception:
        pass  # Seek not supported; fall through to post-read validation

    # Read and validate audio
    audio_bytes = await audio.read()
    validation_error = validate_asr_audio(audio_bytes, mime_type)
    if validation_error:
        return ASRResponse(
            success=False,
            error={"code": "INVALID_AUDIO", "message": validation_error},
            language=language,
        )

    # Check ASR availability — resolve config with model isolation
    asr_cfg, cfg_err = _resolve_voice_provider_config("voice_asr", "mimo_asr", "mimo-v2.5-asr")
    api_key = asr_cfg.get("api_key", "")
    if cfg_err or not api_key:
        return ASRResponse(
            success=False,
            error={"code": "ASR_CONFIG_MISSING", "message": cfg_err or "语音识别暂不可用，请改用文字输入。"},
            language=language,
        )

    # Call MiMo ASR — model is always ASR-specific, never chat model
    base_url = asr_cfg.get("base_url", "https://api.xiaomimimo.com/v1")
    model = asr_cfg.get("default_model", "mimo-v2.5-asr")

    recognized_text, meta = await call_mimo_asr(
        api_key=api_key,
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        model=model,
        base_url=base_url,
        language=language,
    )

    if recognized_text is None:
        error = meta.get("error", {"code": "ASR_FAILED", "message": "语音识别失败，请改用文字输入。"})
        return ASRResponse(
            success=False,
            provider="mimo",
            model=model,
            language=language,
            latency_ms=meta.get("latency_ms"),
            error=error,
        )

    # Normalize text
    normalized = maybe_normalize_asr_text(recognized_text)

    # Log non-sensitive info only
    logger.info("ASR success: text_len=%d, latency=%sms", len(normalized), meta.get("latency_ms"))

    return ASRResponse(
        success=True,
        text=recognized_text,
        normalized_text=normalized,
        provider="mimo",
        model=model,
        language=language,
        duration_ms=meta.get("duration_ms"),
        latency_ms=meta.get("latency_ms"),
    )


# ---------------------------------------------------------------------------
# POST /api/assistant/tts
# ---------------------------------------------------------------------------
@router.post("/tts", response_model=TTSResponse)
async def tts_synthesize(request: TTSRequest) -> TTSResponse:
    """Text-to-speech endpoint. Returns audio URL for playback.

    Reused by both normal voice input and phone call mode.
    """
    # Validate format
    _ALLOWED_TTS_FORMATS = {"wav", "mp3"}
    output_format = (request.format or "wav").strip().lower()
    if output_format not in _ALLOWED_TTS_FORMATS:
        return TTSResponse(
            success=False,
            voice=request.voice or DEFAULT_VOICE,
            error={"code": "INVALID_FORMAT", "message": f"不支持的音频格式: {output_format}。支持: wav, mp3。"},
        )

    # Rate limit
    allowed, msg = check_rate_limit(request.session_id, "tts")
    if not allowed:
        return TTSResponse(
            success=False,
            voice=request.voice or DEFAULT_VOICE,
            error={"code": "RATE_LIMITED", "message": msg},
        )

    # Validate text
    if not request.text or not request.text.strip():
        return TTSResponse(
            success=False,
            voice=request.voice or DEFAULT_VOICE,
            error={"code": "EMPTY_TEXT", "message": "播报文本为空。"},
        )

    # Truncate if too long
    text = request.text.strip()
    max_len = 300
    if len(text) > max_len:
        text = text[:max_len] + "……"

    # Check TTS availability — resolve config with model isolation
    tts_cfg, cfg_err = _resolve_voice_provider_config("voice_tts", "mimo_tts", "mimo-v2.5-tts")
    api_key = tts_cfg.get("api_key", "")
    if cfg_err or not api_key:
        return TTSResponse(
            success=False,
            voice=request.voice or DEFAULT_VOICE,
            error={"code": "TTS_CONFIG_MISSING", "message": cfg_err or "语音播报暂不可用，文字回复仍可查看。"},
        )

    # Resolve voice (handles clone fallback)
    effective_voice = resolve_voice(
        request.voice,
        request.clone_voice_id,
        request.voice_source,
    )

    # Load style prompt from DB or use fallback
    style_prompt = request.style_prompt
    if not style_prompt:
        style_prompt = load_active_prompt(
            "assistant_tts_style_prompt",
            fallback=_TTS_STYLE_FALLBACK,
        )

    # Call MiMo TTS — model is always TTS-specific, never chat model
    base_url = tts_cfg.get("base_url", "https://api.xiaomimimo.com/v1")
    model = tts_cfg.get("default_model", "mimo-v2.5-tts")

    audio_bytes, meta = await call_mimo_tts(
        api_key=api_key,
        text=text,
        voice=effective_voice,
        output_format=output_format,
        style_prompt=style_prompt,
        model=model,
        base_url=base_url,
    )

    if audio_bytes is None:
        error = meta.get("error", {"code": "TTS_FAILED", "message": "语音播报失败，文字回复仍可查看。"})
        return TTSResponse(
            success=False,
            voice=effective_voice,
            provider="mimo",
            model=model,
            format=output_format,
            error=error,
        )

    # Save to temp file and return URL
    _cleanup_old_audio_files()
    audio_id = uuid.uuid4().hex[:16]
    ext = "wav" if output_format == "wav" else "mp3"
    temp_path = _TTS_TEMP_DIR / f"{audio_id}.{ext}"
    temp_path.write_bytes(audio_bytes)

    audio_url = f"/api/assistant/tts/audio/{audio_id}.{ext}"

    logger.info("TTS success: audio_id=%s, voice=%s, size=%d", audio_id, effective_voice, len(audio_bytes))

    return TTSResponse(
        success=True,
        audio_url=audio_url,
        voice=effective_voice,
        provider="mimo",
        model=model,
        format=output_format,
    )


# ---------------------------------------------------------------------------
# GET /api/assistant/tts/audio/{audio_id}
# ---------------------------------------------------------------------------
@router.get("/tts/audio/{filename}")
def get_tts_audio(filename: str):
    """Serve a temporary TTS audio file.

    Security: no directory traversal, no directory listing, files auto-expire.
    """
    # Prevent path traversal
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

    file_path = _TTS_TEMP_DIR / safe_name
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio not found or expired")

    # Check age
    age = time.time() - file_path.stat().st_mtime
    if age > _AUDIO_MAX_AGE_SECONDS:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio expired")

    media_type = "audio/wav" if safe_name.endswith(".wav") else "audio/mpeg"
    return FileResponse(file_path, media_type=media_type)


def format_to_mime(fmt: str | None) -> str | None:
    """Convert format string to MIME type."""
    if not fmt:
        return None
    fmt = fmt.strip().lower()
    return {
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
    }.get(fmt)
