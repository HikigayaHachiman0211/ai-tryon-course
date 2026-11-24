"""Canonical DeepSeek model IDs, retirement aliases, and vision capability checks."""
from __future__ import annotations

DEFAULT_DEEPSEEK_MODEL = "deepseek-flash"

DEEPSEEK_TEXT_MODELS: tuple[str, ...] = (
    "deepseek-flash",
    "deepseek-v4-pro",
)

RETIRED_DEEPSEEK_MODEL_ALIASES: dict[str, str] = {
    "deepseek-chat": DEFAULT_DEEPSEEK_MODEL,
    "deepseek-reasoner": DEFAULT_DEEPSEEK_MODEL,
    "deepseek-v4-flash": DEFAULT_DEEPSEEK_MODEL,
    "deepseek-v4-flash-vision-exp": DEFAULT_DEEPSEEK_MODEL,
    "deepseek-v4.1-flash": DEFAULT_DEEPSEEK_MODEL,
}

DEEPSEEK_NON_VISION_MODELS: frozenset[str] = frozenset({
    "deepseek-v4-pro",
})


def normalize_deepseek_model(model: str | None) -> str:
    """Map retired/legacy DeepSeek API model IDs to current canonical equivalents."""
    cleaned = (model or "").strip()
    if not cleaned:
        return DEFAULT_DEEPSEEK_MODEL
    lower = cleaned.lower()
    if lower in RETIRED_DEEPSEEK_MODEL_ALIASES:
        return RETIRED_DEEPSEEK_MODEL_ALIASES[lower]
    if "v4.1-flash" in lower or "4.1-flash" in lower:
        return DEFAULT_DEEPSEEK_MODEL
    return cleaned


def is_deepseek_vision_capable(model: str | None) -> bool:
    """Return True if the DeepSeek official API model supports multimodal image input."""
    normalized = normalize_deepseek_model(model).lower()
    return normalized not in DEEPSEEK_NON_VISION_MODELS
