"""Contract tests for provider-config resolution (Task 2).

Covers the following contract rules:
  R1 - Missing provider row + env key set → env fallback works
  R2 - DB unreachable + env key set → env fallback works
  R3 - Row present, enabled=False + env key → no key, failure_reason mentions disabled
  R4 - Feature enabled=False → resolve_effective_provider returns rule-only chain
  R5 - Request-provider override still goes first in the fallback chain
  R6 - Gemini image-model guard: '-image' model replaced for text features
  R7 - build_auth_headers: bearer / api_key_header / query_key
  R8 - Resolved provider dict has the expected stable key set
  R9 - Secret values never appear in failure_reason or diagnostics output

Run from the backend directory:
  cd backend && python -m pytest app/tests/test_provider_config_contract.py -v
"""
from __future__ import annotations

import contextlib
import json
import os
import unittest
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Expected stable key set for resolved provider dicts
# ---------------------------------------------------------------------------

_EXPECTED_PROVIDER_KEYS = frozenset({
    "api_key",
    "base_url",
    "default_model",
    "auth_type",
    "auth_header_name",
    "source",
    "db_url_source",
    "failure_reason",
})


# ---------------------------------------------------------------------------
# DB helpers — use SQLAlchemy in-memory SQLite to avoid Windows file locks
# ---------------------------------------------------------------------------

def _make_engine(providers=None, features=None):
    """Return an in-memory SQLite engine populated with test rows."""
    from sqlalchemy import create_engine, text

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE ai_api_providers (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_key     TEXT UNIQUE NOT NULL,
                display_name     TEXT DEFAULT '',
                category         TEXT DEFAULT 'llm',
                enabled          INTEGER DEFAULT 1,
                is_default       INTEGER DEFAULT 0,
                base_url         TEXT DEFAULT '',
                api_key_encrypted TEXT,
                auth_type        TEXT DEFAULT 'api_key_header',
                auth_header_name TEXT DEFAULT '',
                default_model    TEXT DEFAULT '',
                timeout_seconds  INTEGER DEFAULT 30,
                retry_count      INTEGER DEFAULT 1
            )
        """))
        conn.execute(text("""
            CREATE TABLE ai_feature_configs (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                feature_key      TEXT UNIQUE NOT NULL,
                enabled          INTEGER DEFAULT 1,
                default_provider TEXT NOT NULL DEFAULT 'mimo',
                fallback_order   TEXT,
                default_model    TEXT DEFAULT '',
                config           TEXT DEFAULT '{}'
            )
        """))
        for p in (providers or []):
            conn.execute(
                text(
                    "INSERT INTO ai_api_providers "
                    "(provider_key, display_name, enabled, base_url, api_key_encrypted, "
                    "auth_type, auth_header_name, default_model) "
                    "VALUES (:pk, :dn, :en, :bu, :ake, :at, :ahn, :dm)"
                ),
                {
                    "pk": p["provider_key"],
                    "dn": p.get("display_name", ""),
                    "en": 1 if p.get("enabled", True) else 0,
                    "bu": p.get("base_url", ""),
                    "ake": p.get("api_key_encrypted"),
                    "at": p.get("auth_type", "api_key_header"),
                    "ahn": p.get("auth_header_name", ""),
                    "dm": p.get("default_model", ""),
                },
            )
        for f in (features or []):
            conn.execute(
                text(
                    "INSERT INTO ai_feature_configs "
                    "(feature_key, enabled, default_provider, fallback_order, default_model, config) "
                    "VALUES (:fk, :en, :dp, :fo, :dm, :cfg)"
                ),
                {
                    "fk": f["feature_key"],
                    "en": 1 if f.get("enabled", True) else 0,
                    "dp": f.get("default_provider", "mimo"),
                    "fo": json.dumps(f.get("fallback_order", [])),
                    "dm": f.get("default_model", ""),
                    "cfg": json.dumps(f.get("config", {})),
                },
            )
    return engine


@contextlib.contextmanager
def _clean_env(*keys):
    """Context manager: remove env keys on entry, restore on exit."""
    saved = {k: os.environ.pop(k, None) for k in keys}
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# R1 — Missing row + env key → env fallback
# ---------------------------------------------------------------------------

class TestR1MissingRowEnvFallback(unittest.TestCase):

    def test_missing_row_uses_env_key(self):
        """Provider row not in DB → env var key is used."""
        engine = _make_engine(providers=[])  # empty providers table
        with patch("app.ai_runtime_config._get_engine", return_value=engine), \
             patch.dict(os.environ, {"MIMO_API_KEY": "env-test-key-r1"}, clear=False):
            from app.ai_runtime_config import resolve_provider_config
            result = resolve_provider_config("mimo")

        self.assertEqual(result["api_key"], "env-test-key-r1")
        self.assertEqual(result["source"], "env_var")

    def test_missing_row_no_env_key_returns_empty(self):
        """Provider row not in DB, no env key → empty key, no exception."""
        engine = _make_engine(providers=[])
        with patch("app.ai_runtime_config._get_engine", return_value=engine), \
             _clean_env("MIMO_API_KEY"):
            from app.ai_runtime_config import resolve_provider_config
            result = resolve_provider_config("mimo")

        self.assertEqual(result["api_key"], "")


# ---------------------------------------------------------------------------
# R2 — DB unreachable + env key → env fallback
# ---------------------------------------------------------------------------

class TestR2DbUnreachableEnvFallback(unittest.TestCase):

    def test_no_db_engine_uses_env_key(self):
        """_get_engine returns None (DB unavailable) → env var key is used."""
        with patch("app.ai_runtime_config._get_engine", return_value=None), \
             patch.dict(os.environ, {"MIMO_API_KEY": "env-test-key-r2"}, clear=False):
            from app.ai_runtime_config import resolve_provider_config
            result = resolve_provider_config("mimo")

        self.assertEqual(result["api_key"], "env-test-key-r2")
        self.assertEqual(result["source"], "env_var")

    def test_no_db_gemini_env_key(self):
        """Gemini env fallback when DB unavailable."""
        with patch("app.ai_runtime_config._get_engine", return_value=None), \
             patch.dict(os.environ, {"GEMINI_API_KEY": "env-gemini-key"}, clear=False):
            from app.ai_runtime_config import resolve_provider_config
            result = resolve_provider_config("gemini")

        self.assertEqual(result["api_key"], "env-gemini-key")
        self.assertEqual(result["source"], "env_var")


# ---------------------------------------------------------------------------
# R3 — Row exists, enabled=False → no key, no env fallback, disabled reason
# ---------------------------------------------------------------------------

class TestR3DisabledProviderAuthoritative(unittest.TestCase):

    def test_disabled_row_blocks_env_fallback(self):
        """Provider row present with enabled=False: env key is NOT used."""
        engine = _make_engine(providers=[{
            "provider_key": "mimo",
            "enabled": False,
            "api_key_encrypted": None,
            "default_model": "mimo-v2.5",
        }])
        with patch("app.ai_runtime_config._get_engine", return_value=engine), \
             patch.dict(os.environ, {"MIMO_API_KEY": "should-not-be-used"}, clear=False):
            from app.ai_runtime_config import resolve_provider_config
            result = resolve_provider_config("mimo")

        self.assertEqual(result["api_key"], "")
        self.assertNotEqual(result["api_key"], "should-not-be-used")

    def test_disabled_row_failure_reason_mentions_disabled(self):
        """failure_reason must explain the provider is disabled."""
        engine = _make_engine(providers=[{
            "provider_key": "mimo",
            "enabled": False,
        }])
        with patch("app.ai_runtime_config._get_engine", return_value=engine), \
             patch.dict(os.environ, {"MIMO_API_KEY": "some-key"}, clear=False):
            from app.ai_runtime_config import resolve_provider_config
            result = resolve_provider_config("mimo")

        reason = result.get("failure_reason", "")
        self.assertTrue(
            "disabled" in reason.lower() or "禁用" in reason,
            f"failure_reason '{reason}' does not mention disabled state",
        )

    def test_enabled_row_still_allows_env_key_when_db_key_missing(self):
        """Enabled row with no encrypted key still falls back to env key."""
        engine = _make_engine(providers=[{
            "provider_key": "mimo",
            "enabled": True,
            "api_key_encrypted": None,
        }])
        with patch("app.ai_runtime_config._get_engine", return_value=engine), \
             patch.dict(os.environ, {"MIMO_API_KEY": "fallback-env-key"}, clear=False):
            from app.ai_runtime_config import resolve_provider_config
            result = resolve_provider_config("mimo")

        self.assertEqual(result["api_key"], "fallback-env-key")


# ---------------------------------------------------------------------------
# R4 — Feature enabled=False → rule-only chain
# ---------------------------------------------------------------------------

class TestR4DisabledFeatureReturnsRuleChain(unittest.TestCase):

    def test_disabled_recommendation_returns_rule_chain(self):
        """Disabled recommendation feature returns ["rule"] chain."""
        engine = _make_engine(features=[{
            "feature_key": "recommendation",
            "enabled": False,
            "default_provider": "mimo",
            "fallback_order": ["mimo", "gemini", "rule"],
        }])
        with patch("app.ai_runtime_config._get_engine", return_value=engine):
            from app.ai_runtime_config import resolve_effective_provider
            provider, chain = resolve_effective_provider("recommendation")

        self.assertEqual(chain, ["rule"])
        self.assertEqual(provider, "rule")

    def test_disabled_assistant_chat_returns_rule_chain(self):
        """Disabled assistant_chat feature returns ["rule"] chain."""
        engine = _make_engine(features=[{
            "feature_key": "assistant_chat",
            "enabled": False,
            "default_provider": "mimo",
            "fallback_order": ["mimo", "deepseek", "rule"],
        }])
        with patch("app.ai_runtime_config._get_engine", return_value=engine):
            from app.ai_runtime_config import resolve_effective_provider
            provider, chain = resolve_effective_provider("assistant_chat")

        self.assertEqual(chain, ["rule"])

    def test_enabled_feature_with_db_row_returns_normal_chain(self):
        """Enabled feature DB row returns its configured chain, not rule-only."""
        engine = _make_engine(features=[{
            "feature_key": "recommendation",
            "enabled": True,
            "default_provider": "deepseek",
            "fallback_order": ["deepseek", "rule"],
        }])
        with patch("app.ai_runtime_config._get_engine", return_value=engine):
            from app.ai_runtime_config import resolve_effective_provider
            provider, chain = resolve_effective_provider("recommendation")

        self.assertIn("deepseek", chain)
        self.assertNotEqual(chain, ["rule"])

    def test_no_db_feature_row_uses_code_defaults(self):
        """No DB row for feature → code defaults are used (not rule-only)."""
        engine = _make_engine(features=[])  # no features in DB
        with patch("app.ai_runtime_config._get_engine", return_value=engine):
            from app.ai_runtime_config import resolve_effective_provider
            provider, chain = resolve_effective_provider("recommendation")

        self.assertNotEqual(chain, ["rule"])
        self.assertIn("mimo", chain)


# ---------------------------------------------------------------------------
# R5 — Request-provider override goes first
# ---------------------------------------------------------------------------

class TestR5RequestProviderOverride(unittest.TestCase):

    def test_request_provider_goes_first_with_db_feature(self):
        """Explicitly requested provider is first even when DB has different default."""
        engine = _make_engine(features=[{
            "feature_key": "recommendation",
            "enabled": True,
            "default_provider": "mimo",
            "fallback_order": ["mimo", "gemini", "rule"],
        }])
        with patch("app.ai_runtime_config._get_engine", return_value=engine):
            from app.ai_runtime_config import resolve_effective_provider
            provider, chain = resolve_effective_provider(
                "recommendation", request_provider="deepseek"
            )

        self.assertEqual(provider, "deepseek")
        self.assertEqual(chain[0], "deepseek")

    def test_request_provider_goes_first_without_db(self):
        """Explicitly requested provider is first when DB is unavailable."""
        with patch("app.ai_runtime_config._get_engine", return_value=None):
            from app.ai_runtime_config import resolve_effective_provider
            provider, chain = resolve_effective_provider(
                "recommendation", request_provider="gemini"
            )

        self.assertEqual(provider, "gemini")
        self.assertEqual(chain[0], "gemini")


# ---------------------------------------------------------------------------
# R6 — Gemini image-model guard for text features
# ---------------------------------------------------------------------------

class TestR6GeminiImageModelGuard(unittest.TestCase):

    def test_image_model_replaced_for_recommendation(self):
        """'-image' model in gemini row is replaced for 'recommendation' feature."""
        engine = _make_engine(providers=[{
            "provider_key": "gemini",
            "enabled": True,
            "api_key_encrypted": None,
            "default_model": "gemini-3.1-flash-image-preview",
        }])
        with patch("app.ai_runtime_config._get_engine", return_value=engine), \
             patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
            from app.ai_runtime_config import resolve_provider_config
            result = resolve_provider_config("gemini", feature_key="recommendation")

        self.assertNotIn("-image", result["default_model"].lower())

    def test_image_model_replaced_for_assistant_chat(self):
        """'-image' model in gemini row is replaced for 'assistant_chat' feature."""
        engine = _make_engine(providers=[{
            "provider_key": "gemini",
            "enabled": True,
            "api_key_encrypted": None,
            "default_model": "gemini-3.1-flash-image-preview",
        }])
        with patch("app.ai_runtime_config._get_engine", return_value=engine), \
             patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
            from app.ai_runtime_config import resolve_provider_config
            result = resolve_provider_config("gemini", feature_key="assistant_chat")

        self.assertNotIn("-image", result["default_model"].lower())

    def test_image_model_replaced_for_vision_analysis(self):
        """'-image' generation model is replaced for 'vision_analysis' feature."""
        engine = _make_engine(providers=[{
            "provider_key": "gemini",
            "enabled": True,
            "api_key_encrypted": None,
            "default_model": "gemini-pro-image-generation",
        }])
        with patch("app.ai_runtime_config._get_engine", return_value=engine), \
             patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
            from app.ai_runtime_config import resolve_provider_config
            result = resolve_provider_config("gemini", feature_key="vision_analysis")

        self.assertNotIn("-image", result["default_model"].lower())

    def test_image_model_kept_when_no_feature_key(self):
        """Without feature_key the image model is not replaced (tryon uses it)."""
        engine = _make_engine(providers=[{
            "provider_key": "gemini",
            "enabled": True,
            "api_key_encrypted": None,
            "default_model": "gemini-3.1-flash-image-preview",
        }])
        with patch("app.ai_runtime_config._get_engine", return_value=engine), \
             patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
            from app.ai_runtime_config import resolve_provider_config
            result = resolve_provider_config("gemini")  # no feature_key

        self.assertIn("-image", result["default_model"].lower())

    def test_correct_text_model_not_replaced(self):
        """Non-image Gemini model is not replaced even for text features."""
        engine = _make_engine(providers=[{
            "provider_key": "gemini",
            "enabled": True,
            "api_key_encrypted": None,
            "default_model": "gemini-3.1-flash-lite-preview",
        }])
        with patch("app.ai_runtime_config._get_engine", return_value=engine), \
             patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
            from app.ai_runtime_config import resolve_provider_config
            result = resolve_provider_config("gemini", feature_key="recommendation")

        self.assertEqual(result["default_model"], "gemini-3.1-flash-lite-preview")


# ---------------------------------------------------------------------------
# R7 — build_auth_headers helper
# ---------------------------------------------------------------------------

class TestR7BuildAuthHeaders(unittest.TestCase):

    def _fn(self, cfg):
        from app.ai_runtime_config import build_auth_headers
        return build_auth_headers(cfg)

    def test_bearer_auth_type(self):
        """auth_type='bearer' → Authorization: Bearer <key>."""
        headers = self._fn({
            "api_key": "mykey",
            "auth_type": "bearer",
            "auth_header_name": "",
        })
        self.assertEqual(headers.get("Authorization"), "Bearer mykey")
        self.assertNotIn("api-key", headers)

    def test_authorization_header_name_forces_bearer(self):
        """auth_header_name='Authorization' forces bearer style."""
        headers = self._fn({
            "api_key": "mykey",
            "auth_type": "api_key_header",
            "auth_header_name": "Authorization",
        })
        self.assertEqual(headers.get("Authorization"), "Bearer mykey")

    def test_custom_api_key_header(self):
        """Custom header name is used when auth_type is api_key_header."""
        headers = self._fn({
            "api_key": "mykey",
            "auth_type": "api_key_header",
            "auth_header_name": "api-key",
        })
        self.assertEqual(headers.get("api-key"), "mykey")
        self.assertNotIn("Authorization", headers)

    def test_default_api_key_header_fallback(self):
        """Empty auth_header_name defaults to 'api-key'."""
        headers = self._fn({
            "api_key": "mykey",
            "auth_type": "api_key_header",
            "auth_header_name": "",
        })
        self.assertEqual(headers.get("api-key"), "mykey")

    def test_query_key_auth_type_adds_no_auth_header(self):
        """auth_type='query_key' → no auth header (key goes in URL params)."""
        headers = self._fn({
            "api_key": "mykey",
            "auth_type": "query_key",
            "auth_header_name": "",
        })
        self.assertNotIn("Authorization", headers)
        self.assertNotIn("api-key", headers)
        self.assertIn("Content-Type", headers)

    def test_content_type_always_present(self):
        """Content-Type: application/json is always in headers."""
        for auth_type in ("bearer", "api_key_header", "query_key"):
            with self.subTest(auth_type=auth_type):
                headers = self._fn({
                    "api_key": "k",
                    "auth_type": auth_type,
                    "auth_header_name": "",
                })
                self.assertEqual(headers["Content-Type"], "application/json")


# ---------------------------------------------------------------------------
# R8 — Stable resolved-provider dict key set
# ---------------------------------------------------------------------------

class TestR8StableKeySet(unittest.TestCase):

    def test_resolve_provider_config_has_expected_keys(self):
        """Resolved provider dict always has the contract-defined keys."""
        with patch("app.ai_runtime_config._get_engine", return_value=None), \
             _clean_env("MIMO_API_KEY"):
            from app.ai_runtime_config import resolve_provider_config
            result = resolve_provider_config("mimo")

        missing = _EXPECTED_PROVIDER_KEYS - result.keys()
        self.assertEqual(missing, set(), f"Missing keys: {missing}")

    def test_resolve_provider_config_no_unexpected_secrets(self):
        """Resolved dict fields (except api_key) contain no secret format markers."""
        with patch("app.ai_runtime_config._get_engine", return_value=None), \
             patch.dict(os.environ, {"MIMO_API_KEY": "test-api-key-stable"}, clear=False):
            from app.ai_runtime_config import resolve_provider_config
            result = resolve_provider_config("mimo")

        for key, val in result.items():
            if key == "api_key":
                continue
            val_str = str(val)
            self.assertNotIn("fernet:", val_str.lower(),
                             f"Field '{key}' contains 'fernet:' prefix")
            self.assertNotIn("b64:", val_str.lower(),
                             f"Field '{key}' contains 'b64:' prefix")


# ---------------------------------------------------------------------------
# R9 — Secrets never appear in failure_reason or diagnostics
# ---------------------------------------------------------------------------

class TestR9NoSecretsInDiagnostics(unittest.TestCase):

    def test_failure_reason_does_not_contain_env_key(self):
        """The env-supplied API key must never appear in failure_reason."""
        secret = "super-secret-api-key-r9-do-not-leak"
        with patch("app.ai_runtime_config._get_engine", return_value=None), \
             patch.dict(os.environ, {"MIMO_API_KEY": secret}, clear=False):
            from app.ai_runtime_config import resolve_provider_config
            result = resolve_provider_config("mimo")

        reason = result.get("failure_reason", "")
        self.assertNotIn(secret, reason,
                         "Secret value leaked into failure_reason")

    def test_diagnostics_does_not_contain_api_key(self):
        """get_diagnostics output must not contain any API key value."""
        secret = "super-secret-api-key-for-diagnostics"
        engine = _make_engine(providers=[])
        with patch("app.ai_runtime_config._get_engine", return_value=engine), \
             patch.dict(os.environ, {"MIMO_API_KEY": secret}, clear=False):
            from app.ai_runtime_config import get_diagnostics
            diag = get_diagnostics()

        diag_str = json.dumps(diag)
        self.assertNotIn(secret, diag_str,
                         "Secret value leaked into diagnostics output")

    def test_disabled_provider_failure_reason_has_no_key(self):
        """failure_reason for a disabled provider must not include key material."""
        secret = "env-key-r9-disabled"
        engine = _make_engine(providers=[{
            "provider_key": "mimo",
            "enabled": False,
        }])
        with patch("app.ai_runtime_config._get_engine", return_value=engine), \
             patch.dict(os.environ, {"MIMO_API_KEY": secret}, clear=False):
            from app.ai_runtime_config import resolve_provider_config
            result = resolve_provider_config("mimo")

        reason = result.get("failure_reason", "")
        self.assertNotIn(secret, reason,
                         "Secret value leaked into failure_reason for disabled provider")


# ---------------------------------------------------------------------------
# Entry point for direct invocation
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
