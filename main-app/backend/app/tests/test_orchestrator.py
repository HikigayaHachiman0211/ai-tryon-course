"""Pure unit tests for assistant orchestrator helper functions.

No mocking, no network, no database.  Tests pure logic in:
  - orchestrator.classify_intent
  - orchestrator.build_recommend_reply
  - orchestrator.build_tryon_reply
  - orchestrator.build_style_lab_reply
  - orchestrator.build_unknown_reply
  - orchestrator.build_recommend_action
"""
from __future__ import annotations

from app.assistant.orchestrator import (
    build_recommend_action,
    build_recommend_reply,
    build_style_lab_reply,
    build_tryon_reply,
    build_unknown_reply,
    classify_intent,
)


# ---------------------------------------------------------------------------
# classify_intent
# ---------------------------------------------------------------------------

class TestClassifyIntent:
    def test_recommend_keywords(self):
        assert classify_intent("帮我推荐一件黑色羽绒服") == "recommend"

    def test_recommend_budget_keyword(self):
        assert classify_intent("预算500以内的女款羽绒服") == "recommend"

    def test_tryon_keyword(self):
        assert classify_intent("我想试穿这件") == "tryon"

    def test_virtual_tryon_keyword(self):
        assert classify_intent("虚拟试穿怎么用") == "tryon"

    def test_style_lab_keyword(self):
        assert classify_intent("自己搭配") == "style_lab"

    def test_faq_keyword_how(self):
        # "尺码" is also a recommend keyword so we use a clearly non-recommend question
        assert classify_intent("这个网站怎么用") == "faq"

    def test_faq_keyword_what(self):
        assert classify_intent("什么是MBTI") == "faq"

    def test_faq_privacy(self):
        assert classify_intent("我的照片会怎么处理，隐私有保障吗") == "faq"

    def test_unknown_random(self):
        assert classify_intent("随便说说") == "unknown"

    def test_empty_string(self):
        assert classify_intent("") == "unknown"


# ---------------------------------------------------------------------------
# build_recommend_reply
# ---------------------------------------------------------------------------

class TestBuildRecommendReply:
    def test_female_gender(self):
        reply = build_recommend_reply({"gender": "female"})
        assert "女款" in reply

    def test_male_gender(self):
        reply = build_recommend_reply({"gender": "male"})
        assert "男款" in reply

    def test_color(self):
        reply = build_recommend_reply({"color_preference": "黑色"})
        assert "黑色" in reply

    def test_budget_max_only(self):
        reply = build_recommend_reply({"price_max": 500.0})
        assert "500" in reply
        assert "以内" in reply

    def test_budget_min_and_max(self):
        reply = build_recommend_reply({"price_min": 200.0, "price_max": 800.0})
        assert "200" in reply
        assert "800" in reply

    def test_size(self):
        reply = build_recommend_reply({"size": "XL"})
        assert "XL" in reply

    def test_style(self):
        reply = build_recommend_reply({"style_preference": "短款"})
        assert "短款" in reply

    def test_brand(self):
        reply = build_recommend_reply({"brand_preference": "波司登"})
        assert "波司登" in reply

    def test_empty_patch_still_returns_string(self):
        reply = build_recommend_reply({})
        assert isinstance(reply, str)
        assert len(reply) > 0


# ---------------------------------------------------------------------------
# Static reply builders
# ---------------------------------------------------------------------------

class TestStaticReplies:
    def test_tryon_reply_mentions_tryon(self):
        reply = build_tryon_reply()
        assert "试穿" in reply

    def test_style_lab_reply_mentions_style_lab(self):
        reply = build_style_lab_reply()
        assert "Style Lab" in reply or "自己搭配" in reply

    def test_unknown_reply_is_nonempty(self):
        reply = build_unknown_reply()
        assert isinstance(reply, str)
        assert len(reply) > 0


# ---------------------------------------------------------------------------
# build_recommend_action
# ---------------------------------------------------------------------------

class TestBuildRecommendAction:
    def test_action_type(self):
        action = build_recommend_action({"color_preference": "白色"})
        assert action.type == "fill_recommend_form"

    def test_action_has_form_patch(self):
        action = build_recommend_action({"color_preference": "白色", "gender": "female"})
        assert action.form_patch is not None
        assert action.form_patch.color_preference == "白色"
        assert action.form_patch.gender == "female"

    def test_action_requires_confirmation_default_true(self):
        action = build_recommend_action({})
        assert action.requires_confirmation is True

    def test_action_requires_confirmation_false(self):
        action = build_recommend_action({}, requires_confirmation=False)
        assert action.requires_confirmation is False

    def test_unknown_fields_stripped(self):
        action = build_recommend_action({"color_preference": "蓝色", "nonexistent_field": "x"})
        assert action.form_patch is not None
        assert not hasattr(action.form_patch, "nonexistent_field")
