"""Shared LLM response parsing and validation helpers.

Used by both recommendation.py (profile inference) and
assistant/llm_clients.py (chat intent extraction) to avoid
duplicated, drifting implementations.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

# Fields that constitute a valid profile inference response.
_PROFILE_FIELDS: frozenset[str] = frozenset(
    {"recommended_size", "body_shape", "suggested_style", "reasoning"}
)

# Safe action types the assistant frontend understands.
_SAFE_ACTION_TYPES: frozenset[str] = frozenset({"none", "fill_recommend_form"})


def extract_json_object(text: str | None) -> dict[str, Any] | None:
    """Extract the first JSON object from *text*.

    Handles:
    - None / empty / whitespace-only input → None
    - Markdown code fences (```json ... ``` or ``` ... ```)
    - JSON embedded in surrounding prose
    - Truncated JSON → None (json.JSONDecodeError)
    - Non-object JSON (array, string, number) → None

    Returns a dict on success, None on any failure.
    """
    if not text:
        return None

    cleaned = text.strip()
    if not cleaned:
        return None

    # Strip leading code fence
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        result = json.loads(cleaned[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(result, dict):
        return None

    return result


def coerce_confidence(value: Any, *, default: float = 0.5) -> float:
    """Return a finite float in [0.0, 1.0].

    Rejects booleans, strings, None, NaN, and ±inf; all return *default*.
    Integers are accepted and clamped.
    """
    # bool is a subclass of int — must be rejected before the int check
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default

    f = float(value)

    # Reject NaN — cannot be clamped meaningfully
    if math.isnan(f):
        return default

    # Clamp ±inf and out-of-range values
    return max(0.0, min(1.0, f))


def coerce_text(value: Any, *, max_len: int = 2000) -> str | None:
    """Return a stripped string of at most *max_len* characters, or None.

    Unlike str(), this refuses to convert dicts/lists/ints — callers must
    not silently render Python reprs into user-facing text.
    """
    if not isinstance(value, str):
        return None

    stripped = value.strip()
    if not stripped:
        return None

    return stripped[:max_len]


def has_known_profile_field(parsed: dict[str, Any]) -> bool:
    """Return True if *parsed* contains at least one recognised profile key.

    Used to distinguish a genuine profile inference response (which must
    contain at least one of the four expected keys) from junk JSON that
    the LLM accidentally returned in a valid-but-useless envelope.
    """
    return bool(_PROFILE_FIELDS & parsed.keys())


def coerce_action_type(value: Any) -> str:
    """Return *value* if it is a known safe action type, else ``'none'``."""
    if isinstance(value, str) and value in _SAFE_ACTION_TYPES:
        return value
    return "none"
