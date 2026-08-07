"""MiMo TTS client — calls mimo-v2.5-tts for text-to-speech."""
from __future__ import annotations

import base64
import logging
import re
import time

import httpx

logger = logging.getLogger(__name__)

# Default style prompt for the assistant's voice
_DEFAULT_STYLE_PROMPT = (
    "你是一个亲切自然的羽绒服 AI 导购助手。语气温和、清晰、不过度夸张，像在帮用户挑选适合的冬季外套。"
)


def _sanitize_for_log(text: str) -> str:
    """Strip API keys, full TTS text from log messages."""
    text = re.sub(r"api[_-]?key\s*[:=]\s*\S+", "api-key=[REDACTED]", text, flags=re.IGNORECASE)
    if len(text) > 300:
        text = text[:300] + "..."
    return text


async def call_mimo_tts(
    *,
    api_key: str,
    text: str,
    voice: str = "茉莉",
    output_format: str = "wav",
    style_prompt: str | None = None,
    model: str = "mimo-v2.5-tts",
    base_url: str = "https://api.xiaomimimo.com/v1",
) -> tuple[bytes | None, dict]:
    """Call MiMo TTS API. Returns (audio_bytes, metadata).

    Returns (None, metadata) on failure — never raises.
    """
    meta: dict = {"model": model, "provider": "mimo", "voice": voice, "format": output_format}
    start = time.time()

    if not api_key:
        meta["error"] = {"code": "TTS_CONFIG_MISSING", "message": "语音播报暂不可用，文字回复仍可查看。"}
        return None, meta

    if not text or not text.strip():
        meta["error"] = {"code": "TTS_EMPTY_TEXT", "message": "播报文本为空。"}
        return None, meta

    # Truncate text to max length
    max_len = 300
    if len(text) > max_len:
        text = text[:max_len] + "……"

    effective_style = style_prompt or _DEFAULT_STYLE_PROMPT

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": effective_style},
            {"role": "assistant", "content": text},
        ],
        "audio": {
            "format": output_format,
            "voice": voice,
        },
    }

    # Log truncated text length only — never log full text
    logger.info("TTS request: text_len=%d, voice=%s, format=%s", len(text), voice, output_format)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            latency_ms = int((time.time() - start) * 1000)
            meta["latency_ms"] = latency_ms

            if resp.status_code != 200:
                logger.warning("MiMo TTS HTTP %d: %s", resp.status_code, _sanitize_for_log(resp.text[:200]))
                meta["error"] = {"code": "TTS_API_ERROR", "message": f"语音播报服务返回错误 ({resp.status_code})。"}
                return None, meta

            data = resp.json()

            # Log response structure for debugging (no secrets)
            resp_keys = list(data.keys())
            choices = data.get("choices", [])
            choice_keys = list(choices[0].keys()) if choices else []
            msg_keys = list(choices[0].get("message", {}).keys()) if choices else []
            has_text_content = bool(choices and choices[0].get("message", {}).get("content"))
            logger.info(
                "MiMo TTS response: model=%s, status=%d, resp_keys=%s, choice_keys=%s, msg_keys=%s, has_text=%s",
                model, resp.status_code, resp_keys, choice_keys, msg_keys, has_text_content,
            )

            # Try to extract audio from response
            audio_bytes = _extract_audio_from_response(data, output_format)
            if audio_bytes:
                # Validate audio magic numbers
                if output_format == "wav" and not (audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE"):
                    logger.warning("MiMo TTS: returned audio claims wav but header mismatch, first 12 bytes: %s", audio_bytes[:12].hex())
                    meta["error"] = {"code": "TTS_INVALID_AUDIO", "message": "语音播报返回了无效音频格式。"}
                    return None, meta
                if output_format == "mp3" and not (audio_bytes[:3] == b"ID3" or (audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xE0) == 0xE0)):
                    logger.warning("MiMo TTS: returned audio claims mp3 but header mismatch, first 4 bytes: %s", audio_bytes[:4].hex())
                    meta["error"] = {"code": "TTS_INVALID_AUDIO", "message": "语音播报返回了无效音频格式。"}
                    return None, meta

                meta["audio_size_bytes"] = len(audio_bytes)
                return audio_bytes, meta

            # Detailed failure log
            logger.warning(
                "MiMo TTS no audio extracted: model=%s, resp_keys=%s, choice_keys=%s, msg_keys=%s, has_text=%s",
                model, resp_keys, choice_keys, msg_keys, has_text_content,
            )
            meta["error"] = {"code": "TTS_NO_AUDIO", "message": "语音播报未返回音频数据。"}
            return None, meta

    except httpx.TimeoutException:
        latency_ms = int((time.time() - start) * 1000)
        meta["latency_ms"] = latency_ms
        meta["error"] = {"code": "TTS_TIMEOUT", "message": "语音播报超时，请稍后重试。"}
        logger.warning("MiMo TTS timeout after %dms", latency_ms)
        return None, meta
    except Exception as exc:
        latency_ms = int((time.time() - start) * 1000)
        meta["latency_ms"] = latency_ms
        meta["error"] = {"code": "TTS_NETWORK_ERROR", "message": "网络请求失败，请稍后重试。"}
        logger.warning("MiMo TTS error: %s", _sanitize_for_log(str(exc)))
        return None, meta


def _extract_audio_from_response(data: dict, output_format: str) -> bytes | None:
    """Extract audio bytes from TTS API response.

    Handles multiple response formats:
    - data.choices[0].message.audio.data (base64)
    - data.choices[0].audio.data (base64)
    - data.audio.data (base64)
    - data.audio_url (URL — not handled here, caller should download)
    """
    # Try standard choices path
    choices = data.get("choices", [])
    if choices:
        msg = choices[0].get("message", {})
        audio_obj = msg.get("audio") or choices[0].get("audio")
        if audio_obj:
            return _decode_audio_obj(audio_obj)

    # Try top-level audio
    audio_obj = data.get("audio")
    if audio_obj:
        return _decode_audio_obj(audio_obj)

    # Try data field
    data_field = data.get("data")
    if isinstance(data_field, dict):
        return _decode_audio_obj(data_field)
    if isinstance(data_field, list) and data_field:
        first = data_field[0]
        if isinstance(first, dict):
            b64 = first.get("b64_json") or first.get("data") or ""
            if b64:
                return base64.b64decode(b64)

    return None


def _decode_audio_obj(audio_obj: dict | str) -> bytes | None:
    """Decode audio object to bytes."""
    if isinstance(audio_obj, str):
        # Might be base64 string
        try:
            return base64.b64decode(audio_obj)
        except Exception:
            return None

    if isinstance(audio_obj, dict):
        b64 = audio_obj.get("data") or audio_obj.get("b64_json") or audio_obj.get("base64") or ""
        if b64:
            try:
                return base64.b64decode(b64)
            except Exception:
                return None

    return None
