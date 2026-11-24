from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

SUPPORTED_LOCALES = ("zh-CN", "en", "ja")
DEFAULT_LOCALE = "zh-CN"


def normalize_locale(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip().lower().replace("_", "-")
    if raw in {"zh", "zh-cn", "zh-hans"} or raw.startswith("zh-hans-"):
        return "zh-CN"
    if raw == "en" or raw.startswith("en-"):
        return "en"
    if raw == "ja" or raw.startswith("ja-"):
        return "ja"
    return None


@dataclass(frozen=True)
class LocalePreference:
    locale: str
    quality: float
    order: int


def parse_accept_language(value: str | None) -> list[LocalePreference]:
    if not value:
        return []
    preferences: list[LocalePreference] = []
    for order, part in enumerate(value.split(",")):
        pieces = [piece.strip() for piece in part.split(";")]
        locale = normalize_locale(pieces[0])
        quality = 1.0
        for piece in pieces[1:]:
            if piece.startswith("q="):
                try:
                    quality = float(piece[2:])
                except ValueError:
                    quality = 0.0
        if locale and quality > 0:
            preferences.append(LocalePreference(locale, max(0.0, min(1.0, quality)), order))
    return sorted(preferences, key=lambda item: (-item.quality, item.order))


def resolve_locale(*, explicit: str | None = None, accept_language: str | None = None, query: str | None = None) -> str:
    return normalize_locale(explicit) or normalize_locale(query) or (parse_accept_language(accept_language)[0].locale if parse_accept_language(accept_language) else DEFAULT_LOCALE)


def request_locale(request, *, explicit: str | None = None) -> str:
    return resolve_locale(
        explicit=explicit,
        query=request.query_params.get("lang") or request.query_params.get("locale"),
        accept_language=request.headers.get("accept-language"),
    )
