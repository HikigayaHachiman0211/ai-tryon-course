from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import Request

from app.database import AIAPIProvider, AIFeatureConfig, Base, PromptConfig, _seed_ai_configs, _seed_prompts


def test_existing_models_migrate_on_startup_without_overwriting_admin_settings():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            AIAPIProvider(provider_key="mimo", display_name="Custom", category="multi", enabled=False,
                          default_model="mimo-v2.5-pro", model_options=["mimo-v2.5", "mimo-v2.5-pro", "mimo-v2-omni", "my-model"],
                          api_key_encrypted="keep-encrypted", updated_by="admin"),
            AIAPIProvider(provider_key="mimo_asr", display_name="ASR", category="asr", default_model="mimo-v2.5-asr"),
            AIFeatureConfig(feature_key="recommendation", default_provider="mimo", default_model="mimo-v2.5", enabled=False, updated_by="admin"),
            AIFeatureConfig(feature_key="vision_analysis", default_provider="mimo", default_model="custom-vision", updated_by="admin"),
            AIFeatureConfig(feature_key="voice_asr", default_provider="mimo_asr", default_model="mimo-v2.5-asr"),
            PromptConfig(name="custom_prompt", locale="zh-CN", display_name="Custom", content="admin content",
                         default_content="admin default", model_name="mimo-v2.5-pro", updated_by="admin"),
        ])
        session.commit()

        _seed_prompts(session)
        _seed_ai_configs(session)
        _seed_ai_configs(session)  # The migration must be repeatable.

        provider = session.query(AIAPIProvider).filter_by(provider_key="mimo").one()
        assert provider.default_model == "mimo-v2.6-pro"
        assert provider.model_options == ["mimo-v2.6-flash", "mimo-v2.6-pro", "my-model"]
        assert provider.display_name == "Custom" and provider.enabled is False
        assert provider.api_key_encrypted == "keep-encrypted" and provider.updated_by == "admin"
        assert session.query(AIAPIProvider).filter_by(provider_key="mimo_asr").one().default_model == "mimo-v2.5-asr"
        assert session.query(AIFeatureConfig).filter_by(feature_key="recommendation").one().default_model == "mimo-v2.6-flash"
        assert session.query(AIFeatureConfig).filter_by(feature_key="vision_analysis").one().default_model == "custom-vision"
        assert session.query(AIFeatureConfig).filter_by(feature_key="voice_asr").one().default_model == "mimo-v2.5-asr"
        prompt = session.query(PromptConfig).filter_by(name="custom_prompt").one()
        assert prompt.model_name == "mimo-v2.6-pro"
        assert prompt.content == "admin content" and prompt.default_content == "admin default"
        assert session.query(PromptConfig).filter_by(name="mimo_image_profile_analysis", locale="zh-CN").one().model_name == "mimo-v2.6-flash"


def test_new_install_uses_v26_defaults():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_ai_configs(session)
        provider = session.query(AIAPIProvider).filter_by(provider_key="mimo").one()
        assert provider.default_model == "mimo-v2.6-flash"
        assert provider.model_options == ["mimo-v2.6-flash", "mimo-v2.6-pro", "mimo-v2.6-pro-ultraspeed"]
        assert session.query(AIFeatureConfig).filter_by(feature_key="assistant_chat").one().default_model == "mimo-v2.6-flash"


def test_admin_provider_and_prompt_tests_send_supported_mimo_requests():
    from app.routers.ai_config import test_provider
    from app.routers.prompts import PromptTestRequest, test_prompt

    sent = []

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            sent.append(kwargs["json"])
            return SimpleNamespace(status_code=200, json=lambda: {"choices": [{"message": {"content": "ok"}}]})

    def run_without_io(coro):
        try:
            coro.send(None)
        except StopIteration as exc:
            return exc.value
        raise AssertionError("Unexpected asynchronous I/O")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        provider = AIAPIProvider(provider_key="mimo", display_name="MiMo", category="multi", enabled=True,
                                 default_model="mimo-v2.5", base_url="https://api.xiaomimimo.com/v1",
                                 api_key_encrypted="encrypted", auth_type="api_key_header")
        prompt = PromptConfig(name="test", locale="zh-CN", display_name="Test", content="Hello",
                              model_name="mimo-v2.5-pro", temperature=0.2)
        session.add_all([provider, prompt])
        session.commit()
        admin = SimpleNamespace(username="admin")
        request = Request({"type": "http", "headers": [], "query_string": b""})
        with patch("app.routers.ai_config.decrypt_secret", return_value="test-key"), \
             patch("app.services.secret_crypto.decrypt_secret", return_value="test-key"), \
             patch("httpx.AsyncClient", FakeClient):
            assert run_without_io(test_provider(provider.id, admin=admin, db=session))["success"]
            assert run_without_io(test_prompt(prompt.id, PromptTestRequest(), request, admin=admin, db=session))["success"]

    assert sent[0]["model"] == "mimo-v2.6-flash"
    assert sent[0]["thinking"] == {"type": "disabled"}
    assert sent[0]["max_completion_tokens"] >= 32
    assert "max_tokens" not in sent[0]
    assert sent[1]["model"] == "mimo-v2.6-pro"
    assert sent[1]["max_completion_tokens"] == 4096
