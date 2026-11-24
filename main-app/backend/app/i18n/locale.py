from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_LOCALES = ("zh-CN", "en", "ja")
DEFAULT_LOCALE = "zh-CN"


def normalize_locale(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().replace("_", "-").lower()
    if normalized in {"zh", "zh-cn", "zh-hans"}:
        return "zh-CN"
    if normalized == "en" or normalized.startswith("en-"):
        return "en"
    if normalized == "ja" or normalized.startswith("ja-"):
        return "ja"
    return None


@dataclass(frozen=True)
class _LanguagePreference:
    range: str
    quality: float
    order: int


def resolve_locale_from_accept_language(value: str | None) -> str | None:
    if not value:
        return None

    preferences: list[_LanguagePreference] = []
    for order, item in enumerate(value.split(",")):
        parts = [part.strip() for part in item.split(";")]
        language_range = parts[0]
        quality = 1.0
        for parameter in parts[1:]:
            name, separator, raw_quality = parameter.partition("=")
            if name.lower() != "q" or not separator:
                continue
            try:
                quality = float(raw_quality)
            except ValueError:
                quality = 0.0
        if language_range == "*" or quality <= 0:
            continue
        preferences.append(
            _LanguagePreference(
                range=language_range,
                quality=max(0.0, min(1.0, quality)),
                order=order,
            )
        )

    preferences.sort(key=lambda item: (-item.quality, item.order))
    for preference in preferences:
        locale = normalize_locale(preference.range)
        if locale:
            return locale
    return None


def resolve_locale(explicit: str | None, accept_language: str | None) -> str:
    return (
        normalize_locale(explicit)
        or resolve_locale_from_accept_language(accept_language)
        or DEFAULT_LOCALE
    )
