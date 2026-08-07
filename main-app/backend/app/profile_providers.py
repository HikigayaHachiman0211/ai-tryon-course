from __future__ import annotations

import base64
import os
import re
from typing import Any

import httpx

from app.ai_runtime_config import build_auth_headers
from app.llm_parsing import extract_json_object as _extract_json_object
from app.prompt_loader import load_active_prompt


DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")

DEFAULT_DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_MODELS = [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "deepseek-chat",
    "deepseek-reasoner",
]
DEEPSEEK_API_BASE = "https://api.deepseek.com"

DEFAULT_MIMO_API_BASE = "https://api.xiaomimimo.com/v1"
DEFAULT_MIMO_MODEL = os.getenv("MIMO_MODEL", "mimo-v2.5")
MIMO_API_BASE = os.getenv("MIMO_API_BASE", DEFAULT_MIMO_API_BASE).rstrip("/")
MIMO_API_KEY = os.getenv("MIMO_API_KEY", "")
MIMO_AUTH_HEADER = os.getenv("MIMO_AUTH_HEADER", "api-key").strip().lower()
MIMO_MODELS = ["mimo-v2.5", "mimo-v2.5-pro", "mimo-v2-omni"]


def _sanitize_error_for_log(exc: Exception) -> str:
    """Sanitize exception message to strip any sensitive data (API keys, base64, etc).

    Ordering matters: longer/more-specific patterns run first so shorter
    patterns don't partially consume the string and leave secrets exposed.
    """
    text = str(exc)
    # 1. Authorization header with Bearer token — must match the full value
    text = re.sub(
        r"Authorization\s*[:=]\s*Bearer\s+\S+",
        "Authorization: Bearer [REDACTED]",
        text,
        flags=re.IGNORECASE,
    )
    # 2. api-key / api_key header with value
    text = re.sub(
        r"api[_-]?key\s*[:=]\s*\S+",
        "api-key=[REDACTED]",
        text,
        flags=re.IGNORECASE,
    )
    # 3. Query-string ?key=...
    text = re.sub(r"\?key=\S+", "?key=[REDACTED]", text, flags=re.IGNORECASE)
    # 4. Standalone Bearer token (if not already caught by #1)
    text = re.sub(r"Bearer\s+\S+", "Bearer [REDACTED]", text, flags=re.IGNORECASE)
    # 5. Inline base64 data URLs
    text = re.sub(
        r"data:[a-z]+/[a-z]+;base64,[A-Za-z0-9+/=]{40,}",
        "data:[REDACTED]",
        text,
        flags=re.IGNORECASE,
    )
    # Truncate very long messages that might contain request bodies
    if len(text) > 300:
        text = text[:300] + "..."
    return text


def _run_sanitization_self_test() -> None:
    """Minimal assertions to guarantee no token leakage survives sanitization."""
    cases = [
        (
            "Request failed: Authorization: Bearer demo-secret-token-12345",
            "demo-secret-token-12345",
        ),
        (
            "HTTP 401: api-key: abcdefghijklmnop",
            "abcdefghijklmnop",
        ),
        (
            "Error from https://api.example.com/v1?key=AIzaSyD-SECRET",
            "AIzaSyD-SECRET",
        ),
        (
            "Inline image data:image/jpeg;base64," + "A" * 80,
            "AAAA",
        ),
        (
            "Header set: Authorization=Bearer ghp_xxxxxxxxxxxx",
            "ghp_xxxxxxxxxxxx",
        ),
    ]
    for raw, secret in cases:
        cleaned = _sanitize_error_for_log(Exception(raw))
        assert secret not in cleaned, (
            f"Sanitization leak: '{secret}' found in '{cleaned}'"
        )


# Run self-test once at import time (zero-cost after module is loaded)
_run_sanitization_self_test()


def normalize_vision_provider(value: str | None) -> str | None:
    """Normalize vision provider request value. Returns None if not specified."""
    if not value:
        return None
    provider = value.strip().lower()
    return provider if provider in {"mimo", "gemini", "auto"} else None


def strip_json_block(text: str) -> dict[str, Any] | None:
    return _extract_json_object(text)


def call_gemini_profile(
    *,
    image_bytes: bytes,
    mime_type: str | None,
    api_key: str,
    gender: str | None,
    mbti: str | None,
    color_preference: str,
    size: str | None,
    style_preference: str | None,
    model: str,
) -> dict[str, Any] | None:
    prompt = f"""
你是服装搭配分析助手。请结合全身照、用户颜色偏好、MBTI 和已知条件，输出一个 JSON 对象，不要输出 markdown。

已知条件：
- 颜色偏好: {color_preference}
- 用户性别: {gender or '未提供'}
- MBTI: {mbti or '未提供'}
- 用户已提供尺码: {size or '未提供'}
- 用户已提供款式偏好: {style_preference or '未提供'}

返回字段：
{{
  "recommended_size": "XS/S/M/L/XL/2XL/3XL/4XL/5XL/unknown 之一",
  "body_shape": "偏瘦/标准/微胖/高壮/H型/梨形/倒三角/沙漏型/O型/未知 之一",
  "suggested_style": "常规短外套/短款/轻薄款/绗缝款（排骨款）/面包服/中长款大衣/长款/巴恩风/工装风 之一",
  "reasoning": "50字内中文解释"
}}

要求：
- 如果用户已提供尺码或款式偏好，也要结合图像做校验，但仍返回完整 JSON。
- 如果无法可靠判断，请写 unknown 或 未知。
""".strip()

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type or "image/png",
                            "data": base64.b64encode(image_bytes).decode("utf-8"),
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    response = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": api_key},
        json=payload,
        timeout=30.0,
    )
    response.raise_for_status()
    response_json = response.json()

    texts: list[str] = []
    for candidate in response_json.get("candidates", []):
        content = candidate.get("content") or {}
        for part in content.get("parts", []):
            if "text" in part:
                texts.append(part["text"])

    if not texts:
        return None

    return strip_json_block("\n".join(texts))


def call_gemini_text_profile(
    *,
    api_key: str,
    gender: str | None,
    mbti: str | None,
    color_preference: str,
    size: str | None,
    style_preference: str | None,
    model: str,
) -> dict[str, Any] | None:
    """Gemini text-only profile inference (no image). Uses generateContent without inline_data."""
    prompt = f"""你是服装搭配分析助手。请根据用户提供的信息，推断体型特征和推荐方案，输出一个 JSON 对象。

已知条件：
- 颜色偏好: {color_preference}
- 用户性别: {gender or '未提供'}
- MBTI: {mbti or '未提供'}
- 用户已提供尺码: {size or '未提供'}
- 用户已提供款式偏好: {style_preference or '未提供'}

返回字段（JSON 格式）：
{{
  "recommended_size": "XS/S/M/L/XL/2XL/3XL/4XL/5XL/unknown 之一",
  "body_shape": "偏瘦/标准/微胖/高壮/H型/梨形/倒三角/沙漏型/O型/未知 之一",
  "suggested_style": "常规短外套/短款/轻薄款/绗缝款（排骨款）/面包服/中长款大衣/长款/巴恩风/工装风 之一",
  "reasoning": "50字内中文解释"
}}

要求：
- 综合所有已知条件进行推断。
- 如果信息不足无法可靠判断，请写 unknown 或 未知。
""".strip()

    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    response = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": api_key},
        json=payload,
        timeout=30.0,
    )
    response.raise_for_status()
    response_json = response.json()

    texts: list[str] = []
    for candidate in response_json.get("candidates", []):
        content = candidate.get("content") or {}
        for part in content.get("parts", []):
            if "text" in part:
                texts.append(part["text"])

    if not texts:
        return None

    return strip_json_block("\n".join(texts))


def call_deepseek_profile(
    *,
    api_key: str,
    gender: str | None,
    mbti: str | None,
    color_preference: str,
    size: str | None,
    style_preference: str | None,
    model: str,
    base_url: str | None = None,
) -> dict[str, Any] | None:
    prompt = f"""你是服装搭配分析助手。请根据用户提供的信息，推断体型特征和推荐方案，输出一个 JSON 对象。

已知条件：
- 颜色偏好: {color_preference}
- 用户性别: {gender or '未提供'}
- MBTI: {mbti or '未提供'}
- 用户已提供尺码: {size or '未提供'}
- 用户已提供款式偏好: {style_preference or '未提供'}

返回字段（JSON 格式）：
{{
  "recommended_size": "XS/S/M/L/XL/2XL/3XL/4XL/5XL/unknown 之一",
  "body_shape": "偏瘦/标准/微胖/高壮/H型/梨形/倒三角/沙漏型/O型/未知 之一",
  "suggested_style": "常规短外套/短款/轻薄款/绗缝款（排骨款）/面包服/中长款大衣/长款/巴恩风/工装风 之一",
  "reasoning": "50字内中文解释"
}}

要求：
- 综合所有已知条件进行推断。
- 如果信息不足无法可靠判断，请写 unknown 或 未知。
""".strip()

    messages = [
        {"role": "system", "content": "你是一个专业的冬季羽绒服搭配分析助手，根据用户信息输出 JSON 格式的推荐结果。"},
        {"role": "user", "content": prompt},
    ]

    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": 512,
        "stream": False,
    }

    api_base = (base_url or DEEPSEEK_API_BASE).rstrip("/")
    response = httpx.post(
        f"{api_base}/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json=payload,
        timeout=30.0,
    )
    response.raise_for_status()
    response_json = response.json()

    choices = response_json.get("choices", [])
    if not choices:
        return None

    content = choices[0].get("message", {}).get("content", "")
    if not content:
        return None

    return strip_json_block(content)


def call_mimo_profile(
    *,
    api_key: str,
    gender: str | None,
    mbti: str | None,
    color_preference: str,
    size: str | None,
    style_preference: str | None,
    model: str | None = None,
    image_bytes: bytes | None = None,
    mime_type: str | None = None,
    prompt_override: str | None = None,
    base_url: str | None = None,
    auth_type: str | None = None,
    auth_header_name: str | None = None,
) -> dict[str, Any] | None:
    api_base = (base_url or MIMO_API_BASE or DEFAULT_MIMO_API_BASE).rstrip("/")
    if not api_base:
        return None
    effective_key = api_key or MIMO_API_KEY
    if not effective_key:
        return None

    # Normalize model: default mimo-v2.5, allow mimo-v2-omni
    normalized_model = (model or DEFAULT_MIMO_MODEL or "mimo-v2.5").strip()
    if normalized_model not in MIMO_MODELS:
        normalized_model = "mimo-v2.5"

    # Use prompt_override if provided, otherwise load from DB or use defaults
    system_msg = "你是专业的冬季羽绒服搭配分析助手。请根据用户信息和照片输出严格 JSON，不要输出多余解释。"

    _prompt_vars = {
        "color_preference": color_preference,
        "gender": gender or "未提供",
        "mbti": mbti or "未提供",
        "size": size or "未提供",
        "style_preference": style_preference or "未提供",
    }

    _DEFAULT_TEXT_PROMPT = (
        "请根据以下用户信息推断体型特征和推荐方案，输出一个 JSON 对象。\n\n"
        "已知条件：\n"
        "- 颜色偏好: {color_preference}\n"
        "- 用户性别: {gender}\n"
        "- MBTI: {mbti}\n"
        "- 用户已提供尺码: {size}\n"
        "- 用户已提供款式偏好: {style_preference}\n\n"
        "返回字段（JSON 格式）：\n"
        '{\n'
        '  "recommended_size": "XS/S/M/L/XL/2XL/3XL/4XL/5XL/unknown 之一",\n'
        '  "body_shape": "偏瘦/标准/微胖/高壮/H型/梨形/倒三角/沙漏型/O型/未知 之一",\n'
        '  "suggested_style": "常规短外套/短款/轻薄款/绗缝款（排骨款）/面包服/中长款大衣/长款/巴恩风/工装风 之一",\n'
        '  "reasoning": "50字内中文解释"\n'
        '}\n\n'
        "要求：\n"
        "- 综合所有已知条件进行推断。\n"
        "- 如果信息不足无法可靠判断，请写 unknown 或 未知。"
    )

    _DEFAULT_MULTIMODAL_PROMPT = (
        "请根据照片和以下用户偏好，分析身型特征并推荐羽绒服方案，输出严格 JSON。\n\n"
        "已知条件：\n"
        "- 颜色偏好: {color_preference}\n"
        "- 用户性别: {gender}\n"
        "- MBTI: {mbti}\n"
        "- 用户已提供尺码: {size}\n"
        "- 用户已提供款式偏好: {style_preference}\n\n"
        "返回字段（JSON 格式）：\n"
        '{\n'
        '  "recommended_size": "XS/S/M/L/XL/2XL/3XL/4XL/5XL/unknown 之一",\n'
        '  "body_shape": "偏瘦/标准/微胖/高壮/H型/梨形/倒三角/沙漏型/O型/未知 之一",\n'
        '  "suggested_style": "常规短外套/短款/轻薄款/绗缝款（排骨款）/面包服/中长款大衣/长款/巴恩风/工装风 之一",\n'
        '  "reasoning": "50字内中文解释"\n'
        '}\n\n'
        "要求：\n"
        "- 结合照片中的人物身型、穿着风格与已知条件综合分析。\n"
        "- 如果照片或信息不足无法可靠判断，请写 unknown 或 未知。"
    )

    if prompt_override:
        text_prompt = prompt_override
        multimodal_prompt = prompt_override
    else:
        # Try loading from DB prompt management, fall back to defaults
        text_prompt = load_active_prompt("mimo_image_profile_analysis", _DEFAULT_TEXT_PROMPT, _prompt_vars)
        multimodal_prompt = load_active_prompt("mimo_image_profile_analysis", _DEFAULT_MULTIMODAL_PROMPT, _prompt_vars)

    if image_bytes:
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        effective_mime = mime_type or "image/jpeg"
        data_url = f"data:{effective_mime};base64,{encoded}"
        user_content = [
            {"type": "image_url", "image_url": {"url": data_url}},
            {"type": "text", "text": multimodal_prompt},
        ]
    else:
        user_content = text_prompt

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_content},
    ]

    payload = {
        "model": normalized_model,
        "messages": messages,
        "temperature": 0.2,
        # MiMo v2.5 may spend several hundred tokens in reasoning_content before
        # emitting the final JSON in message.content. 512 tokens often truncates
        # before content is produced, which looks like an empty model response.
        "max_completion_tokens": 4096,
        "stream": False,
    }

    headers = build_auth_headers({
        "api_key": effective_key,
        "auth_type": auth_type or "api_key_header",
        "auth_header_name": auth_header_name or "",
    })

    # Multimodal (image) analysis on MiMo's full-modal model takes noticeably
    # longer than text-only inference (image perception + reasoning_content).
    # A 30s read timeout caused vision calls to time out and silently fall back
    # to Gemini, so allow more headroom when an image is sent.
    request_timeout = 90.0 if image_bytes else 45.0
    response = httpx.post(
        f"{api_base}/chat/completions",
        headers=headers,
        json=payload,
        timeout=request_timeout,
    )
    response.raise_for_status()
    response_json = response.json()

    choices = response_json.get("choices", [])
    if not choices:
        return None

    # Read content, ignore reasoning_content
    message = choices[0].get("message", {})
    content = message.get("content") or message.get("reasoning_content") or ""
    if not content:
        return None

    return strip_json_block(content)
