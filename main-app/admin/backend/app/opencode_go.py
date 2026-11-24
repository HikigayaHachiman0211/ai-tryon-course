"""OpenCode Go multi-protocol model registry and request/response adapter."""
from __future__ import annotations

import base64
from typing import Any
from urllib.parse import urlparse

import httpx

DEFAULT_OPENCODE_GO_BASE_URL = "https://opencode.ai/inference/go"
DEFAULT_OPENCODE_GO_MODEL = "deepseek-v4.1-flash"
OPENCODE_GO_USER_AGENT = "ai-tryon-client/1.0"

# Native API protocol and image-input capability per OpenCode Go model
# Verified against https://opencode.ai/inference/go/v1/models + user dashboard list.
OPENCODE_GO_MODEL_SPECS: dict[str, dict[str, Any]] = {
    "deepseek-v4.1-flash": {"protocol": "chat-completions", "vision": True},
    "gemini-4-argon": {"protocol": "generate-content", "vision": True},
    "claude-haiku-5-5": {"protocol": "messages", "vision": True},
    "gpt-6-luna": {"protocol": "responses", "vision": True},
    "gpt-5.6-luna": {"protocol": "responses", "vision": True},
    "grok-4.7": {"protocol": "responses", "vision": True},
    "qwen3.8-max": {"protocol": "messages", "vision": True},
    "qwen3.8-flash": {"protocol": "messages", "vision": True},
    "qwen3.7-plus": {"protocol": "messages", "vision": True},
    "glm-5.3-flash": {"protocol": "chat-completions", "vision": True},
    "mimo-v2.6-flash": {"protocol": "chat-completions", "vision": True},
    "mimo-v2.6-pro": {"protocol": "chat-completions", "vision": True},
    "kimi-k3.1-pro": {"protocol": "chat-completions", "vision": True},
    "kimi-k3": {"protocol": "chat-completions", "vision": True},
    "kimi-k2.7-code": {"protocol": "chat-completions", "vision": True},
    "minimax-m3": {"protocol": "messages", "vision": True},
    "minimax-m3.1-flash": {"protocol": "chat-completions", "vision": True},
    "step-5-preview": {"protocol": "chat-completions", "vision": True},
    "hy4": {"protocol": "chat-completions", "vision": True},
    "longcat-2.5-free": {"protocol": "chat-completions", "vision": True},
    "muse-spark-1.2-contributor": {"protocol": "responses", "vision": True},
    "muse-spark-1.3-contributor": {"protocol": "responses", "vision": True},
    "deepseek-v4-pro": {"protocol": "chat-completions", "vision": False},
    "glm-5.3": {"protocol": "chat-completions", "vision": False},
    "glm-5.2": {"protocol": "chat-completions", "vision": False},
    "mimo-v2.5": {"protocol": "chat-completions", "vision": False},
    "mimo-v2.5-pro": {"protocol": "chat-completions", "vision": False},
    "longcat-2.0": {"protocol": "chat-completions", "vision": False},
    "hy4-preview": {"protocol": "chat-completions", "vision": False},
    "hy3": {"protocol": "chat-completions", "vision": False},
    "beam-free": {"protocol": "chat-completions", "vision": False},
    "iceman-contributor-free": {"protocol": "chat-completions", "vision": False},
}

OPENCODE_GO_MODELS: tuple[str, ...] = tuple(OPENCODE_GO_MODEL_SPECS.keys())
OPENCODE_GO_VISION_MODELS: frozenset[str] = frozenset(
    k for k, spec in OPENCODE_GO_MODEL_SPECS.items() if spec["vision"]
)
OPENCODE_GO_TEXT_ONLY_MODELS: frozenset[str] = frozenset(
    k for k, spec in OPENCODE_GO_MODEL_SPECS.items() if not spec["vision"]
)

_ROOT_STRIP_SUFFIXES: tuple[str, ...] = (
    "/openai/v1/chat/completions",
    "/openai/v1/responses",
    "/anthropic/v1/messages",
    "/google/v1beta",
    "/anthropic/v1",
    "/openai/v1",
    "/v1beta",
    "/v1",
)


def normalize_opencode_go_root(base_url: str | None) -> str:
    """Normalize any OpenCode Go endpoint variant down to the Go root prefix."""
    cleaned = (base_url or "").strip().rstrip("/")
    if not cleaned:
        return DEFAULT_OPENCODE_GO_BASE_URL
    lower = cleaned.lower()
    for suffix in _ROOT_STRIP_SUFFIXES:
        if lower.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].rstrip("/")
            break
    parsed = urlparse(cleaned)
    if parsed.netloc.lower() == "opencode.ai" and not parsed.path.strip("/"):
        return DEFAULT_OPENCODE_GO_BASE_URL
    return cleaned or DEFAULT_OPENCODE_GO_BASE_URL


def detect_opencode_go_protocol(model: str | None) -> str:
    """Return the native OpenCode Go protocol key for a given model ID."""
    key = (model or DEFAULT_OPENCODE_GO_MODEL).strip().lower()
    if key in OPENCODE_GO_MODEL_SPECS:
        return str(OPENCODE_GO_MODEL_SPECS[key]["protocol"])
    if key.startswith(("gpt-", "grok-", "muse-spark")):
        return "responses"
    if key.startswith(("claude-", "qwen")):
        return "messages"
    if key.startswith("gemini-"):
        return "generate-content"
    return "chat-completions"


def is_opencode_go_vision_capable(model: str | None) -> bool:
    """Return True unless the model is known to be text-only."""
    key = (model or DEFAULT_OPENCODE_GO_MODEL).strip().lower()
    if key in OPENCODE_GO_MODEL_SPECS:
        return bool(OPENCODE_GO_MODEL_SPECS[key]["vision"])
    return key not in OPENCODE_GO_TEXT_ONLY_MODELS


def resolve_opencode_go_endpoint(
    base_url: str | None,
    protocol: str,
    model: str,
) -> str:
    """Resolve the full HTTP endpoint URL for an OpenCode Go model protocol."""
    root = normalize_opencode_go_root(base_url)
    if protocol == "responses":
        return f"{root}/openai/v1/responses"
    if protocol == "messages":
        return f"{root}/anthropic/v1/messages"
    if protocol == "generate-content":
        return f"{root}/google/v1beta/models/{model}:generateContent"
    return f"{root}/openai/v1/chat/completions"


def resolve_opencode_go_models_url(base_url: str | None) -> str:
    """Return the OpenCode Go public/authenticated models listing URL."""
    root = normalize_opencode_go_root(base_url)
    return f"{root}/v1/models"


def build_opencode_go_headers(
    api_key: str,
    protocol: str,
    session_id: str | None = None,
) -> dict[str, str]:
    """Build protocol-appropriate headers including recommended User-Agent and session tracking."""
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": OPENCODE_GO_USER_AGENT,
    }
    if protocol == "messages":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    elif protocol == "generate-content":
        headers["x-goog-api-key"] = api_key
    if session_id and session_id.strip():
        headers["x-opencode-session"] = session_id.strip()
    return headers


def build_opencode_go_payload(
    *,
    model: str,
    protocol: str,
    messages: list[dict[str, str]],
    system_prompt: str | None = None,
    image_bytes: bytes | None = None,
    mime_type: str | None = None,
    temperature: float | None = 0.2,
    max_tokens: int = 1024,
    json_mode: bool = False,
) -> dict[str, Any]:
    """Convert unified chat turns (+ optional image) into native OpenCode Go payload."""
    encoded_image = base64.b64encode(image_bytes).decode("utf-8") if image_bytes else ""
    effective_mime = mime_type or "image/jpeg"
    data_url = f"data:{effective_mime};base64,{encoded_image}" if encoded_image else ""

    if protocol == "generate-content":
        contents: list[dict[str, Any]] = []
        last_user_idx = max(
            (i for i, m in enumerate(messages) if m.get("role") == "user"),
            default=len(messages) - 1,
        )
        for idx, msg in enumerate(messages):
            role = "model" if msg.get("role") == "assistant" else "user"
            parts: list[dict[str, Any]] = [{"text": msg.get("content", "")}]
            if encoded_image and idx == last_user_idx:
                parts.append({"inline_data": {"mime_type": effective_mime, "data": encoded_image}})
            contents.append({"role": role, "parts": parts})

        gen_cfg: dict[str, Any] = {"maxOutputTokens": max_tokens}
        if temperature is not None:
            gen_cfg["temperature"] = temperature
        if json_mode:
            gen_cfg["responseMimeType"] = "application/json"

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": gen_cfg,
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        return payload

    if protocol == "messages":
        anth_messages: list[dict[str, Any]] = []
        last_user_idx = max(
            (i for i, m in enumerate(messages) if m.get("role") == "user"),
            default=len(messages) - 1,
        )
        for idx, msg in enumerate(messages):
            role = "assistant" if msg.get("role") == "assistant" else "user"
            text_val = msg.get("content", "")
            if encoded_image and idx == last_user_idx:
                content: Any = [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": effective_mime,
                            "data": encoded_image,
                        },
                    },
                    {"type": "text", "text": text_val},
                ]
            else:
                content = text_val
            anth_messages.append({"role": role, "content": content})

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": anth_messages,
        }
        if system_prompt:
            payload["system"] = system_prompt
        if temperature is not None:
            payload["temperature"] = temperature
        return payload

    if protocol == "responses":
        input_items: list[dict[str, Any]] = []
        last_user_idx = max(
            (i for i, m in enumerate(messages) if m.get("role") == "user"),
            default=len(messages) - 1,
        )
        for idx, msg in enumerate(messages):
            role = "assistant" if msg.get("role") == "assistant" else "user"
            text_type = "output_text" if role == "assistant" else "input_text"
            parts = [{"type": text_type, "text": msg.get("content", "")}]
            if encoded_image and idx == last_user_idx:
                parts.insert(0, {"type": "input_image", "image_url": data_url})
            input_items.append({"role": role, "content": parts})

        payload = {
            "model": model,
            "input": input_items,
            "max_output_tokens": max_tokens,
        }
        if system_prompt:
            payload["instructions"] = system_prompt
        if temperature is not None:
            payload["temperature"] = temperature
        return payload

    # Default: OpenAI-compatible chat-completions
    chat_messages: list[dict[str, Any]] = []
    if system_prompt:
        chat_messages.append({"role": "system", "content": system_prompt})
    last_user_idx = max(
        (i for i, m in enumerate(messages) if m.get("role") == "user"),
        default=len(messages) - 1,
    )
    for idx, msg in enumerate(messages):
        role = msg.get("role", "user")
        text_val = msg.get("content", "")
        if encoded_image and idx == last_user_idx:
            content = [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": text_val},
            ]
        else:
            content = text_val
        chat_messages.append({"role": role, "content": content})

    payload = {
        "model": model,
        "messages": chat_messages,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    return payload


def extract_opencode_go_text(protocol: str, data: dict[str, Any]) -> str:
    """Extract primary text output across all four OpenCode Go response schemas."""
    if not isinstance(data, dict):
        return ""

    if protocol == "generate-content":
        texts: list[str] = []
        fallback_texts: list[str] = []
        for candidate in data.get("candidates", []):
            content = candidate.get("content") or {}
            for part in content.get("parts", []):
                if "text" in part and isinstance(part["text"], str):
                    fallback_texts.append(part["text"])
                    if not part.get("thought"):
                        texts.append(part["text"])
        return "\n".join(texts or fallback_texts).strip()

    if protocol == "messages":
        blocks = data.get("content") or []
        parts = [
            b.get("text", "")
            for b in blocks
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
        ]
        return "\n".join(parts).strip()

    if protocol == "responses":
        if isinstance(data.get("output_text"), str) and data["output_text"].strip():
            return data["output_text"].strip()
        parts = []
        for item in data.get("output") or []:
            if not isinstance(item, dict):
                continue
            for content_item in item.get("content") or []:
                if (
                    isinstance(content_item, dict)
                    and content_item.get("type") in ("output_text", "text")
                    and isinstance(content_item.get("text"), str)
                ):
                    parts.append(content_item["text"])
        return "\n".join(parts).strip()

    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        text_parts = [
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and isinstance(p.get("text"), str)
        ]
        content = "\n".join(text_parts)
    if isinstance(content, str) and content.strip():
        return content.strip()
    reasoning = message.get("reasoning_content")
    return reasoning.strip() if isinstance(reasoning, str) else ""


def _prepare_request(
    *,
    api_key: str,
    model: str | None,
    messages: list[dict[str, str]],
    base_url: str | None,
    system_prompt: str | None,
    image_bytes: bytes | None,
    mime_type: str | None,
    temperature: float | None,
    max_tokens: int,
    json_mode: bool,
    session_id: str | None,
) -> tuple[str, str, dict[str, str], dict[str, Any]]:
    resolved_model = (model or DEFAULT_OPENCODE_GO_MODEL).strip() or DEFAULT_OPENCODE_GO_MODEL
    protocol = detect_opencode_go_protocol(resolved_model)
    url = resolve_opencode_go_endpoint(base_url, protocol, resolved_model)
    headers = build_opencode_go_headers(api_key, protocol, session_id=session_id)
    payload = build_opencode_go_payload(
        model=resolved_model,
        protocol=protocol,
        messages=messages,
        system_prompt=system_prompt,
        image_bytes=image_bytes,
        mime_type=mime_type,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_mode,
    )
    return protocol, url, headers, payload


def call_opencode_go_sync(
    *,
    api_key: str,
    model: str | None,
    messages: list[dict[str, str]],
    base_url: str | None = None,
    system_prompt: str | None = None,
    image_bytes: bytes | None = None,
    mime_type: str | None = None,
    temperature: float | None = 0.2,
    max_tokens: int = 1500,
    json_mode: bool = False,
    timeout: float = 45.0,
    session_id: str | None = None,
) -> str:
    """Synchronous OpenCode Go request supporting all four native protocols."""
    protocol, url, headers, payload = _prepare_request(
        api_key=api_key,
        model=model,
        messages=messages,
        base_url=base_url,
        system_prompt=system_prompt,
        image_bytes=image_bytes,
        mime_type=mime_type,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_mode,
        session_id=session_id,
    )
    resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code == 400 and "response_format" in payload:
        retry_payload = dict(payload)
        retry_payload.pop("response_format", None)
        resp = httpx.post(url, headers=headers, json=retry_payload, timeout=timeout)
    resp.raise_for_status()
    return extract_opencode_go_text(protocol, resp.json())


async def call_opencode_go_async(
    *,
    api_key: str,
    model: str | None,
    messages: list[dict[str, str]],
    base_url: str | None = None,
    system_prompt: str | None = None,
    image_bytes: bytes | None = None,
    mime_type: str | None = None,
    temperature: float | None = 0.2,
    max_tokens: int = 1024,
    json_mode: bool = False,
    timeout: float = 30.0,
    session_id: str | None = None,
) -> httpx.Response:
    """Async OpenCode Go request returning the raw httpx.Response."""
    _protocol, url, headers, payload = _prepare_request(
        api_key=api_key,
        model=model,
        messages=messages,
        base_url=base_url,
        system_prompt=system_prompt,
        image_bytes=image_bytes,
        mime_type=mime_type,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_mode,
        session_id=session_id,
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code == 400 and "response_format" in payload:
            retry_payload = dict(payload)
            retry_payload.pop("response_format", None)
            resp = await client.post(url, headers=headers, json=retry_payload)
        return resp


def parse_opencode_go_models_response(data: dict[str, Any]) -> list[str]:
    """Extract sorted unique model IDs from /v1/models JSON payload."""
    items = data.get("data") or []
    discovered = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, dict):
            mid = str(item.get("id") or "").strip()
            if mid and mid not in seen:
                seen.add(mid)
                discovered.append(mid)
    known_rank = {mid: i for i, mid in enumerate(OPENCODE_GO_MODELS)}
    return sorted(discovered, key=lambda mid: (known_rank.get(mid, 10_000), mid))
