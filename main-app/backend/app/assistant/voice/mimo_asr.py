"""MiMo ASR client — calls mimo-v2.5-asr for speech-to-text."""
from __future__ import annotations

import logging
import re
import time

import httpx

from app.assistant.voice.audio_utils import encode_audio_data_url

logger = logging.getLogger(__name__)


def _sanitize_for_log(text: str) -> str:
    """Strip API keys, base64 audio from log messages."""
    text = re.sub(r"api[_-]?key\s*[:=]\s*\S+", "api-key=[REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"data:[a-z]+/[a-z]+;base64,[A-Za-z0-9+/=]{40,}", "data:[REDACTED]", text, flags=re.IGNORECASE)
    if len(text) > 300:
        text = text[:300] + "..."
    return text


async def call_mimo_asr(
    *,
    api_key: str,
    audio_bytes: bytes,
    mime_type: str,
    model: str = "mimo-v2.5-asr",
    base_url: str = "https://api.xiaomimimo.com/v1",
    language: str = "zh",
) -> tuple[str | None, dict]:
    """Call MiMo ASR API. Returns (recognized_text, metadata).

    Returns (None, metadata) on failure — never raises.
    Metadata includes latency_ms, error info.
    """
    meta: dict = {"model": model, "provider": "mimo"}
    start = time.time()

    if not api_key:
        meta["error"] = {"code": "ASR_CONFIG_MISSING", "message": "语音识别暂不可用，请改用文字输入。"}
        return None, meta

    data_url = encode_audio_data_url(audio_bytes, mime_type)

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
    }
    # Transcription-only system instruction — prevents the model from answering
    system_msg = {
        "role": "system",
        "content": (
            "你是一个纯语音转写引擎。只输出用户语音的文字转写结果，"
            "不要回答问题、不要添加解释、不要输出任何非转写内容。"
            "如果音频中没有可识别的语音，输出空字符串。"
        ),
    }

    payload = {
        "model": model,
        "messages": [
            system_msg,
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": data_url},
                    }
                ],
            }
        ],
        "asr_options": {"language": language},
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            latency_ms = int((time.time() - start) * 1000)
            meta["latency_ms"] = latency_ms

            # Redacted log: model, status, response keys
            resp_keys = list(resp.json().keys()) if resp.status_code == 200 else []
            logger.info(
                "MiMo ASR response: model=%s, status=%d, keys=%s, latency=%dms",
                model, resp.status_code, resp_keys, latency_ms,
            )

            if resp.status_code != 200:
                logger.warning("MiMo ASR HTTP %d: %s", resp.status_code, _sanitize_for_log(resp.text[:200]))
                meta["error"] = {"code": "ASR_API_ERROR", "message": f"ASR 服务返回错误 ({resp.status_code})。"}
                return None, meta

            data = resp.json()
            # Parse response: choices[0].message.content
            choices = data.get("choices", [])
            if not choices:
                logger.warning("MiMo ASR: no choices in response, keys=%s", list(data.keys()))
                meta["error"] = {"code": "ASR_EMPTY_RESPONSE", "message": "ASR 未返回识别结果。"}
                return None, meta

            content = choices[0].get("message", {}).get("content", "")

            # Log content type for debugging (not the content itself)
            logger.info("MiMo ASR content type: %s", type(content).__name__)

            # Content might be JSON string or plain text
            text = _extract_text_from_content(content)
            if not text:
                meta["error"] = {"code": "ASR_EMPTY_TEXT", "message": "ASR 识别结果为空。"}
                return None, meta

            meta["duration_ms"] = latency_ms
            return text, meta

    except httpx.TimeoutException:
        latency_ms = int((time.time() - start) * 1000)
        meta["latency_ms"] = latency_ms
        meta["error"] = {"code": "ASR_TIMEOUT", "message": "语音识别超时，请稍后重试。"}
        logger.warning("MiMo ASR timeout after %dms", latency_ms)
        return None, meta
    except Exception as exc:
        latency_ms = int((time.time() - start) * 1000)
        meta["latency_ms"] = latency_ms
        meta["error"] = {"code": "ASR_NETWORK_ERROR", "message": "网络请求失败，请稍后重试。"}
        logger.warning("MiMo ASR error: %s", _sanitize_for_log(str(exc)))
        return None, meta


def _extract_text_from_content(content: str | list | dict) -> str:
    """Extract text from ASR response content — handles JSON, string, and list formats."""
    if isinstance(content, str):
        # Try to parse as JSON first
        import json
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed.get("text", "") or parsed.get("transcript", "") or ""
            if isinstance(parsed, str):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        return content.strip()

    if isinstance(content, dict):
        return content.get("text", "") or content.get("transcript", "") or ""

    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                t = item.get("text", "") or ""
                if t:
                    texts.append(t)
            elif isinstance(item, str):
                texts.append(item)
        return " ".join(texts).strip()

    return ""
