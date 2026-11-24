import asyncio
import base64
import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from PIL import Image
from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, MetaData, String, Table, Text, create_engine

from app import admin_runtime_config, totokens_image


def png_bytes(color):
    output = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(output, "PNG")
    return output.getvalue()


class RelayImageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.person = Path(self.temp.name) / "person.png"
        self.garment = Path(self.temp.name) / "garment.png"
        self.person.write_bytes(png_bytes("red"))
        self.garment.write_bytes(png_bytes("blue"))
        self.output = png_bytes("green")
        self.sent = []

    def client(self, payload=None, status=200, error=None):
        sent = self.sent

        class Client:
            def __init__(self, **kwargs):
                self.options = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, **kwargs):
                sent.append((url, kwargs, self.options))
                if error:
                    raise error
                return SimpleNamespace(status_code=status, json=lambda: payload)

        return Client

    async def generate(self, model_key):
        return await totokens_image.generate_image(
            base_url="https://totokens.cc/v1/", api_key="fake-key", model_key=model_key,
            model_id="gemini-3.1-flash-image" if model_key == "flash" else "gpt-image-2",
            prompt="Use both references", model_path=str(self.person), garment_path=str(self.garment),
            timeout_seconds=120, fetch_remote_image=AsyncMock(side_effect=AssertionError("unexpected network")),
        )

    async def test_gemini_native_request_contains_both_images(self):
        payload = {"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "image/png", "data": base64.b64encode(self.output).decode(),
        }}]}}]}
        with patch.object(totokens_image.httpx, "AsyncClient", self.client(payload)):
            result = await self.generate("flash")
        self.assertEqual(Image.open(io.BytesIO(result)).size, (4, 4))
        self.assertEqual(len(self.sent), 1)
        url, request, options = self.sent[0]
        self.assertEqual(url, "https://totokens.cc/v1beta/models/gemini-3.1-flash-image:generateContent")
        self.assertEqual(request["headers"]["Authorization"], "Bearer fake-key")
        parts = request["json"]["contents"][0]["parts"]
        self.assertEqual(parts[0]["text"], "Use both references")
        self.assertEqual(base64.b64decode(parts[1]["inlineData"]["data"]), self.person.read_bytes())
        self.assertEqual(base64.b64decode(parts[2]["inlineData"]["data"]), self.garment.read_bytes())
        self.assertFalse(options["follow_redirects"])

    async def test_gpt_image_edit_sends_two_distinct_files(self):
        payload = {"data": [{"b64_json": base64.b64encode(self.output).decode()}]}
        with patch.object(totokens_image.httpx, "AsyncClient", self.client(payload)):
            result = await self.generate("pro")
        self.assertEqual(Image.open(io.BytesIO(result)).size, (4, 4))
        url, request, _ = self.sent[0]
        self.assertEqual(url, "https://totokens.cc/v1/images/edits")
        self.assertEqual(request["data"], {"model": "gpt-image-2", "prompt": "Use both references", "n": "1"})
        self.assertEqual([item[0] for item in request["files"]], ["image[]", "image[]"])
        self.assertEqual(request["files"][0][1][1], self.person.read_bytes())
        self.assertEqual(request["files"][1][1][1], self.garment.read_bytes())
        self.assertEqual(len(self.sent), 1)

    async def test_chatgpt_key_routes_chatgpt_image_latest_via_relay(self):
        payload = {"data": [{"b64_json": base64.b64encode(self.output).decode()}]}
        with patch.object(totokens_image.httpx, "AsyncClient", self.client(payload)):
            result = await totokens_image.generate_image(
                base_url="https://totokens.cc", api_key="fake-key", model_id="chatgpt-image-latest", model_key="chatgpt",
                prompt="Use both references", model_path=str(self.person), garment_path=str(self.garment),
                timeout_seconds=120, fetch_remote_image=AsyncMock(side_effect=AssertionError("unexpected network")),
            )
        self.assertEqual(Image.open(io.BytesIO(result)).size, (4, 4))
        url, request, _ = self.sent[0]
        self.assertEqual(url, "https://totokens.cc/v1/images/edits")
        self.assertEqual(request["data"]["model"], "chatgpt-image-latest")
        self.assertEqual(len(self.sent), 1)

    async def test_relay_error_never_retries_or_exposes_key(self):
        with patch.object(totokens_image.httpx, "AsyncClient", self.client(status=429)):
            with self.assertRaises(RuntimeError) as error:
                await self.generate("pro")
        self.assertEqual(len(self.sent), 1)
        self.assertIn("429", str(error.exception))
        self.assertNotIn("fake-key", str(error.exception))

    async def test_gpt_url_uses_the_checked_image_fetcher(self):
        payload = {"data": [{"url": "https://images.example/output.png"}]}
        fetch = AsyncMock(return_value=(self.output, "image/png"))
        with patch.object(totokens_image.httpx, "AsyncClient", self.client(payload)):
            result = await totokens_image.generate_image(
                base_url="https://totokens.cc", api_key="fake-key", model_id="gpt-image-2", model_key="pro",
                prompt="test", model_path=str(self.person), garment_path=str(self.garment),
                timeout_seconds=120, fetch_remote_image=fetch,
            )
        fetch.assert_awaited_once_with("https://images.example/output.png")
        self.assertEqual(Image.open(io.BytesIO(result)).size, (4, 4))

    def test_relay_url_rejects_insecure_or_embedded_credentials(self):
        for value in ("http://totokens.cc", "https://user:password@totokens.cc", "https://totokens.cc/?key=secret"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                totokens_image.relay_root(value)


class RelayRuntimeTests(unittest.TestCase):
    def test_admin_selected_provider_is_used_without_touching_gemini(self):
        engine = create_engine("sqlite:///:memory:")
        metadata = MetaData()
        providers = Table("ai_api_providers", metadata,
            Column("provider_key", String, primary_key=True), Column("api_key_encrypted", Text),
            Column("enabled", Boolean), Column("timeout_seconds", Integer), Column("retry_count", Integer),
            Column("updated_at", DateTime), Column("base_url", String))
        features = Table("ai_feature_configs", metadata,
            Column("feature_key", String, primary_key=True), Column("enabled", Boolean), Column("config", JSON),
            Column("updated_at", DateTime), Column("default_model", String), Column("default_provider", String))
        metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(providers.insert(), [
                {"provider_key": "gemini", "api_key_encrypted": "direct", "enabled": True, "timeout_seconds": 30, "retry_count": 1},
                {"provider_key": "totokens", "api_key_encrypted": "relay", "enabled": True, "timeout_seconds": 120, "retry_count": 0, "base_url": "https://totokens.cc"},
            ])
            conn.execute(features.insert(), {"feature_key": "tryon", "enabled": True,
                "default_provider": "totokens", "default_model": "direct-model",
                "config": {"flash_model": "direct-model", "pro_model": "direct-pro"}})
        with patch.object(admin_runtime_config, "_get_engine", return_value=engine), \
             patch.object(admin_runtime_config, "_decrypt_secret", side_effect=lambda value: "decoded-" + value):
            config = admin_runtime_config._read_config_from_db()
        self.assertEqual(config["provider_key"], "totokens")
        self.assertEqual(config["api_key"], "decoded-relay")
        self.assertEqual(config["flash_model"], "gemini-3.1-flash-image")
        self.assertEqual(config["pro_model"], "gpt-image-2")
        self.assertEqual(config["retry_count"], 0)
        with patch.object(admin_runtime_config, "resolve_tryon_runtime_config", return_value=config):
            status = admin_runtime_config.get_tryon_runtime_status()
        self.assertEqual(status["model_labels"]["pro"], "gpt-image-2")
        self.assertNotIn("api_key", status)

    def test_dispatch_does_not_add_paid_fallback_models(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "UPLOAD_DIR": directory + "/uploads", "ASSET_DIR": directory + "/assets",
            "HISTORY_DIR": directory + "/history", "OBJECT_STORAGE_PROVIDER": "local",
        }):
            import main
            config = {"enabled": True, "provider_key": "totokens", "api_key": "fake-key",
                      "flash_model": "gemini-3.1-flash-image", "pro_model": "gpt-image-2"}
            with patch.object(main, "resolve_tryon_runtime_config", return_value=config):
                self.assertEqual(main._resolve_tryon_generation_config("pro")["model_ids"], ["gpt-image-2"])
                fake_generate = AsyncMock(return_value=b"image")
                with patch.object(totokens_image, "generate_image", fake_generate):
                    self.assertEqual(asyncio.run(main._call_ai_studio_image("prompt", "person", "garment", "pro")), b"image")
                fake_generate.assert_awaited_once()
                with patch.object(main, "KEY_USAGE", {}):
                    main._record_key_usage("pro", True)
                    self.assertIsNone(main.KEY_USAGE["tryon"]["cost"])
                    self.assertFalse(main.KEY_USAGE["tryon"]["cost_known"])

    def test_dual_provider_exposes_chatgpt_model_and_dispatches_to_totokens(self):
        engine = create_engine("sqlite:///:memory:")
        metadata = MetaData()
        providers = Table("ai_api_providers", metadata,
            Column("provider_key", String, primary_key=True), Column("api_key_encrypted", Text),
            Column("enabled", Boolean), Column("timeout_seconds", Integer), Column("retry_count", Integer),
            Column("updated_at", DateTime), Column("base_url", String))
        features = Table("ai_feature_configs", metadata,
            Column("feature_key", String, primary_key=True), Column("enabled", Boolean), Column("config", JSON),
            Column("updated_at", DateTime), Column("default_model", String), Column("default_provider", String))
        metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(providers.insert(), [
                {"provider_key": "gemini", "api_key_encrypted": "direct", "enabled": True, "timeout_seconds": 30, "retry_count": 1},
                {"provider_key": "totokens", "api_key_encrypted": "relay", "enabled": True, "timeout_seconds": 120, "retry_count": 0, "base_url": "https://totokens.cc"},
            ])
            conn.execute(features.insert(), {"feature_key": "tryon", "enabled": True,
                "default_provider": "gemini", "default_model": "gemini-3.1-flash-image-preview",
                "config": {"flash_model": "gemini-3.1-flash-image-preview", "pro_model": "gemini-3-pro-image-preview", "totokens_pro_model": "chatgpt-image-latest"}})
        with patch.object(admin_runtime_config, "_get_engine", return_value=engine), \
             patch.object(admin_runtime_config, "_decrypt_secret", side_effect=lambda value: "decoded-" + value):
            config = admin_runtime_config._read_config_from_db()
        self.assertEqual(config["provider_key"], "gemini")
        self.assertEqual(config["api_key"], "decoded-direct")
        self.assertTrue(config["relay_configured"])
        self.assertEqual(config["relay_api_key"], "decoded-relay")
        self.assertEqual(config["chatgpt_model"], "chatgpt-image-latest")
        with patch.object(admin_runtime_config, "resolve_tryon_runtime_config", return_value=config):
            status = admin_runtime_config.get_tryon_runtime_status()
        self.assertEqual(status["available_models"], ["flash", "pro", "chatgpt"])
        self.assertTrue(status["chatgpt_configured"])
        self.assertEqual(status["chatgpt_model"], "chatgpt-image-latest")
        self.assertNotIn("api_key", status)
        self.assertNotIn("relay_api_key", status)

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "UPLOAD_DIR": directory + "/uploads", "ASSET_DIR": directory + "/assets",
            "HISTORY_DIR": directory + "/history", "OBJECT_STORAGE_PROVIDER": "local",
        }):
            import main
            with patch.object(main, "resolve_tryon_runtime_config", return_value=config):
                self.assertEqual(main._validate_model_key("chatgpt"), "chatgpt")
                resolved_chatgpt = main._resolve_tryon_generation_config("chatgpt")
                self.assertEqual(resolved_chatgpt["provider_key"], "totokens")
                self.assertEqual(resolved_chatgpt["api_key"], "decoded-relay")
                self.assertEqual(resolved_chatgpt["model_ids"], ["chatgpt-image-latest"])
                self.assertEqual(main._resolve_tryon_generation_config("flash")["provider_key"], "gemini")
                fake_generate = AsyncMock(return_value=b"chatgpt-image")
                with patch.object(totokens_image, "generate_image", fake_generate):
                    self.assertEqual(asyncio.run(main._call_ai_studio_image("prompt", "person", "garment", "chatgpt")), b"chatgpt-image")
                fake_generate.assert_awaited_once()

    def test_multi_api_profiles_route_gemini_gpt1k_and_gpt2k4k_strictly(self):
        engine = create_engine("sqlite:///:memory:")
        metadata = MetaData()
        providers = Table("ai_api_providers", metadata,
            Column("provider_key", String, primary_key=True), Column("api_key_encrypted", Text),
            Column("enabled", Boolean), Column("timeout_seconds", Integer), Column("retry_count", Integer),
            Column("updated_at", DateTime), Column("base_url", String))
        features = Table("ai_feature_configs", metadata,
            Column("feature_key", String, primary_key=True), Column("enabled", Boolean), Column("config", JSON),
            Column("updated_at", DateTime), Column("default_model", String), Column("default_provider", String))
        metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(providers.insert(), [
                {"provider_key": "gemini", "api_key_encrypted": None, "enabled": True, "timeout_seconds": 60, "retry_count": 1},
                {"provider_key": "totokens", "api_key_encrypted": None, "enabled": True, "timeout_seconds": 120, "retry_count": 0, "base_url": "https://totokens.cc"},
            ])
            conn.execute(features.insert(), {
                "feature_key": "tryon",
                "enabled": True,
                "default_provider": "totokens",
                "default_model": "gemini-3.1-flash-image",
                "config": {
                    "totokens_flash_model": "gemini-3.1-flash-image",
                    "totokens_pro_model": "gpt-image-2",
                    "totokens_apis": [
                        {"id": "totokens_gemini", "scope": "gemini", "enabled": True, "api_key_encrypted": "gem-k"},
                        {"id": "totokens_gpt_1k", "scope": "gpt_1k", "enabled": True, "api_key_encrypted": "1k-k"},
                        {"id": "totokens_gpt_2k4k", "scope": "gpt_2k4k", "enabled": True, "api_key_encrypted": "2k4k-k"},
                    ],
                },
            })
        with patch.object(admin_runtime_config, "_get_engine", return_value=engine), \
             patch.object(admin_runtime_config, "_decrypt_secret", side_effect=lambda value: "dec-" + value):
            config = admin_runtime_config._read_config_from_db()

        self.assertTrue(config["relay_configured"])
        with patch.object(admin_runtime_config, "resolve_tryon_runtime_config", return_value=config):
            status = admin_runtime_config.get_tryon_runtime_status()
        status_text = str(status)
        self.assertNotIn("dec-gem-k", status_text)
        self.assertNotIn("dec-1k-k", status_text)
        self.assertNotIn("dec-2k4k-k", status_text)
        totokens_prov = next(p for p in status["providers"] if p["key"] == "totokens")
        self.assertTrue(totokens_prov["configured"])
        self.assertEqual(totokens_prov["configured_scopes"], ["gemini", "gpt_1k", "gpt_2k4k"])

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "UPLOAD_DIR": directory + "/uploads", "ASSET_DIR": directory + "/assets",
            "HISTORY_DIR": directory + "/history", "OBJECT_STORAGE_PROVIDER": "local",
        }):
            import main
            with patch.object(main, "resolve_tryon_runtime_config", return_value=config):
                gem_cfg = main._resolve_tryon_generation_config(
                    "flash", provider="totokens", model_id="gemini-3.1-flash-image", detail_options={"image_size": "2K"},
                )
                self.assertEqual(gem_cfg["api_key"], "dec-gem-k")

                gpt_1k_cfg = main._resolve_tryon_generation_config(
                    "chatgpt", provider="totokens", model_id="gpt-image-2", detail_options={"image_size": "1K"},
                )
                self.assertEqual(gpt_1k_cfg["api_key"], "dec-1k-k")

                gpt_2k_cfg = main._resolve_tryon_generation_config(
                    "chatgpt", provider="totokens", model_id="gpt-image-2", detail_options={"image_size": "2K"},
                )
                self.assertEqual(gpt_2k_cfg["api_key"], "dec-2k4k-k")

                gpt_4k_cfg = main._resolve_tryon_generation_config(
                    "chatgpt", provider="totokens", model_id="gpt-image-2", detail_options={"image_size": "4K"},
                )
                self.assertEqual(gpt_4k_cfg["api_key"], "dec-2k4k-k")

            # Missing 2K/4K key must NEVER fall back to 1K key.
            only_1k_cfg = dict(config)
            only_1k_cfg["totokens_apis_internal"] = [
                {**p, "api_key": ("dec-1k-k" if p["id"] == "totokens_gpt_1k" else "")}
                for p in config["totokens_apis_internal"]
            ]
            with patch.object(main, "resolve_tryon_runtime_config", return_value=only_1k_cfg):
                with self.assertRaises(RuntimeError):
                    main._resolve_tryon_generation_config(
                        "chatgpt", provider="totokens", model_id="gpt-image-2", detail_options={"image_size": "2K"},
                    )

            # When only 2K/4K key exists and image_size is auto on gpt-image-2, promote to 2K safely.
            only_2k_cfg = dict(config)
            only_2k_cfg["totokens_apis_internal"] = [
                {**p, "api_key": ("dec-2k4k-k" if p["id"] == "totokens_gpt_2k4k" else "")}
                for p in config["totokens_apis_internal"]
            ]
            with patch.object(main, "resolve_tryon_runtime_config", return_value=only_2k_cfg):
                promoted = main._resolve_tryon_generation_config(
                    "chatgpt", provider="totokens", model_id="gpt-image-2", detail_options={},
                )
                self.assertEqual(promoted["api_key"], "dec-2k4k-k")
                self.assertEqual(promoted["effective_detail_options"]["image_size"], "2K")


if __name__ == "__main__":
    unittest.main()
