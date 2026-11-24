from __future__ import annotations

import asyncio

import pytest

import app.assistant.orchestrator as orchestrator
from app.assistant.orchestrator import process_chat
from app.assistant.schemas import AssistantChatRequest


@pytest.fixture(autouse=True)
def disable_external_llm(monkeypatch):
    async def no_llm(*args, **kwargs):
        return None

    monkeypatch.setattr(orchestrator, "try_llm_enhance", no_llm)


def _chat(message: str, locale: str):
    return asyncio.run(process_chat(AssistantChatRequest(message=message, locale=locale)))


def test_equivalent_recommendation_intents_have_the_same_canonical_patch():
    messages = {
        "zh-CN": "黑色女款羽绒服，500以内，尺码M，短款",
        "en": "black women's down jacket under 500, size M, short",
        "ja": "黒いレディースダウンジャケット、500元以内、サイズM、ショート",
    }
    responses = {locale: _chat(message, locale) for locale, message in messages.items()}
    patches = [response.action.form_patch.model_dump(exclude_none=True) for response in responses.values()]
    assert patches[0] == patches[1] == patches[2]
    assert patches[0] == {"gender": "female", "color_preference": "黑色", "price_max": 500.0, "size": "M", "style_preference": "短款"}
    assert all(response.locale == locale for locale, response in responses.items())


def test_rule_fallback_replies_are_localized_and_faq_is_localized():
    english = _chat("How do I use the site?", "en")
    japanese = _chat("サイトの使い方を教えてください", "ja")
    assert "recommendation" not in english.reply.lower() or "recommend" in english.reply.lower()
    assert not any("\u3400" <= char <= "\u9fff" for char in english.reply)
    assert "サイト" in japanese.reply
    assert "推荐" not in japanese.reply


def test_japanese_reply_with_shared_kanji_is_accepted():
    assert orchestrator.reply_matches_locale("条件に合う商品を推薦します。", "ja")
