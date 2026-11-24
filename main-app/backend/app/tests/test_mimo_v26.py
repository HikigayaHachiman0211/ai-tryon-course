from unittest.mock import patch

import httpx
import pytest

from app.ai_runtime_config import resolve_provider_config
from app.assistant.config import get_public_config
from app.assistant.rule_extractor import extract_recommend_fields, sanitize_recommend_fields
from app.profile_providers import call_mimo_profile
from app.tests.test_provider_config_contract import _make_engine


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("mimo-v2.5", "mimo-v2.6-flash"),
        ("mimo-v2.5-pro", "mimo-v2.6-pro"),
        ("mimo-v2-omni", "mimo-v2.6-flash"),
        ("mimo-v2-flash", "mimo-v2.6-flash"),
        ("mimo-v2-pro", "mimo-v2.6-pro"),
    ],
)
def test_retired_model_in_database_and_request_is_mapped(old, new):
    engine = _make_engine(providers=[{"provider_key": "mimo", "default_model": old}])
    with patch("app.ai_runtime_config._get_engine", return_value=engine):
        assert resolve_provider_config("mimo", request_api_key="test")["default_model"] == new
        assert resolve_provider_config("mimo", request_api_key="test", request_model=old)["default_model"] == new


def test_default_and_other_provider_models_are_preserved(monkeypatch):
    monkeypatch.delenv("MIMO_MODEL", raising=False)
    engine = _make_engine(providers=[])
    with patch("app.ai_runtime_config._get_engine", return_value=engine):
        assert resolve_provider_config("mimo", request_api_key="test")["default_model"] == "mimo-v2.6-flash"
        assert resolve_provider_config("mimo", request_api_key="test", request_model="custom-model")["default_model"] == "custom-model"
        assert resolve_provider_config("mimo_asr", request_api_key="test")["default_model"] == "mimo-v2.5-asr"
        assert resolve_provider_config("mimo_tts", request_api_key="test")["default_model"] == "mimo-v2.5-tts"


def test_environment_model_is_used_only_when_admin_has_no_model(monkeypatch):
    monkeypatch.setenv("MIMO_MODEL", "mimo-v2.5-pro")
    engine = _make_engine(providers=[])
    with patch("app.ai_runtime_config._get_engine", return_value=engine):
        assert resolve_provider_config("mimo", request_api_key="test")["default_model"] == "mimo-v2.6-pro"
        assert resolve_provider_config("mimo", request_api_key="test", request_model="mimo-v2.6-flash")["default_model"] == "mimo-v2.6-flash"
    engine = _make_engine(providers=[{"provider_key": "mimo", "default_model": "mimo-v2.6-flash"}])
    with patch("app.ai_runtime_config._get_engine", return_value=engine):
        assert resolve_provider_config("mimo", request_api_key="test")["default_model"] == "mimo-v2.6-flash"


@pytest.mark.parametrize("model", ["mimo-v2.6-flash", "mimo-v2.6-pro", "mimo-v2.6-pro-ultraspeed"])
def test_image_request_uses_selected_v26_model(model):
    response = httpx.Response(200, json={"choices": [{"message": {"content": '{"body_shape":"标准"}'}}]})
    response.request = httpx.Request("POST", "https://api.xiaomimimo.com/v1/chat/completions")
    with patch("app.profile_providers.httpx.post", return_value=response) as post:
        result = call_mimo_profile(
            api_key="test", gender=None, mbti=None, color_preference="黑色",
            size=None, style_preference=None, model=model, image_bytes=b"image",
            mime_type="image/jpeg", prompt_override="Return JSON",
        )
    payload = post.call_args.kwargs["json"]
    assert payload["model"] == model
    assert payload["max_completion_tokens"] == 4096
    assert payload["messages"][1]["content"][0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert result["body_shape"] == "标准"


def test_assistant_defaults_and_explicit_mimo_selection_use_flash():
    assert get_public_config().defaults["mimo_model"] == "mimo-v2.6-flash"
    assert extract_recommend_fields("请用小米分析")['mimo_model'] == "mimo-v2.6-flash"


@pytest.mark.parametrize("model", ["mimo-v2.6-pro", "mimo-v2.6-pro-ultraspeed"])
@pytest.mark.parametrize("message_template", ["请用 {} 分析", "请用{}分析"])
def test_assistant_keeps_explicit_model_choice(model, message_template):
    message = message_template.format(model)
    patch_fields = sanitize_recommend_fields(message, extract_recommend_fields(message))
    assert patch_fields["mimo_model"] == model
