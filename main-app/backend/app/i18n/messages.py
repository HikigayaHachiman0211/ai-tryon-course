from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .locale import DEFAULT_LOCALE, normalize_locale

RESOURCE_DIR = Path(__file__).with_name("resources")

_FALLBACK = {
    "errors": {
        "SYS-000": "An unexpected server error occurred.",
        "SYS-001": "The request data is invalid.",
        "SYS-002": "The request could not be accepted.",
        "REC-001": "The price range is invalid.",
        "REC-002": "The image analysis provider failed; rule-based inference was used.",
        "DBG-001": "Debug pages are disabled.",
        "LAB-001": "The selected product was not found.",
        "UNKNOWN": "Something went wrong. Please try again later.",
    },
    "troubleshooting": {"default": "Please try again later. If the problem continues, share the request ID."},
    "assistant": {
        "welcome": "Hi! I am your AI down-jacket stylist. Tell me what you would like to wear.",
        "fallback": "I could not complete that request. Please try again.",
        "greeting": "Hello! How can I help you choose a down jacket today?",
    },
}


@lru_cache(maxsize=3)
def load_messages(locale: str) -> dict[str, Any]:
    normalized = normalize_locale(locale) or DEFAULT_LOCALE
    path = RESOURCE_DIR / f"{normalized}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else _FALLBACK
    except (OSError, ValueError):
        return _FALLBACK


def _lookup(locale: str, namespace: str, key: str) -> str | None:
    value: Any = load_messages(locale).get(namespace, {})
    for part in key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value if isinstance(value, str) else None


def translate(locale: str, namespace: str, key: str, **params: object) -> str:
    normalized = normalize_locale(locale) or DEFAULT_LOCALE
    value = _lookup(normalized, namespace, key)
    if value is None and normalized != DEFAULT_LOCALE:
        value = _lookup(DEFAULT_LOCALE, namespace, key)
    if value is None:
        value = _lookup("en", namespace, "UNKNOWN") or _FALLBACK["errors"]["UNKNOWN"]
    try:
        return value.format(**params)
    except (KeyError, ValueError):
        return value


def error_message(code: str, locale: str, **params: object) -> str:
    return translate(locale, "errors", code, **params)


def troubleshooting_message(code: str, locale: str, **params: object) -> str:
    return translate(locale, "troubleshooting", code, **params)


def assistant_message(key: str, locale: str, **params: object) -> str:
    return translate(locale, "assistant", key, **params)


def history_message(key: str, locale: str, **params: object) -> str:
    return translate(locale, "history", key, **params)
