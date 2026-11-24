import json
from pathlib import Path

from app.i18n.locale import (
    DEFAULT_LOCALE,
    normalize_locale,
    resolve_locale,
    resolve_locale_from_accept_language,
)


def _contract() -> dict:
    current = Path(__file__).resolve()
    for parent in current.parents:
        path = parent / "scripts" / "i18n" / "locale_contract.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise AssertionError("shared locale contract fixture not found")


def test_normalize_locale_accepts_only_supported_aliases() -> None:
    assert normalize_locale("zh") == "zh-CN"
    assert normalize_locale("zh-Hans") == "zh-CN"
    assert normalize_locale("zh_CN") == "zh-CN"
    assert normalize_locale("en-US") == "en"
    assert normalize_locale("ja-JP") == "ja"
    assert normalize_locale("fr-FR") is None
    for item in _contract()["normalization"]:
        assert normalize_locale(item["input"]) == item["expected"]


def test_accept_language_respects_quality_and_ignores_wildcard() -> None:
    assert resolve_locale_from_accept_language("fr;q=0.9, ja-JP;q=0.8, en;q=0.7") == "ja"
    assert resolve_locale_from_accept_language("en;q=0.4, zh-CN;q=0.9") == "zh-CN"
    assert resolve_locale_from_accept_language("fr, *;q=0.5") is None
    for item in _contract()["accept_language"]:
        assert resolve_locale_from_accept_language(item["input"]) == item["expected"]


def test_explicit_locale_has_priority_over_header_and_invalid_falls_back() -> None:
    assert resolve_locale("ja", "en-US") == "ja"
    assert resolve_locale("fr", "en-US") == "en"
    assert resolve_locale(None, "fr-FR") == DEFAULT_LOCALE
    for item in _contract()["precedence"]:
        assert resolve_locale(item["explicit"], item["accept_language"]) == item["expected"]
