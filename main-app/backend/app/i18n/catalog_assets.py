from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CATALOG_TRANSLATION_DIR = Path(__file__).with_name("catalog-translations")


@lru_cache(maxsize=3)
def load_catalog_translations(locale: str) -> dict[str, dict[str, Any]]:
    if locale == "zh-CN":
        return {}
    path = CATALOG_TRANSLATION_DIR / f"{locale}.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    items = payload.get("items", payload) if isinstance(payload, dict) else {}
    return items if isinstance(items, dict) else {}


def get_catalog_translation(product_key: str, locale: str) -> dict[str, Any] | None:
    value = load_catalog_translations(locale).get(product_key)
    return value if isinstance(value, dict) else None
