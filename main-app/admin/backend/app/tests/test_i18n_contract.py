from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, text

from app.i18n.prompt_migration import has_legacy_name_unique, rebuild_sqlite_prompt_configs
from app.i18n.locale import DEFAULT_LOCALE, SUPPORTED_LOCALES, normalize_locale, resolve_locale
from app.i18n.messages import error_message


def _contract() -> dict:
    current = Path(__file__).resolve()
    for parent in current.parents:
        path = parent / "scripts" / "i18n" / "locale_contract.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise AssertionError("shared locale contract fixture not found")


def test_admin_locale_normalization_and_quality_order():
    assert SUPPORTED_LOCALES == ("zh-CN", "en", "ja")
    assert normalize_locale("zh-Hans-CN") == "zh-CN"
    assert normalize_locale("en-US") == "en"
    assert normalize_locale("ja-JP") == "ja"
    assert resolve_locale(explicit="ja", accept_language="en;q=1,ja;q=0.5") == "ja"
    assert resolve_locale(explicit="fr", accept_language="ja;q=0.9,en;q=0.8") == "ja"
    assert resolve_locale(explicit=None, accept_language="fr, de;q=0.5") == DEFAULT_LOCALE
    contract = _contract()
    for item in contract["normalization"]:
        assert normalize_locale(item["input"]) == item["expected"]
    for item in contract["accept_language"]:
        expected = item["expected"] or DEFAULT_LOCALE
        assert resolve_locale(accept_language=item["input"]) == expected
    for item in contract["precedence"]:
        expected = item["expected"] or DEFAULT_LOCALE
        assert resolve_locale(explicit=item["explicit"], accept_language=item["accept_language"]) == expected


def test_admin_error_code_is_stable_and_message_is_localized():
    assert error_message("AUTH_INVALID_CREDENTIALS", "zh-CN") != error_message("AUTH_INVALID_CREDENTIALS", "en")
    assert error_message("AUTH_INVALID_CREDENTIALS", "ja")
    assert error_message("UNKNOWN_ERROR", "en")


def test_sqlite_prompt_locale_migration_removes_legacy_name_unique_constraint():
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE prompt_configs ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name VARCHAR(100) NOT NULL UNIQUE, "
            "locale VARCHAR(10) NOT NULL DEFAULT 'zh-CN', "
            "display_name VARCHAR(200) NOT NULL, description VARCHAR(500), "
            "category VARCHAR(50), prompt_type VARCHAR(50), content TEXT NOT NULL, "
            "default_content TEXT, variables JSON, model_name VARCHAR(100) NOT NULL, "
            "temperature FLOAT DEFAULT 0.2, is_active BOOLEAN DEFAULT 1, "
            "version INTEGER DEFAULT 1, updated_at DATETIME, updated_by VARCHAR(100))"
        )
        connection.execute(text(
            "INSERT INTO prompt_configs (name, display_name, content, model_name) "
            "VALUES ('demo', 'Demo', 'Chinese', 'mimo')"
        ))
        connection.commit()

        assert has_legacy_name_unique(connection)
        assert rebuild_sqlite_prompt_configs(connection)
        assert not has_legacy_name_unique(connection)
        connection.execute(text(
            "INSERT INTO prompt_configs (name, locale, display_name, content, model_name) "
            "VALUES ('demo', 'en', 'Demo', 'English', 'mimo')"
        ))
        assert connection.execute(text("SELECT COUNT(*) FROM prompt_configs")).scalar_one() == 2
