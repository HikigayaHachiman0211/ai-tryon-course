from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from .locale import DEFAULT_LOCALE, normalize_locale

_RESOURCE_DIR = Path(__file__).resolve().parent / "resources"


@lru_cache(maxsize=3)
def _load(locale: str) -> dict[str, Any]:
    path = _RESOURCE_DIR / f"{locale}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def translate(key: str, locale: str | None = None, **params: Any) -> str:
    target = normalize_locale(locale) or DEFAULT_LOCALE
    value: Any = _load(target)
    for part in key.split("."):
        if not isinstance(value, dict):
            value = None
            break
        value = value.get(part)
    if not isinstance(value, str):
        value = _load(DEFAULT_LOCALE)
        for part in key.split("."):
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(part)
    if not isinstance(value, str):
        return key
    for name, replacement in params.items():
        value = value.replace("{{" + name + "}}", str(replacement))
    return value


def error_message(code: str, locale: str | None = None, **params: Any) -> str:
    return translate(f"errors.{code}", locale, **params) or translate("errors.UNKNOWN_ERROR", locale)
