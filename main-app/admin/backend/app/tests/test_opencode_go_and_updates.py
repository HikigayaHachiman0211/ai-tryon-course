"""Tests for Admin OpenCode Go integration, DeepSeek/Gemini migrations, and live sync/test."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import AIAPIProvider, AIFeatureConfig, Base, PromptConfig, _seed_ai_configs, _seed_prompts
from app.opencode_go import OPENCODE_GO_MODELS
from app.routers.ai_config import sync_provider_models, test_provider as run_provider_test
from app.routers.prompts import PromptTestRequest, test_prompt as run_prompt_test
from app.services.secret_crypto import encrypt_secret


def _test_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [],
        "query_string": b"",
    }
    return Request(scope)


def test_seed_and_migration_for_opencode_go_deepseek_and_gemini():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            AIAPIProvider(
                provider_key="deepseek",
                display_name="Deepseek",
                category="llm",
                enabled=True,
                base_url="https://api.deepseek.com",
                default_model="deepseek-v4-flash",
                model_options=["deepseek-v4-flash", "deepseek-chat", "deepseek-reasoner"],
                updated_by="admin",
            ),
            AIAPIProvider(
                provider_key="gemini",
                display_name="Google Gemini / AI Studio",
                category="multi",
                enabled=True,
                base_url="https://generativelanguage.googleapis.com",
                default_model="gemini-3.1-flash-lite-preview",
                model_options=["gemini-3.1-flash-lite-preview", "my-custom-gemini"],
                api_key_encrypted="keep-gemini-key",
                updated_by="admin",
            ),
            AIFeatureConfig(
                feature_key="recommendation",
                enabled=True,
                default_provider="mimo",
                fallback_order=["mimo", "gemini", "deepseek", "rule"],
                updated_by="system",
            ),
            AIFeatureConfig(
                feature_key="vision_analysis",
                enabled=True,
                default_provider="mimo",
                fallback_order=["mimo", "gemini"],
                updated_by="system",
            ),
            PromptConfig(
                name="deepseek_text_profile_analysis",
                locale="zh-CN",
                display_name="DeepSeek",
                content="prompt",
                default_content="prompt",
                model_name="deepseek-v4-flash",
                updated_by="system",
            ),
        ])
        session.commit()

        _seed_prompts(session)
        _seed_ai_configs(session)
        _seed_ai_configs(session)

        go_provider = session.query(AIAPIProvider).filter_by(provider_key="opencode_go").one()
        assert go_provider.category == "multi"
        assert go_provider.default_model == "deepseek-v4.1-flash"
        assert go_provider.base_url == "https://opencode.ai/inference/go"
        assert list(go_provider.model_options or []) == list(OPENCODE_GO_MODELS)

        ds_provider = session.query(AIAPIProvider).filter_by(provider_key="deepseek").one()
        assert ds_provider.category == "multi"
        assert ds_provider.default_model == "deepseek-flash"
        assert ds_provider.model_options == ["deepseek-flash", "deepseek-v4-pro"]

        gem_provider = session.query(AIAPIProvider).filter_by(provider_key="gemini").one()
        assert gem_provider.api_key_encrypted == "keep-gemini-key"
        assert "my-custom-gemini" in (gem_provider.model_options or [])
        assert "gemini-4-argon" in (gem_provider.model_options or [])
        assert "gemini-3.8-flash" in (gem_provider.model_options or [])

        rec_feat = session.query(AIFeatureConfig).filter_by(feature_key="recommendation").one()
        vis_feat = session.query(AIFeatureConfig).filter_by(feature_key="vision_analysis").one()
        assert rec_feat.fallback_order == ["mimo", "gemini", "deepseek", "opencode_go", "rule"]
        assert vis_feat.fallback_order == ["mimo", "gemini", "deepseek", "opencode_go"]

        ds_prompt = session.query(PromptConfig).filter_by(name="deepseek_text_profile_analysis", locale="zh-CN").one()
        assert ds_prompt.model_name == "deepseek-flash"


def test_admin_opencode_go_connection_test_sync_and_prompt_test():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    admin = SimpleNamespace(username="admin")
    with Session(engine) as session:
        _seed_prompts(session)
        _seed_ai_configs(session)
        go_provider = session.query(AIAPIProvider).filter_by(provider_key="opencode_go").one()
        go_provider.api_key_encrypted = encrypt_secret("go-admin-secret")
        go_provider.default_model = "gpt-6-luna"

        prompt = PromptConfig(
            name="opencode_test_prompt",
            locale="zh-CN",
            display_name="Go Prompt",
            content="Hello {user}",
            default_content="Hello {user}",
            model_name="claude-haiku-5-5",
            updated_by="admin",
        )
        session.add(prompt)
        session.commit()
        session.refresh(go_provider)
        session.refresh(prompt)

        called_urls: list[str] = []

        def make_async_client(status_code=200, json_body=None):
            client = AsyncMock()
            resp = MagicMock()
            resp.status_code = status_code
            resp.text = "ok"
            resp.json.return_value = json_body or {}

            async def _post(url, headers=None, json=None):
                called_urls.append(url)
                return resp

            async def _get(url, headers=None):
                called_urls.append(url)
                return resp

            client.__aenter__.return_value = client
            client.post = _post
            client.get = _get
            return client

        # 1. Test connection uses Responses endpoint for gpt-6-luna
        with patch("app.opencode_go.httpx.AsyncClient", return_value=make_async_client(200, {"output_text": "pong"})):
            res = asyncio.run(run_provider_test(go_provider.id, admin=admin, db=session))
        assert res["success"] is True
        assert "responses" in res["message"]
        assert called_urls[-1] == "https://opencode.ai/inference/go/openai/v1/responses"

        # 2. Sync models merges newly discovered Go models
        sync_body = {"data": [{"id": "deepseek-v4.1-flash"}, {"id": "future-new-model"}]}
        with patch("app.routers.ai_config.httpx.AsyncClient", return_value=make_async_client(200, sync_body)):
            synced = asyncio.run(sync_provider_models(go_provider.id, admin=admin, db=session))
        assert synced["synced_count"] == 2
        assert "future-new-model" in synced["model_options"]

        # 3. Prompt test dispatches Anthropic Messages endpoint for claude-haiku-5-5 via OpenCode Go
        with patch("app.routers.prompts.httpx.AsyncClient", return_value=make_async_client(200, {})), \
             patch("app.opencode_go.httpx.AsyncClient", return_value=make_async_client(200, {"content": [{"type": "text", "text": "Hi there"}]})):
            prompt_res = asyncio.run(
                run_prompt_test(prompt.id, PromptTestRequest(test_params={"user": "Alice"}), _test_request(), admin=admin, db=session)
            )
        assert prompt_res["success"] is True
        assert prompt_res["output"] == "Hi there"
        assert called_urls[-1] == "https://opencode.ai/inference/go/anthropic/v1/messages"


def test_sync_models_for_totokens_and_deepseek_with_and_without_key():
    from app.main import localized_http_exception
    from fastapi import HTTPException

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    admin = SimpleNamespace(username="admin")
    with Session(engine) as session:
        _seed_ai_configs(session)
        totokens = session.query(AIAPIProvider).filter_by(provider_key="totokens").one()
        deepseek = session.query(AIAPIProvider).filter_by(provider_key="deepseek").one()
        totokens.model_options = ["custom-relay-model"]
        session.commit()

        # 1. Without API key: ToTokens & DeepSeek sync built-in curated catalogs cleanly
        t_res = asyncio.run(sync_provider_models(totokens.id, admin=admin, db=session))
        assert t_res["source"] == "builtin"
        assert "gemini-3.1-flash-image" in t_res["model_options"]
        assert "gpt-image-2" in t_res["model_options"]
        assert "custom-relay-model" in t_res["model_options"]

        d_res = asyncio.run(sync_provider_models(deepseek.id, admin=admin, db=session))
        assert d_res["source"] == "builtin"
        assert d_res["model_options"] == ["deepseek-flash", "deepseek-v4-pro"]

        # 2. With API key: ToTokens strips /v1/images/edits suffix and fetches /v1/models
        totokens.api_key_encrypted = encrypt_secret("totokens-key")
        totokens.base_url = "https://totokens.cc/v1/images/edits"
        deepseek.api_key_encrypted = encrypt_secret("deepseek-key")
        session.commit()

        called: list[str] = []

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, url, headers=None):
                called.append(url)
                if "totokens.cc" in url:
                    return SimpleNamespace(
                        status_code=200,
                        text="ok",
                        json=lambda: {"data": [{"id": "gpt-image-2"}, {"id": "gemini-3.1-flash-image"}]},
                    )
                if url.endswith("/v1/models"):
                    return SimpleNamespace(status_code=404, text="not found", json=lambda: {})
                return SimpleNamespace(
                    status_code=200,
                    text="ok",
                    json=lambda: {"data": [{"id": "deepseek-flash"}, {"id": "deepseek-v4-pro"}]},
                )

        with patch("app.routers.ai_config.httpx.AsyncClient", FakeClient):
            t_live = asyncio.run(sync_provider_models(totokens.id, admin=admin, db=session))
            d_live = asyncio.run(sync_provider_models(deepseek.id, admin=admin, db=session))

        assert t_live["source"] == "remote"
        assert t_live["synced_count"] == 2
        assert called[0] == "https://totokens.cc/v1/models"

        assert d_live["source"] == "remote"
        assert d_live["synced_count"] == 2
        assert called[1:] == ["https://api.deepseek.com/v1/models", "https://api.deepseek.com/models"]

        # 3. 400 HTTPException string detail is preserved rather than masked as UNKNOWN_ERROR
        req = _test_request()
        req.state.locale = "zh-CN"
        req.state.request_id = "req-1"
        resp = asyncio.run(localized_http_exception(req, HTTPException(400, detail="拉取模型列表失败: HTTP 401")))
        assert resp.status_code == 400
        assert b"HTTP 401" in resp.body
