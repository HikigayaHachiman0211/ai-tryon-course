"""Tests for OpenCode Go multi-protocol support and DeepSeek V4.1 Flash multimodal updates."""
from __future__ import annotations

import asyncio
import base64
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy import create_engine, text

from app.ai_runtime_config import resolve_effective_provider, resolve_provider_config
from app.assistant.llm_clients import try_llm_enhance
from app.assistant.rule_extractor import extract_recommend_fields
from app.deepseek_models import (
    DEFAULT_DEEPSEEK_MODEL,
    is_deepseek_vision_capable,
    normalize_deepseek_model,
)
from app.opencode_go import (
    DEFAULT_OPENCODE_GO_BASE_URL,
    DEFAULT_OPENCODE_GO_MODEL,
    OPENCODE_GO_MODELS,
    build_opencode_go_headers,
    build_opencode_go_payload,
    detect_opencode_go_protocol,
    extract_opencode_go_text,
    is_opencode_go_vision_capable,
    normalize_opencode_go_root,
    resolve_opencode_go_endpoint,
)
from app.profile_inference import resolve_user_profile
from app.profile_providers import call_deepseek_profile, normalize_vision_provider


def _make_engine(providers=None, features=None):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE ai_api_providers (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_key     TEXT UNIQUE NOT NULL,
                display_name     TEXT DEFAULT '',
                category         TEXT DEFAULT 'multi',
                enabled          INTEGER DEFAULT 1,
                is_default       INTEGER DEFAULT 0,
                base_url         TEXT DEFAULT '',
                api_key_encrypted TEXT,
                auth_type        TEXT DEFAULT 'bearer',
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
                    "at": p.get("auth_type", "bearer"),
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


def test_opencode_go_root_normalization_and_protocol_detection():
    assert normalize_opencode_go_root(None) == DEFAULT_OPENCODE_GO_BASE_URL
    assert normalize_opencode_go_root("https://opencode.ai/inference/go/v1") == "https://opencode.ai/inference/go"
    assert normalize_opencode_go_root("https://opencode.ai/inference/go/openai/v1") == "https://opencode.ai/inference/go"
    assert normalize_opencode_go_root("https://opencode.ai/inference/go/anthropic/v1") == "https://opencode.ai/inference/go"
    assert normalize_opencode_go_root("https://opencode.ai/zen/go/v1") == "https://opencode.ai/zen/go"

    assert len(OPENCODE_GO_MODELS) == 32
    assert detect_opencode_go_protocol("deepseek-v4.1-flash") == "chat-completions"
    assert detect_opencode_go_protocol("gpt-6-luna") == "responses"
    assert detect_opencode_go_protocol("grok-4.7") == "responses"
    assert detect_opencode_go_protocol("muse-spark-1.3-contributor") == "responses"
    assert detect_opencode_go_protocol("claude-haiku-5-5") == "messages"
    assert detect_opencode_go_protocol("qwen3.8-max") == "messages"
    assert detect_opencode_go_protocol("minimax-m3") == "messages"
    assert detect_opencode_go_protocol("minimax-m3.1-flash") == "chat-completions"
    assert detect_opencode_go_protocol("gemini-4-argon") == "generate-content"


def test_opencode_go_endpoints_headers_payloads_and_response_extractors():
    img = b"\x89PNG-fake-image"
    b64 = base64.b64encode(img).decode("utf-8")

    # 1. chat-completions
    assert resolve_opencode_go_endpoint("https://opencode.ai/inference/go/v1", "chat-completions", "deepseek-v4.1-flash") == (
        "https://opencode.ai/inference/go/openai/v1/chat/completions"
    )
    cc_payload = build_opencode_go_payload(
        model="deepseek-v4.1-flash",
        protocol="chat-completions",
        messages=[{"role": "user", "content": "hi"}],
        system_prompt="sys",
        image_bytes=img,
        mime_type="image/png",
        json_mode=True,
    )
    assert cc_payload["messages"][0] == {"role": "system", "content": "sys"}
    assert cc_payload["messages"][1]["content"][0]["image_url"]["url"] == f"data:image/png;base64,{b64}"
    assert cc_payload["response_format"] == {"type": "json_object"}
    assert extract_opencode_go_text("chat-completions", {"choices": [{"message": {"content": '{"ok":true}'}}]}) == '{"ok":true}'

    # 2. responses
    assert resolve_opencode_go_endpoint("https://opencode.ai/inference/go", "responses", "gpt-6-luna") == (
        "https://opencode.ai/inference/go/openai/v1/responses"
    )
    resp_payload = build_opencode_go_payload(
        model="gpt-6-luna",
        protocol="responses",
        messages=[{"role": "user", "content": "analyze"}],
        system_prompt="sys",
        image_bytes=img,
        mime_type="image/jpeg",
    )
    assert resp_payload["instructions"] == "sys"
    assert resp_payload["input"][0]["content"][0]["type"] == "input_image"
    assert extract_opencode_go_text("responses", {"output": [{"type": "message", "content": [{"type": "output_text", "text": "hello"}]}]}) == "hello"

    # 3. messages (Anthropic)
    assert resolve_opencode_go_endpoint("https://opencode.ai/inference/go", "messages", "claude-haiku-5-5") == (
        "https://opencode.ai/inference/go/anthropic/v1/messages"
    )
    msg_headers = build_opencode_go_headers("go-secret", "messages", session_id="sess-42")
    assert msg_headers["Authorization"] == "Bearer go-secret"
    assert msg_headers["x-api-key"] == "go-secret"
    assert msg_headers["anthropic-version"] == "2023-06-01"
    assert msg_headers["x-opencode-session"] == "sess-42"
    msg_payload = build_opencode_go_payload(
        model="claude-haiku-5-5",
        protocol="messages",
        messages=[{"role": "user", "content": "look"}],
        system_prompt="sys",
        image_bytes=img,
        mime_type="image/png",
    )
    assert msg_payload["messages"][0]["content"][0]["source"]["data"] == b64
    assert extract_opencode_go_text("messages", {"content": [{"type": "text", "text": "ok-claude"}]}) == "ok-claude"

    # 4. generate-content (Gemini)
    assert resolve_opencode_go_endpoint("https://opencode.ai/inference/go", "generate-content", "gemini-4-argon") == (
        "https://opencode.ai/inference/go/google/v1beta/models/gemini-4-argon:generateContent"
    )
    gem_headers = build_opencode_go_headers("go-secret", "generate-content")
    assert gem_headers["x-goog-api-key"] == "go-secret"
    gem_payload = build_opencode_go_payload(
        model="gemini-4-argon",
        protocol="generate-content",
        messages=[{"role": "user", "content": "look"}],
        system_prompt="sys",
        image_bytes=img,
        mime_type="image/webp",
        json_mode=True,
    )
    assert gem_payload["systemInstruction"]["parts"][0]["text"] == "sys"
    assert gem_payload["contents"][0]["parts"][1]["inline_data"]["data"] == b64
    assert gem_payload["generationConfig"]["responseMimeType"] == "application/json"
    assert extract_opencode_go_text(
        "generate-content",
        {"candidates": [{"content": {"parts": [{"text": "thought", "thought": True}, {"text": "final"}]}}]},
    ) == "final"


def test_deepseek_v41_flash_normalization_and_vision_guard():
    assert normalize_deepseek_model("deepseek-chat") == DEFAULT_DEEPSEEK_MODEL
    assert normalize_deepseek_model("deepseek-reasoner") == DEFAULT_DEEPSEEK_MODEL
    assert normalize_deepseek_model("deepseek-v4-flash") == DEFAULT_DEEPSEEK_MODEL
    assert normalize_deepseek_model("deepseek-v4-flash-vision-exp") == DEFAULT_DEEPSEEK_MODEL
    assert normalize_deepseek_model("deepseek-v4-pro") == "deepseek-v4-pro"
    assert is_deepseek_vision_capable("deepseek-flash") is True
    assert is_deepseek_vision_capable("deepseek-v4-pro") is False

    engine = _make_engine(providers=[
        {"provider_key": "deepseek", "enabled": True, "default_model": "deepseek-v4-pro"},
        {"provider_key": "opencode_go", "enabled": True, "default_model": "beam-free"},
    ])
    with patch("app.ai_runtime_config._get_engine", return_value=engine), \
         patch.dict("os.environ", {"DEEPSEEK_API_KEY": "ds-k", "OPENCODE_GO_API_KEY": "go-k"}):
        ds_vis = resolve_provider_config("deepseek", feature_key="vision_analysis")
        ds_txt = resolve_provider_config("deepseek", feature_key="recommendation")
        go_vis = resolve_provider_config("opencode_go", feature_key="vision_analysis")
        go_txt = resolve_provider_config("opencode_go", feature_key="recommendation")

    assert ds_vis["default_model"] == "deepseek-flash"
    assert ds_txt["default_model"] == "deepseek-v4-pro"
    assert is_opencode_go_vision_capable("beam-free") is False
    assert go_vis["default_model"] == DEFAULT_OPENCODE_GO_MODEL
    assert go_txt["default_model"] == "beam-free"


def test_call_deepseek_profile_multimodal_and_opencode_go_profile_inference():
    captured: list[dict] = []

    def fake_post(url, *, headers=None, json=None, timeout=None):
        captured.append({"url": url, "headers": headers, "json": json})
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"recommended_size":"L","body_shape":"标准","suggested_style":"短款","reasoning":"身形匀称推荐L码短款"}'
                }
            }]
        }
        return resp

    with patch("httpx.post", side_effect=fake_post):
        out = call_deepseek_profile(
            api_key="ds-test",
            gender="male",
            mbti=None,
            color_preference="黑色",
            size=None,
            style_preference=None,
            model="deepseek-v4-pro",
            image_bytes=b"img-bytes",
            mime_type="image/png",
        )
    assert out is not None and out["recommended_size"] == "L"
    assert captured[0]["json"]["model"] == "deepseek-flash"
    assert captured[0]["json"]["messages"][1]["content"][0]["type"] == "image_url"

    assert normalize_vision_provider("deepseek") == "deepseek"
    assert normalize_vision_provider("opencode_go") == "opencode_go"

    engine = _make_engine(
        providers=[
            {"provider_key": "deepseek", "enabled": True, "default_model": "deepseek-flash", "base_url": "https://api.deepseek.com"},
            {"provider_key": "opencode_go", "enabled": True, "default_model": "claude-haiku-5-5", "base_url": "https://opencode.ai/inference/go"},
        ],
        features=[
            {"feature_key": "recommendation", "enabled": True, "default_provider": "mimo", "fallback_order": ["mimo", "gemini", "deepseek", "opencode_go", "rule"]},
            {"feature_key": "vision_analysis", "enabled": True, "default_provider": "mimo", "fallback_order": ["mimo", "gemini", "deepseek", "opencode_go"]},
        ],
    )

    go_captured: list[str] = []

    def fake_go_post(url, *, headers=None, json=None, timeout=None):
        go_captured.append(url)
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.json.return_value = {
            "content": [{"type": "text", "text": '{"recommended_size":"M","body_shape":"偏瘦","suggested_style":"轻薄款","reasoning":"结合照片与偏好推荐M码"}'}]
        }
        return resp

    with patch("app.ai_runtime_config._get_engine", return_value=engine), \
         patch.dict("os.environ", {"OPENCODE_GO_API_KEY": "go-key-test"}), \
         patch("httpx.post", side_effect=fake_go_post):
        profile = resolve_user_profile(
            image_bytes=b"photo",
            mime_type="image/jpeg",
            color_preference="黑色",
            gender="female",
            mbti=None,
            size=None,
            style_preference=None,
            gemini_api_key=None,
            gemini_model=None,
            ai_provider="opencode_go",
            vision_provider="opencode_go",
        )
    assert profile["ai_provider"] == "opencode_go"
    assert profile["vision_provider_used"] == "opencode_go"
    assert profile["resolved_size"] == "M"
    assert go_captured[0] == "https://opencode.ai/inference/go/anthropic/v1/messages"


def test_assistant_rule_extraction_and_llm_enhance_opencode_go():
    patch_out = extract_recommend_fields("帮我用 OpenCode Go 的 gpt-6-luna 分析照片推荐黑色男款")
    assert patch_out["ai_provider"] == "opencode_go"
    assert patch_out["vision_provider"] == "opencode_go"
    assert patch_out["opencode_go_model"] == "gpt-6-luna"

    ds_vis = extract_recommend_fields("用 DeepSeek 看图推荐白色短款")
    assert ds_vis["vision_provider"] == "deepseek"
    assert ds_vis["ai_provider"] == "deepseek"

    engine = _make_engine(
        providers=[{"provider_key": "opencode_go", "enabled": True, "default_model": "gpt-6-luna", "base_url": "https://opencode.ai/inference/go"}],
        features=[{"feature_key": "assistant_chat", "enabled": True, "default_provider": "opencode_go", "fallback_order": ["opencode_go", "rule"]}],
    )

    def fake_assistant_post(url, *, headers=None, json=None, timeout=None):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.json.return_value = {
            "output_text": '{"intent":"recommend","reply":"已按预算筛选黑色男款","form_patch":{"color_preference":"黑色","gender":"male","ai_provider":"opencode_go","opencode_go_model":"gpt-6-luna"},"confidence":0.9}'
        }
        return resp

    with patch("app.ai_runtime_config._get_engine", return_value=engine), \
         patch.dict("os.environ", {"OPENCODE_GO_API_KEY": "go-key-test"}), \
         patch("httpx.post", side_effect=fake_assistant_post):
        eff, _ = resolve_effective_provider("assistant_chat")
        assert eff == "opencode_go"
        res = asyncio.run(try_llm_enhance("推荐黑色男款", {}))
    assert res is not None
    assert res["provider"] == "opencode_go"
    assert res["form_patch"]["ai_provider"] == "opencode_go"
    assert res["form_patch"]["opencode_go_model"] == "gpt-6-luna"
