import asyncio
import json
import os
import sqlite3
import struct
import sys
import tempfile
import types
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import admin_runtime_config, task_db
from app.queue_worker import process_queue_message
from app.task_queue import QueueMessage
from app.tryon_options import (
    build_runtime_providers_catalog,
    get_model_capabilities,
    infer_preset_key,
    normalize_tryon_options,
    validate_model_id,
    validate_provider_key,
)


def _make_tiny_png() -> bytes:
    def _chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def _load_locale(name: str) -> dict:
    path = ROOT_DIR / "static" / "i18n" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


class _FakeQueue:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.requeued: list[tuple[str, int]] = []

    def delete(self, msg: QueueMessage) -> None:
        self.deleted.append(msg.task_id)

    def requeue(self, msg: QueueMessage, delay_seconds: int = 10) -> None:
        self.requeued.append((msg.task_id, delay_seconds))

    def renew_visibility(self, msg: QueueMessage, visibility_timeout: int = 90) -> QueueMessage:
        return msg


class TestTryonControls(unittest.TestCase):
    def test_tryon_options_validation_and_capabilities(self):
        self.assertEqual(validate_provider_key("Gemini "), "gemini")
        self.assertEqual(validate_provider_key("totokens"), "totokens")
        self.assertIsNone(validate_provider_key("auto"))
        with self.assertRaises(ValueError):
            validate_provider_key("openai-direct")

        self.assertEqual(
            validate_model_id("  gemini-3.1-flash-image-preview  "),
            "gemini-3.1-flash-image-preview",
        )
        self.assertEqual(
            validate_model_id("publishers/google/models/gemini-2.5-flash-image"),
            "publishers/google/models/gemini-2.5-flash-image",
        )
        for bad in ("../secret", "https://evil.example/m", "gpt-image-2?x=1", "user@host", "bad model"):
            with self.assertRaises(ValueError, msg=f"should reject {bad}"):
                validate_model_id(bad)

        self.assertEqual(infer_preset_key("gpt-image-2"), "chatgpt")
        self.assertEqual(infer_preset_key("gemini-3-pro-image-preview"), "pro")
        self.assertEqual(infer_preset_key("gemini-3.1-flash-image"), "flash")

        caps_gpt = get_model_capabilities("totokens", "gpt-image-2")
        self.assertEqual(caps_gpt["protocol"], "openai_images_edit")
        self.assertTrue(caps_gpt["supports_image_size"])
        self.assertEqual(caps_gpt["image_size_options"], ["auto", "1K", "2K", "4K"])
        self.assertTrue(caps_gpt["supports_quality"])
        self.assertFalse(caps_gpt["supports_seed"])

        caps_gpt1 = get_model_capabilities("totokens", "gpt-image-1")
        self.assertEqual(caps_gpt1["protocol"], "openai_images_edit")
        self.assertFalse(caps_gpt1["supports_image_size"])

        caps_25 = get_model_capabilities("gemini", "gemini-2.5-flash-image")
        self.assertFalse(caps_25["supports_image_size"])
        self.assertTrue(caps_25["supports_seed"])

        # Default 'auto' / blank options are omitted.
        self.assertEqual(
            normalize_tryon_options(
                aspect_ratio="auto",
                image_size="auto",
                quality="auto",
                temperature="",
                seed=None,
                protocol="gemini_generate_content",
            ),
            {},
        )

        # Gemini protocol filters out GPT quality while validating numeric bounds.
        norm_gem = normalize_tryon_options(
            aspect_ratio="3:4",
            image_size="2k",
            quality="high",
            temperature="0.65",
            seed="12345",
            protocol="gemini_generate_content",
        )
        self.assertEqual(
            norm_gem,
            {"aspect_ratio": "3:4", "image_size": "2K", "temperature": 0.65, "seed": 12345},
        )

        # OpenAI edit protocol filters out image_size/temperature/seed for 1K-only GPT models,
        # while retaining 1K/2K/4K image_size for gpt-image-2.
        norm_gpt = normalize_tryon_options(
            aspect_ratio="4:5",
            image_size="4K",
            quality="HIGH",
            temperature="0.9",
            seed="99",
            protocol="openai_images_edit",
            model_id="gpt-image-1",
        )
        self.assertEqual(norm_gpt, {"aspect_ratio": "4:5", "quality": "high"})

        norm_gpt2 = normalize_tryon_options(
            aspect_ratio="3:4",
            image_size="2k",
            quality="HIGH",
            temperature="0.9",
            seed="99",
            protocol="openai_images_edit",
            model_id="gpt-image-2",
        )
        self.assertEqual(norm_gpt2, {"aspect_ratio": "3:4", "image_size": "2K", "quality": "high"})

        for invalid_kwargs in (
            {"aspect_ratio": "99:1"},
            {"image_size": "8K"},
            {"quality": "ultra"},
            {"temperature": "2.5"},
            {"seed": "-1"},
            {"seed": "2147483648"},
        ):
            with self.assertRaises(ValueError):
                normalize_tryon_options(**invalid_kwargs)

    def test_runtime_status_catalog_filters_models_and_redacts_secrets(self):
        fake_config = {
            "enabled": True,
            "feature_enabled": True,
            "configured": True,
            "provider_key": "gemini",
            "api_key": "AIza-SECRET-GEMINI-KEY",
            "flash_model": "gemini-3.1-flash-image-preview",
            "pro_model": "gemini-3-pro-image-preview",
            "chatgpt_model": "gpt-image-2",
            "relay_configured": True,
            "relay_enabled": True,
            "relay_api_key": "sk-SECRET-TOTOKENS-KEY",
            "relay_base_url": "https://totokens.cc",
            "providers_internal": {
                "gemini": {
                    "provider_key": "gemini",
                    "enabled": True,
                    "configured": True,
                    "api_key": "AIza-SECRET-GEMINI-KEY",
                    "default_model": "gemini-3.1-flash-image-preview",
                    "models": [
                        "gemini-3.1-flash-image-preview",
                        "gemini-3-pro-image-preview",
                        "text-embedding-004",
                        "gemini-2.5-flash-image",
                    ],
                },
                "totokens": {
                    "provider_key": "totokens",
                    "enabled": True,
                    "configured": True,
                    "api_key": "sk-SECRET-TOTOKENS-KEY",
                    "base_url": "https://totokens.cc",
                    "default_model": "gpt-image-2",
                    "models": [
                        "gpt-image-2",
                        "gemini-3.1-flash-image",
                        "whisper-1",
                    ],
                },
            },
        }
        with patch.object(admin_runtime_config, "resolve_tryon_runtime_config", return_value=fake_config):
            status = admin_runtime_config.get_tryon_runtime_status()

        serialized = json.dumps(status, ensure_ascii=False)
        self.assertNotIn("AIza-SECRET-GEMINI-KEY", serialized)
        self.assertNotIn("sk-SECRET-TOTOKENS-KEY", serialized)
        self.assertEqual(status["default_provider"], "gemini")
        self.assertEqual(len(status["providers"]), 2)
        gemini_entry = next(p for p in status["providers"] if p["key"] == "gemini")
        gemini_ids = [m["id"] for m in gemini_entry["models"]]
        self.assertNotIn("text-embedding-004", gemini_ids)
        self.assertIn("gemini-3.1-flash-image-preview", gemini_ids)

        totokens_entry = next(p for p in status["providers"] if p["key"] == "totokens")
        totokens_ids = [m["id"] for m in totokens_entry["models"]]
        self.assertNotIn("whisper-1", totokens_ids)
        self.assertIn("gpt-image-2", totokens_ids)
        self.assertIn("gemini-3.1-flash-image", totokens_ids)

    def test_resolve_tryon_generation_config_routing_and_strict_no_fallback(self):
        import main

        rich_cfg = {
            "enabled": True,
            "feature_enabled": True,
            "configured": True,
            "provider_key": "gemini",
            "api_key": "AIza-TEST-KEY",
            "base_url": "",
            "timeout_seconds": 60,
            "retry_count": 1,
            "flash_model": "gemini-3.1-flash-image-preview",
            "pro_model": "gemini-3-pro-image-preview",
            "chatgpt_model": "gpt-image-2",
            "relay_enabled": True,
            "relay_configured": True,
            "relay_api_key": "sk-TEST-RELAY",
            "relay_base_url": "https://totokens.cc",
            "providers_internal": {
                "gemini": {
                    "provider_key": "gemini",
                    "enabled": True,
                    "configured": True,
                    "api_key": "AIza-TEST-KEY",
                    "base_url": "",
                    "timeout_seconds": 60,
                    "retry_count": 1,
                    "default_model": "gemini-3.1-flash-image-preview",
                    "models": ["gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview"],
                },
                "totokens": {
                    "provider_key": "totokens",
                    "enabled": True,
                    "configured": True,
                    "api_key": "sk-TEST-RELAY",
                    "base_url": "https://totokens.cc",
                    "timeout_seconds": 120,
                    "retry_count": 1,
                    "default_model": "gpt-image-2",
                    "models": ["gpt-image-2", "gemini-3.1-flash-image"],
                },
            },
        }

        # Switch to ToTokens with Gemini relay model explicitly.
        res_relay_gem = main._resolve_tryon_generation_config(
            "flash",
            provider="totokens",
            model_id="gemini-3.1-flash-image",
            runtime_cfg=rich_cfg,
        )
        self.assertEqual(res_relay_gem["provider_key"], "totokens")
        self.assertEqual(res_relay_gem["model_ids"], ["gemini-3.1-flash-image"])
        self.assertEqual(res_relay_gem["api_key"], "sk-TEST-RELAY")

        # Custom Gemini model ID runs directly on Gemini provider.
        res_custom = main._resolve_tryon_generation_config(
            "pro",
            provider="gemini",
            model_id="gemini-3-pro-image-custom",
            runtime_cfg=rich_cfg,
        )
        self.assertEqual(res_custom["provider_key"], "gemini")
        self.assertEqual(res_custom["model_ids"], ["gemini-3-pro-image-custom"])

        # Mismatched GPT model explicitly on Gemini direct must error cleanly, zero fallback.
        with self.assertRaises(ValueError):
            main._resolve_tryon_generation_config(
                "chatgpt",
                provider="gemini",
                model_id="gpt-image-2",
                runtime_cfg=rich_cfg,
            )

        # Disabled ToTokens provider must NOT silently fall back to Gemini.
        disabled_relay_cfg = json.loads(json.dumps(rich_cfg))
        disabled_relay_cfg["relay_enabled"] = False
        disabled_relay_cfg["relay_configured"] = False
        disabled_relay_cfg["providers_internal"]["totokens"]["enabled"] = False
        disabled_relay_cfg["providers_internal"]["totokens"]["configured"] = False
        with self.assertRaises(RuntimeError):
            main._resolve_tryon_generation_config(
                "chatgpt",
                provider="totokens",
                model_id="gpt-image-2",
                runtime_cfg=disabled_relay_cfg,
            )

    def test_build_direct_generate_config_and_relay_dispatch(self):
        import main

        # Exercise real google.genai.types when available (.venv-local), or stub in minimal CI env.
        injected_stub = False
        try:
            from google.genai import types as _real_types  # noqa: F401
        except ImportError:
            injected_stub = True
            fake_google = types.ModuleType("google")
            fake_genai = types.ModuleType("google.genai")
            fake_types = types.ModuleType("google.genai.types")

            class _SimpleObj:
                def __init__(self, **kwargs):
                    self.__dict__.update(kwargs)

            fake_types.SafetySetting = _SimpleObj
            fake_types.ImageConfig = _SimpleObj
            fake_types.GenerateContentConfig = _SimpleObj
            fake_genai.types = fake_types
            fake_google.genai = fake_genai
            patch_modules = patch.dict(
                sys.modules,
                {"google": fake_google, "google.genai": fake_genai, "google.genai.types": fake_types},
            )
            patch_modules.start()
        else:
            patch_modules = None

        try:
            cfg_pro = main._build_direct_generate_config(
                {"aspect_ratio": "3:4", "image_size": "2K", "temperature": 0.65, "seed": 42},
                model_id="gemini-3-pro-image-preview",
            )
            self.assertEqual(cfg_pro.temperature, 0.65)
            self.assertEqual(cfg_pro.seed, 42)
            self.assertEqual(cfg_pro.image_config.aspect_ratio, "3:4")
            self.assertEqual(cfg_pro.image_config.image_size, "2K")

            # gemini-2.5-flash-image omits image_size when model doesn't support 2K/4K tiers.
            cfg_25 = main._build_direct_generate_config(
                {"aspect_ratio": "1:1", "image_size": "2K"},
                model_id="gemini-2.5-flash-image",
            )
            self.assertEqual(cfg_25.image_config.aspect_ratio, "1:1")
            self.assertIsNone(getattr(cfg_25.image_config, "image_size", None))
        finally:
            if injected_stub and patch_modules is not None:
                patch_modules.stop()

        # Verify _call_ai_studio_image forwards detail_options & model_id to totokens_image.generate_image.
        captured = {}

        async def _fake_generate_image(**kwargs):
            captured.update(kwargs)
            return b"PNG_BYTES"

        resolved_relay = {
            "provider_key": "totokens",
            "api_key": "sk-relay",
            "base_url": "https://totokens.cc",
            "model_ids": ["gpt-image-2"],
            "timeout_seconds": 90,
            "retry_count": 0,
        }
        with (
            patch.object(main, "_resolve_tryon_generation_config", return_value=resolved_relay),
            patch("app.totokens_image.generate_image", side_effect=_fake_generate_image),
        ):
            out = asyncio.run(
                main._call_ai_studio_image(
                    "prompt",
                    "m.jpg",
                    "g.jpg",
                    "chatgpt",
                    provider="totokens",
                    model_id="gpt-image-2",
                    detail_options={"aspect_ratio": "4:5", "quality": "high"},
                )
            )
        self.assertEqual(out, b"PNG_BYTES")
        self.assertEqual(captured["model_id"], "gpt-image-2")
        self.assertEqual(captured["generation_options"], {"aspect_ratio": "4:5", "quality": "high"})

    def test_task_db_migration_and_worker_detail_forwarding(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "legacy_tasks.db"
            db_url = f"sqlite:///{db_path.as_posix()}"

            # Simulate legacy SQLite table created before provider_key/model_id/detail_options_json existed.
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE workbench_generation_tasks (
                    task_id VARCHAR(64) PRIMARY KEY,
                    idempotency_key VARCHAR(192) NOT NULL,
                    access_token_hash VARCHAR(128) NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    message_code VARCHAR(64) NOT NULL DEFAULT 'pending',
                    message TEXT NOT NULL DEFAULT '',
                    progress INTEGER NOT NULL DEFAULT 0,
                    locale VARCHAR(16) NOT NULL DEFAULT 'zh-CN',
                    model_key VARCHAR(32) NOT NULL DEFAULT 'flash',
                    freedom INTEGER NOT NULL DEFAULT 5,
                    garment_type VARCHAR(64) NOT NULL DEFAULT '',
                    custom_prompt TEXT NOT NULL DEFAULT '',
                    prompt_mode VARCHAR(32) NOT NULL DEFAULT 'append',
                    target_filename VARCHAR(255) NOT NULL DEFAULT '',
                    reference_filename VARCHAR(255) NOT NULL DEFAULT '',
                    input_target_blob VARCHAR(500),
                    input_reference_blob VARCHAR(500),
                    output_result_blob VARCHAR(500),
                    result_filename VARCHAR(255),
                    error_code VARCHAR(128),
                    error_detail TEXT,
                    logs_json TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    lease_owner VARCHAR(128),
                    lease_expires_at FLOAT,
                    upstream_status VARCHAR(32),
                    upstream_started_at FLOAT,
                    upstream_completed_at FLOAT,
                    created_at FLOAT NOT NULL DEFAULT 0,
                    updated_at FLOAT NOT NULL DEFAULT 0
                )
                """
            )
            conn.commit()
            conn.close()

            task_db.reset_engine_cache()
            try:
                task_db.ensure_task_tables(db_url=db_url)
                conn = sqlite3.connect(db_path)
                cols = {row[1] for row in conn.execute("PRAGMA table_info(workbench_generation_tasks)").fetchall()}
                conn.close()
                self.assertTrue({"provider_key", "model_id", "detail_options_json"}.issubset(cols))

                created, is_new = task_db.create_or_get_task(
                    task_id="task_tryon_01",
                    idempotency_key="idem_01",
                    access_token_hash="hash_01",
                    locale="zh-CN",
                    model_key="pro",
                    freedom=6,
                    garment_type="top",
                    custom_prompt="",
                    prompt_mode="append",
                    target_filename="target.jpg",
                    reference_filename="garment.jpg",
                    provider_key="gemini",
                    model_id="gemini-3-pro-image-preview",
                    detail_options={"aspect_ratio": "3:4", "image_size": "2K", "seed": 777},
                    db_url=db_url,
                )
                self.assertTrue(is_new)
                self.assertEqual(created["provider_key"], "gemini")
                self.assertEqual(created["model_id"], "gemini-3-pro-image-preview")
                self.assertEqual(created["detail_options"], {"aspect_ratio": "3:4", "image_size": "2K", "seed": 777})

                # Prepare dummy image inputs and test queue_worker forwards provider/model_id/detail_options.
                tiny_png = _make_tiny_png()
                target_file = Path(tmpdir) / "target.jpg"
                garment_file = Path(tmpdir) / "garment.jpg"
                target_file.write_bytes(tiny_png)
                garment_file.write_bytes(tiny_png)

                worker_calls = {}

                async def _fake_generate(
                    prompt,
                    model_path,
                    garment_path,
                    model_key,
                    *,
                    provider=None,
                    model_id=None,
                    detail_options=None,
                ):
                    worker_calls.update(
                        {
                            "model_key": model_key,
                            "provider": provider,
                            "model_id": model_id,
                            "detail_options": detail_options,
                        }
                    )
                    return tiny_png

                fake_queue = _FakeQueue()
                with (
                    patch.dict(os.environ, {"UPLOAD_DIR": tmpdir, "ASSET_DIR": tmpdir}),
                    patch("app.object_storage.get_object_storage", return_value=None),
                ):
                    import main as workbench_main

                    with (
                        patch.object(workbench_main, "UPLOAD_DIR", tmpdir),
                        patch.object(workbench_main, "ASSET_DIR", tmpdir),
                        patch.object(workbench_main, "_record_key_usage"),
                    ):
                        result = asyncio.run(
                            process_queue_message(
                                QueueMessage("msg1", "pop1", "task_tryon_01"),
                                worker_id="worker-test",
                                task_queue=fake_queue,
                                object_storage=None,
                                db_url=db_url,
                                generate_fn=_fake_generate,
                                runtime_config_fn=lambda: {
                                    "enabled": True,
                                    "provider_key": "gemini",
                                    "configured": True,
                                    "api_key": "AIza-test",
                                    "timeout_seconds": 60,
                                },
                            )
                        )
                self.assertEqual(result["status"], "completed", msg=repr(result))
                self.assertEqual(fake_queue.deleted, ["task_tryon_01"])
                self.assertEqual(worker_calls["provider"], "gemini")
                self.assertEqual(worker_calls["model_id"], "gemini-3-pro-image-preview")
                self.assertEqual(
                    worker_calls["detail_options"],
                    {"aspect_ratio": "3:4", "image_size": "2K", "seed": 777},
                )
            finally:
                task_db.reset_engine_cache()

    def test_submit_task_and_rate_status_validation(self):
        import main

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "sample_model.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 64)
            (Path(tmpdir) / "sample_garment.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 64)
            with (
                patch.object(main, "UPLOAD_DIR", tmpdir),
                TestClient(main.app) as client,
            ):
                res_bad_model = client.post(
                    "/submit-task",
                    data={
                        "target_image": "sample_model.jpg",
                        "reference_image": "sample_garment.jpg",
                        "provider": "gemini",
                        "model_id": "../bad-model",
                    },
                )
                self.assertEqual(res_bad_model.status_code, 400)

                res_bad_provider = client.post(
                    "/submit-task",
                    data={
                        "target_image": "sample_model.jpg",
                        "reference_image": "sample_garment.jpg",
                        "provider": "invalid-provider",
                        "model_id": "gemini-3.1-flash-image-preview",
                    },
                )
                self.assertEqual(res_bad_provider.status_code, 400)

                res_rate_ok = client.get(
                    "/api/rate-status",
                    params={
                        "model": "chatgpt",
                        "provider": "totokens",
                        "model_id": "gemini-3.1-flash-image",
                    },
                )
                self.assertEqual(res_rate_ok.status_code, 200)
                self.assertEqual(res_rate_ok.json()["model_name"], "gemini-3.1-flash-image")

                res_rate_bad = client.get(
                    "/api/rate-status",
                    params={
                        "model": "flash",
                        "model_id": "gpt?inject=1",
                    },
                )
                self.assertEqual(res_rate_bad.status_code, 400)

    def test_gpt_image_2_resolution_dimensions_and_profile_validation(self):
        from app.tryon_options import map_aspect_ratio_to_openai_size

        self.assertIsNone(map_aspect_ratio_to_openai_size("auto"))
        self.assertEqual(map_aspect_ratio_to_openai_size("3:4"), "1024x1536")
        self.assertEqual(map_aspect_ratio_to_openai_size("3:4", image_size="2K"), "1536x2048")
        self.assertEqual(map_aspect_ratio_to_openai_size("3:4", image_size="4K"), "2400x3200")
        self.assertEqual(map_aspect_ratio_to_openai_size("auto", image_size="2K"), "2048x2048")
        self.assertEqual(map_aspect_ratio_to_openai_size("auto", image_size="4K"), "2880x2880")
        for ratio in ("1:1", "2:3", "3:4", "4:5", "9:16", "3:2", "4:3", "5:4", "16:9", "21:9"):
            for tier in ("2K", "4K"):
                dim = map_aspect_ratio_to_openai_size(ratio, image_size=tier)
                w, h = (int(v) for v in dim.split("x"))
                self.assertEqual(w % 16, 0, msg=f"{dim} width not multiple of 16")
                self.assertEqual(h % 16, 0, msg=f"{dim} height not multiple of 16")
                self.assertLessEqual(max(w, h), 3840)
                self.assertLessEqual(w * h, 8294400)

    def test_three_locale_tryon_and_new_runtime_keys_parity(self):
        zh = _load_locale("zh-CN")
        en = _load_locale("en")
        ja = _load_locale("ja")

        self.assertEqual(set(zh["tryon"].keys()), set(en["tryon"].keys()))
        self.assertEqual(set(zh["tryon"].keys()), set(ja["tryon"].keys()))
        self.assertEqual(set(zh["runtime"].keys()), set(en["runtime"].keys()))
        self.assertEqual(set(zh["runtime"].keys()), set(ja["runtime"].keys()))
        for key, value in zh["tryon"].items():
            self.assertTrue(str(value).strip(), f"zh-CN tryon.{key} is empty")
            self.assertTrue(str(en["tryon"][key]).strip(), f"en tryon.{key} is empty")
            self.assertTrue(str(ja["tryon"][key]).strip(), f"ja tryon.{key} is empty")
