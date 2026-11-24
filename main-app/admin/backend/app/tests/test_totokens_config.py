import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import AIAPIProvider, AIFeatureConfig, Base, _seed_ai_configs
from app.routers.ai_config import (
    TryonConfigUpdateRequest, get_tryon_config, test_tryon_config as run_connection_check,
    update_tryon_config,
)


class ToTokensAdminConfigTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        _seed_ai_configs(self.session)
        self.admin = SimpleNamespace(username="test-admin")
        self.encrypt = patch("app.services.secret_crypto.encrypt_secret", side_effect=lambda key: "encrypted:" + key)
        self.decrypt = patch("app.routers.ai_config.decrypt_secret", side_effect=lambda value: value.removeprefix("encrypted:"))
        self.encrypt.start()
        self.decrypt.start()
        self.addCleanup(self.encrypt.stop)
        self.addCleanup(self.decrypt.stop)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)

    def test_switching_provider_preserves_direct_gemini_and_key(self):
        direct = self.session.query(AIAPIProvider).filter_by(provider_key="gemini").one()
        direct.api_key_encrypted = "encrypted:direct-key"
        self.session.commit()
        result = update_tryon_config(TryonConfigUpdateRequest(
            provider_key="totokens", enabled=True, api_key="relay-key", base_url="https://totokens.cc/v1",
            flash_model="gemini-3.1-flash-image", pro_model="gpt-image-2", retry_count=0,
        ), admin=self.admin, db=self.session)
        self.assertEqual(result["provider_key"], "totokens")
        self.assertNotIn("api_key", result)
        self.assertEqual(direct.api_key_encrypted, "encrypted:direct-key")
        relay = self.session.query(AIAPIProvider).filter_by(provider_key="totokens").one()
        self.assertEqual(relay.api_key_encrypted, "encrypted:relay-key")
        feature = self.session.query(AIFeatureConfig).filter_by(feature_key="tryon").one()
        self.assertEqual(feature.config["flash_model"], "gemini-3.1-flash-image-preview")
        self.assertEqual(feature.config["totokens_pro_model"], "gpt-image-2")
        self.assertEqual(feature.default_model, "gemini-3.1-flash-image")
        self.assertEqual(feature.fallback_order, ["totokens"])

        direct_view = get_tryon_config(provider_key="gemini", admin=self.admin, db=self.session)
        self.assertEqual(direct_view["active_provider_key"], "totokens")
        self.assertEqual(direct_view["flash_model"], "gemini-3.1-flash-image-preview")
        update_tryon_config(TryonConfigUpdateRequest(provider_key="gemini", enabled=True), admin=self.admin, db=self.session)
        self.assertEqual(feature.default_provider, "gemini")
        self.assertEqual(feature.default_model, "gemini-3.1-flash-image-preview")
        self.assertEqual(feature.fallback_order, ["gemini"])
        self.assertEqual(feature.config["totokens_pro_model"], "gpt-image-2")
        self.assertEqual(relay.api_key_encrypted, "encrypted:relay-key")

    def test_rejects_insecure_relay_url(self):
        with self.assertRaises(HTTPException):
            update_tryon_config(TryonConfigUpdateRequest(
                provider_key="totokens", enabled=False, base_url="http://totokens.cc",
            ), admin=self.admin, db=self.session)
        self.session.rollback()
        feature = self.session.query(AIFeatureConfig).filter_by(feature_key="tryon").one()
        self.assertEqual(feature.default_provider, "gemini")

    def test_connection_check_only_reads_model_list(self):
        update_tryon_config(TryonConfigUpdateRequest(
            provider_key="totokens", enabled=True, api_key="relay-key", base_url="https://totokens.cc/v1",
        ), admin=self.admin, db=self.session)
        calls = []

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, url, **kwargs):
                calls.append((url, kwargs))
                return SimpleNamespace(status_code=200, json=lambda: {"data": [
                    {"id": "gemini-3.1-flash-image"}, {"id": "gpt-image-2"},
                ]})

        with patch("app.routers.ai_config.httpx.AsyncClient", FakeClient):
            result = asyncio.run(run_connection_check(admin=self.admin, db=self.session))
        self.assertTrue(result["success"])
        self.assertEqual(result["model_check"], {"flash_found": True, "pro_found": True})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "https://totokens.cc/v1/models")
        self.assertEqual(calls[0][1]["headers"]["Authorization"], "Bearer relay-key")

    def test_multi_api_profiles_save_redact_test_and_clear_independently(self):
        from fastapi import HTTPException
        from app.database import AIFeatureConfig
        from app.routers.ai_config import TotokensAPIProfileUpdate

        # Configure three separate ToTokens keys without any legacy root key.
        saved = update_tryon_config(
            TryonConfigUpdateRequest(
                provider_key="totokens",
                enabled=True,
                base_url="https://totokens.cc",
                totokens_apis=[
                    TotokensAPIProfileUpdate(id="totokens_gemini", api_key="sk-gemini-group-secret"),
                    TotokensAPIProfileUpdate(id="totokens_gpt_1k", api_key="sk-gpt-1k-group-secret"),
                    TotokensAPIProfileUpdate(id="totokens_gpt_2k4k", api_key="sk-gpt-2k4k-group-secret"),
                    TotokensAPIProfileUpdate(
                        id="totokens_custom_vip",
                        scope="gpt_all",
                        label="VIP GPT Route",
                        api_key="sk-vip-custom-secret",
                        default_model="gpt-image-2",
                        models=["gpt-image-2", "gpt-image-1.5"],
                    ),
                ],
            ),
            admin=self.admin,
            db=self.session,
        )

        serialized_text = str(saved)
        for secret in (
            "sk-gemini-group-secret",
            "sk-gpt-1k-group-secret",
            "sk-gpt-2k4k-group-secret",
            "sk-vip-custom-secret",
        ):
            self.assertNotIn(secret, serialized_text)
        self.assertFalse(saved["has_api_key"])
        self.assertTrue(saved["totokens_has_api_key"])
        self.assertEqual(saved["totokens_configured_count"], 4)
        self.assertEqual(len(saved["totokens_apis"]), 4)

        # Partial update preserving untouched encrypted keys
        fetched = get_tryon_config(provider_key="totokens", admin=self.admin, db=self.session)
        self.assertTrue(all(p["has_api_key"] for p in fetched["totokens_apis"]))
        feature = self.session.query(AIFeatureConfig).filter_by(feature_key="tryon").one()
        raw_apis = feature.config["totokens_apis"]
        self.assertTrue(all(item["api_key_encrypted"].startswith("encrypted:") for item in raw_apis))

        # Test individual profile checks only that profile's key
        tested_calls = []

        class ProfileFakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, url, **kwargs):
                tested_calls.append((url, kwargs["headers"]["Authorization"]))
                return SimpleNamespace(status_code=200, json=lambda: {"data": [{"id": "gpt-image-2"}]})

        with patch("app.routers.ai_config.httpx.AsyncClient", ProfileFakeClient):
            res_2k = asyncio.run(
                run_connection_check(provider_key="totokens", profile_id="totokens_gpt_2k4k", admin=self.admin, db=self.session)
            )
        self.assertTrue(res_2k["success"])
        self.assertEqual(res_2k["profile_id"], "totokens_gpt_2k4k")
        self.assertEqual(tested_calls, [("https://totokens.cc/v1/models", "Bearer sk-gpt-2k4k-group-secret")])

        # Clear one profile while keeping others, and reject deleting built-ins
        cleared = update_tryon_config(
            TryonConfigUpdateRequest(
                provider_key="totokens",
                totokens_apis=[
                    TotokensAPIProfileUpdate(id="totokens_gpt_1k", clear_api_key=True),
                    TotokensAPIProfileUpdate(id="totokens_custom_vip", delete=True),
                ],
            ),
            admin=self.admin,
            db=self.session,
        )
        by_id = {p["id"]: p for p in cleared["totokens_apis"]}
        self.assertFalse(by_id["totokens_gpt_1k"]["has_api_key"])
        self.assertTrue(by_id["totokens_gpt_2k4k"]["has_api_key"])
        self.assertNotIn("totokens_custom_vip", by_id)

        with self.assertRaises(HTTPException) as exc:
            update_tryon_config(
                TryonConfigUpdateRequest(
                    provider_key="totokens",
                    totokens_apis=[TotokensAPIProfileUpdate(id="totokens_gemini", delete=True)],
                ),
                admin=self.admin,
                db=self.session,
            )
        self.assertEqual(exc.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
