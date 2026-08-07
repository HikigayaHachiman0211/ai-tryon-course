"""Audio utility functions for ASR/TTS — format detection, validation, encoding."""
from __future__ import annotations

import base64
import logging
import re

logger = logging.getLogger(__name__)

# Allowed MIME types for ASR input — strictly wav/mp3 only
ALLOWED_MIME_TYPES = {
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
}

# Max base64-encoded size (10 MB)
MAX_BASE64_BYTES = 10 * 1024 * 1024


def detect_audio_mime(filename: str, content_type: str | None) -> str | None:
    """Detect audio MIME type from filename and Content-Type header.

    Returns None if format cannot be determined.
    """
    # Prefer Content-Type if explicitly provided and valid
    if content_type:
        ct = content_type.strip().lower().split(";")[0].strip()
        if ct in ALLOWED_MIME_TYPES:
            return ct

    # Fall back to extension
    ext_map = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".mpeg": "audio/mpeg",
    }
    lower_name = filename.lower()
    for ext, mime in ext_map.items():
        if lower_name.endswith(ext):
            return mime

    return None


def _has_wav_header(data: bytes) -> bool:
    """Check if data starts with RIFF....WAVE header."""
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def _has_mp3_header(data: bytes) -> bool:
    """Check if data starts with ID3 tag or MPEG frame sync word."""
    if len(data) < 3:
        return False
    # ID3v2 tag
    if data[:3] == b"ID3":
        return True
    # MPEG frame sync: 11 set bits (0xFF 0xE0 or higher)
    if data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return True
    return False


def validate_audio_content_signature(file_bytes: bytes, declared_mime: str | None) -> str | None:
    """Validate that the actual audio content matches the declared MIME type.

    Strict: WAV declaration requires RIFF/WAVE header; MP3 declaration requires ID3 or frame sync.
    Unknown/unsupported bytes are always rejected — no pass-through for ambiguous content.
    Returns error message if mismatch or invalid, None if OK.
    """
    if not file_bytes:
        return None  # Empty handled by caller

    if len(file_bytes) < 12:
        return "音频文件过短或格式无效。"

    is_wav_content = _has_wav_header(file_bytes)
    is_mp3_content = _has_mp3_header(file_bytes)

    if declared_mime in ("audio/wav", "audio/wave", "audio/x-wav"):
        if is_wav_content:
            return None
        return "音频内容与声明格式不匹配，请上传真实 WAV 或 MP3。"

    if declared_mime in ("audio/mpeg", "audio/mp3"):
        if is_mp3_content:
            return None
        return "音频内容与声明格式不匹配，请上传真实 WAV 或 MP3。"

    return "不支持的音频格式。"


def validate_asr_audio(file_bytes: bytes, mime_type: str | None) -> str | None:
    """Validate audio for ASR. Returns error message or None if valid."""
    if not file_bytes:
        return "音频文件为空。"

    if mime_type and mime_type not in ALLOWED_MIME_TYPES:
        return f"不支持的音频格式: {mime_type}。请使用 wav 或 mp3。"

    # Check base64 size limit
    encoded_size = len(base64.b64encode(file_bytes))
    if encoded_size > MAX_BASE64_BYTES:
        return f"音频文件过大（Base64 后 {encoded_size // (1024*1024)}MB），上限 {MAX_BASE64_BYTES // (1024*1024)}MB。"

    # Content signature check
    sig_error = validate_audio_content_signature(file_bytes, mime_type)
    if sig_error:
        return sig_error

    return None


def encode_audio_data_url(file_bytes: bytes, mime_type: str) -> str:
    """Encode audio bytes as a base64 data URL for MiMo ASR API."""
    b64 = base64.b64encode(file_bytes).decode("ascii")
    return f"data:{mime_type};base64,{b64}"


def maybe_normalize_asr_text(text: str) -> str:
    """Post-process ASR text: trim, normalize punctuation, fix common misrecognitions."""
    if not text:
        return ""

    result = text.strip()

    # Remove excessive whitespace
    result = re.sub(r"\s+", " ", result)

    # Fix common misrecognitions for clothing domain
    result = result.replace("羽绒福", "羽绒服")
    result = result.replace("羽容服", "羽绒服")
    result = result.replace("雨绒服", "羽绒服")

    return result
