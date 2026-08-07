"""Tests for LLM response hardening — TDD red phase.

Covers gaps G1–G6 from the Task 3 design:
  G1 - non-finite / out-of-range confidence
  G2 - rogue action.type from LLM
  G3 - junk-JSON (no known profile fields) counted as AI success
  G4 - non-string reasoning / oversized reply
  G5 - malformed provider envelopes (already safe, regression tests)
  G6 - truncated JSON silently returns None
"""
from __future__ import annotations

import json
import math
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Part 1 — extract_json_object (consolidated strip_json_block)
# ---------------------------------------------------------------------------

class TestExtractJsonObject(unittest.TestCase):

    def _fn(self, text):
        from app.llm_parsing import extract_json_object
        return extract_json_object(text)

    def test_none_input_returns_none(self):
        self.assertIsNone(self._fn(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(self._fn(""))

    def test_whitespace_only_returns_none(self):
        self.assertIsNone(self._fn("   \n  "))

    def test_plain_prose_returns_none(self):
        self.assertIsNone(self._fn("The recommended size is L."))

    def test_bare_json_object(self):
        result = self._fn('{"a": 1}')
        self.assertEqual(result, {"a": 1})

    def test_fenced_json_block(self):
        text = '```json\n{"body_shape": "标准"}\n```'
        result = self._fn(text)
        self.assertEqual(result, {"body_shape": "标准"})

    def test_fenced_no_lang_tag(self):
        text = '```\n{"body_shape": "标准"}\n```'
        result = self._fn(text)
        self.assertEqual(result, {"body_shape": "标准"})

    def test_json_embedded_in_prose(self):
        text = 'Here is the result: {"recommended_size": "M"} Hope that helps.'
        result = self._fn(text)
        self.assertEqual(result, {"recommended_size": "M"})

    def test_truncated_json_returns_none(self):
        self.assertIsNone(self._fn('{"recommended_size": "M", "body_sh'))

    def test_json_array_returns_none(self):
        self.assertIsNone(self._fn('[1, 2, 3]'))

    def test_json_string_returns_none(self):
        self.assertIsNone(self._fn('"just a string"'))

    def test_json_number_returns_none(self):
        self.assertIsNone(self._fn('42'))

    def test_single_quote_json_returns_none(self):
        self.assertIsNone(self._fn("{'a': 1}"))

    def test_nested_braces(self):
        text = '{"outer": {"inner": 1}}'
        result = self._fn(text)
        self.assertEqual(result, {"outer": {"inner": 1}})

    def test_extra_text_before_brace(self):
        text = "Some preamble\n```\n{\"key\": \"val\"}\n```\nTrailing text"
        result = self._fn(text)
        self.assertEqual(result, {"key": "val"})

    def test_result_is_always_dict_or_none(self):
        for text in ['{"x":1}', '', 'abc', '[1]']:
            result = self._fn(text)
            self.assertIn(type(result), (dict, type(None)))


# ---------------------------------------------------------------------------
# Part 2 — coerce_confidence (G1)
# ---------------------------------------------------------------------------

class TestCoerceConfidence(unittest.TestCase):

    def _fn(self, value, **kw):
        from app.llm_parsing import coerce_confidence
        return coerce_confidence(value, **kw)

    def test_valid_float_passthrough(self):
        self.assertAlmostEqual(self._fn(0.8), 0.8)

    def test_zero_and_one_passthrough(self):
        self.assertAlmostEqual(self._fn(0.0), 0.0)
        self.assertAlmostEqual(self._fn(1.0), 1.0)

    def test_nan_returns_default(self):
        result = self._fn(float("nan"))
        self.assertFalse(math.isnan(result))
        self.assertGreaterEqual(result, 0.0)
        self.assertLessEqual(result, 1.0)

    def test_inf_returns_clamped(self):
        result = self._fn(float("inf"))
        self.assertEqual(result, 1.0)

    def test_negative_inf_returns_clamped(self):
        result = self._fn(float("-inf"))
        self.assertEqual(result, 0.0)

    def test_above_one_clamped(self):
        self.assertEqual(self._fn(2.0), 1.0)

    def test_below_zero_clamped(self):
        self.assertEqual(self._fn(-1.0), 0.0)

    def test_string_returns_default(self):
        result = self._fn("0.8")
        self.assertIsInstance(result, float)
        self.assertGreaterEqual(result, 0.0)
        self.assertLessEqual(result, 1.0)

    def test_bool_returns_default(self):
        result = self._fn(True)
        self.assertIsInstance(result, float)
        self.assertGreaterEqual(result, 0.0)
        self.assertLessEqual(result, 1.0)

    def test_none_returns_default(self):
        result = self._fn(None)
        self.assertIsInstance(result, float)
        self.assertGreaterEqual(result, 0.0)
        self.assertLessEqual(result, 1.0)

    def test_custom_default(self):
        self.assertAlmostEqual(self._fn(None, default=0.7), 0.7)

    def test_integer_input(self):
        result = self._fn(1)
        self.assertAlmostEqual(result, 1.0)


# ---------------------------------------------------------------------------
# Part 3 — coerce_text (G4)
# ---------------------------------------------------------------------------

class TestCoerceText(unittest.TestCase):

    def _fn(self, value, **kw):
        from app.llm_parsing import coerce_text
        return coerce_text(value, **kw)

    def test_normal_string_passthrough(self):
        self.assertEqual(self._fn("hello"), "hello")

    def test_none_returns_none(self):
        self.assertIsNone(self._fn(None))

    def test_dict_returns_none(self):
        self.assertIsNone(self._fn({"a": 1}))

    def test_list_returns_none(self):
        self.assertIsNone(self._fn([1, 2, 3]))

    def test_int_returns_none(self):
        self.assertIsNone(self._fn(42))

    def test_strips_whitespace(self):
        self.assertEqual(self._fn("  hi  "), "hi")

    def test_empty_after_strip_returns_none(self):
        self.assertIsNone(self._fn("   "))

    def test_length_clamped(self):
        long_text = "x" * 5000
        result = self._fn(long_text, max_len=2000)
        self.assertIsNotNone(result)
        self.assertLessEqual(len(result), 2000)

    def test_default_max_len_2000(self):
        long_text = "x" * 3000
        result = self._fn(long_text)
        self.assertLessEqual(len(result), 2000)

    def test_short_text_not_truncated(self):
        text = "短推理文本"
        self.assertEqual(self._fn(text), text)


# ---------------------------------------------------------------------------
# Part 4 — has_known_profile_field (G3)
# ---------------------------------------------------------------------------

class TestHasKnownProfileField(unittest.TestCase):

    def _fn(self, parsed):
        from app.llm_parsing import has_known_profile_field
        return has_known_profile_field(parsed)

    def test_all_known_fields(self):
        self.assertTrue(self._fn({
            "recommended_size": "M",
            "body_shape": "标准",
            "suggested_style": "短款",
            "reasoning": "OK",
        }))

    def test_one_known_field(self):
        self.assertTrue(self._fn({"recommended_size": "L"}))

    def test_junk_fields_only(self):
        self.assertFalse(self._fn({"foo": "bar", "baz": 1}))

    def test_empty_dict(self):
        self.assertFalse(self._fn({}))

    def test_mixed_junk_and_known(self):
        self.assertTrue(self._fn({"body_shape": "偏瘦", "extra": "ignored"}))


# ---------------------------------------------------------------------------
# Part 5 — Provider envelope hardening (G5, regression)
# ---------------------------------------------------------------------------

class TestGeminiEnvelope(unittest.TestCase):

    def _call(self, response_body):
        from app.recommendation import call_gemini_text_profile
        mock_resp = MagicMock()
        mock_resp.json.return_value = response_body
        mock_resp.raise_for_status = MagicMock()
        with patch("app.profile_providers.httpx.post", return_value=mock_resp):
            return call_gemini_text_profile(
                api_key="k", gender=None, mbti=None,
                color_preference="黑色", size=None, style_preference=None, model="m",
            )

    def test_empty_candidates_returns_none(self):
        self.assertIsNone(self._call({"candidates": []}))

    def test_no_candidates_key_returns_none(self):
        self.assertIsNone(self._call({}))

    def test_candidate_missing_content_returns_none(self):
        self.assertIsNone(self._call({"candidates": [{}]}))

    def test_candidate_no_text_part_returns_none(self):
        self.assertIsNone(self._call({
            "candidates": [{"content": {"parts": [{"inline_data": "x"}]}}]
        }))

    def test_valid_response_returns_dict(self):
        result = self._call({
            "candidates": [{
                "content": {"parts": [{"text": '{"body_shape": "标准", "recommended_size": "M", "suggested_style": "短款", "reasoning": "OK"}'}]}
            }]
        })
        self.assertIsInstance(result, dict)


class TestDeepSeekEnvelope(unittest.TestCase):

    def _call(self, response_body):
        from app.recommendation import call_deepseek_profile
        mock_resp = MagicMock()
        mock_resp.json.return_value = response_body
        mock_resp.raise_for_status = MagicMock()
        with patch("app.profile_providers.httpx.post", return_value=mock_resp):
            return call_deepseek_profile(
                api_key="k", gender=None, mbti=None,
                color_preference="黑色", size=None, style_preference=None, model="m",
            )

    def test_empty_choices_returns_none(self):
        self.assertIsNone(self._call({"choices": []}))

    def test_no_choices_key_returns_none(self):
        self.assertIsNone(self._call({}))

    def test_empty_content_returns_none(self):
        self.assertIsNone(self._call({
            "choices": [{"message": {"content": ""}}]
        }))

    def test_valid_response_returns_dict(self):
        payload = '{"body_shape": "标准", "recommended_size": "L", "suggested_style": "长款", "reasoning": "test"}'
        result = self._call({"choices": [{"message": {"content": payload}}]})
        self.assertIsInstance(result, dict)


class TestMimoEnvelope(unittest.TestCase):

    def _call(self, response_body):
        from app.recommendation import call_mimo_profile
        mock_resp = MagicMock()
        mock_resp.json.return_value = response_body
        mock_resp.raise_for_status = MagicMock()
        with patch("app.profile_providers.httpx.post", return_value=mock_resp):
            return call_mimo_profile(
                api_key="k", gender=None, mbti=None,
                color_preference="黑色", size=None, style_preference=None,
            )

    def test_empty_choices_returns_none(self):
        self.assertIsNone(self._call({"choices": []}))

    def test_content_none_reasoning_content_fallback(self):
        payload = '{"body_shape": "标准", "recommended_size": "M", "suggested_style": "短款", "reasoning": "R"}'
        result = self._call({
            "choices": [{"message": {"content": None, "reasoning_content": payload}}]
        })
        self.assertIsInstance(result, dict)

    def test_both_none_returns_none(self):
        self.assertIsNone(self._call({
            "choices": [{"message": {"content": None, "reasoning_content": None}}]
        }))


# ---------------------------------------------------------------------------
# Part 6 — resolve_user_profile: junk-JSON falls through (G3)
# ---------------------------------------------------------------------------

class TestResolveUserProfileJunkJson(unittest.TestCase):

    def _resolve(self, ai_returns):
        """Patch all three call_*_profile to return ai_returns, run resolve."""
        from app.recommendation import resolve_user_profile

        with (
            patch("app.profile_inference.call_gemini_profile", return_value=ai_returns),
            patch("app.profile_inference.call_gemini_text_profile", return_value=ai_returns),
            patch("app.profile_inference.call_deepseek_profile", return_value=ai_returns),
            patch("app.profile_inference.call_mimo_profile", return_value=ai_returns),
            patch("app.profile_inference.resolve_effective_provider",
                  side_effect=[("gemini", ["gemini"]), ("gemini", ["gemini"])]),
            patch("app.profile_inference.resolve_provider_config",
                  return_value={"api_key": "k", "default_model": "m", "base_url": None,
                                "auth_type": None, "auth_header_name": None, "failure_reason": ""}),
        ):
            return resolve_user_profile(
                image_bytes=None, mime_type=None,
                color_preference="黑色", gender=None, mbti=None,
                size=None, style_preference=None,
                gemini_api_key="k", gemini_model="m",
            )

    def test_junk_json_triggers_rule_fallback(self):
        result = self._resolve({"completely": "unrelated", "junk": True})
        self.assertTrue(result["rule_fallback_used"], "junk-JSON should trigger rule fallback")
        self.assertNotIn(result["ai_provider"], ("gemini", "deepseek", "mimo"))

    def test_valid_profile_json_uses_ai(self):
        result = self._resolve({
            "body_shape": "标准", "recommended_size": "M",
            "suggested_style": "短款", "reasoning": "ok",
        })
        self.assertFalse(result["rule_fallback_used"])


# ---------------------------------------------------------------------------
# Part 7 — resolve_user_profile: reasoning safety (G4)
# ---------------------------------------------------------------------------

class TestResolveUserProfileReasoningSafety(unittest.TestCase):

    def _resolve(self, ai_returns):
        from app.recommendation import resolve_user_profile

        with (
            patch("app.profile_inference.call_gemini_text_profile", return_value=ai_returns),
            patch("app.profile_inference.resolve_effective_provider",
                  side_effect=[("gemini", ["gemini"]), ("gemini", ["gemini"])]),
            patch("app.profile_inference.resolve_provider_config",
                  return_value={"api_key": "k", "default_model": "m", "base_url": None,
                                "auth_type": None, "auth_header_name": None, "failure_reason": ""}),
        ):
            return resolve_user_profile(
                image_bytes=None, mime_type=None,
                color_preference="黑色", gender=None, mbti=None,
                size=None, style_preference=None,
                gemini_api_key="k", gemini_model="m",
            )

    def test_reasoning_as_dict_not_leaked(self):
        result = self._resolve({
            "body_shape": "标准", "recommended_size": "M",
            "suggested_style": "短款", "reasoning": {"nested": "dict"},
        })
        self.assertIsInstance(result["reasoning"], str)
        self.assertNotIn("{", result["reasoning"][:5])

    def test_reasoning_oversized_clamped(self):
        result = self._resolve({
            "body_shape": "标准", "recommended_size": "M",
            "suggested_style": "短款", "reasoning": "x" * 5000,
        })
        self.assertLessEqual(len(result["reasoning"]), 2000)

    def test_reasoning_none_uses_fallback(self):
        result = self._resolve({
            "body_shape": "标准", "recommended_size": "M",
            "suggested_style": "短款", "reasoning": None,
        })
        self.assertIsInstance(result["reasoning"], str)
        self.assertGreater(len(result["reasoning"]), 0)


# ---------------------------------------------------------------------------
# Part 8 — try_llm_enhance: rogue action type (G2)
# ---------------------------------------------------------------------------

class TestTryLlmEnhanceActionType(unittest.TestCase):

    def _make_llm_text(self, action_type: str) -> str:
        return json.dumps({
            "intent": "recommend",
            "reply": "OK",
            "form_patch": {"color_preference": "黑色"},
            "action": {"type": action_type, "requires_confirmation": True},
            "confidence": 0.9,
        }, ensure_ascii=False)

    def _call(self, raw_text):
        import asyncio
        from app.assistant.llm_clients import try_llm_enhance

        mock_caller = MagicMock(return_value=raw_text)
        with (
            patch("app.assistant.llm_clients.resolve_effective_provider",
                  return_value=("mimo", ["mimo"])),
            patch("app.assistant.llm_clients.resolve_provider_config",
                  return_value={"api_key": "k", "default_model": "m", "base_url": None,
                                "auth_type": None, "auth_header_name": None}),
            patch.dict("app.assistant.llm_clients._PROVIDER_CALLERS", {"mimo": mock_caller}),
            patch("app.assistant.llm_clients.load_active_prompt", side_effect=lambda *a, **kw: a[1] if len(a) > 1 else ""),
        ):
            return asyncio.get_event_loop().run_until_complete(
                try_llm_enhance("推荐黑色羽绒服", {})
            )

    def test_known_action_type_passthrough(self):
        result = self._call(self._make_llm_text("fill_recommend_form"))
        self.assertIn(result["action_type"], ("fill_recommend_form", "none"))

    def test_none_action_type_passthrough(self):
        result = self._call(self._make_llm_text("none"))
        self.assertEqual(result["action_type"], "none")

    def test_rogue_action_type_rejected(self):
        result = self._call(self._make_llm_text("delete_all_products"))
        self.assertIn(result["action_type"], ("fill_recommend_form", "none"),
                      "rogue action type must be coerced to a safe value")

    def test_rogue_action_type_xss_rejected(self):
        result = self._call(self._make_llm_text("<script>alert(1)</script>"))
        self.assertIn(result["action_type"], ("fill_recommend_form", "none"))


# ---------------------------------------------------------------------------
# Part 9 — try_llm_enhance: NaN confidence (G1)
# ---------------------------------------------------------------------------

class TestTryLlmEnhanceNanConfidence(unittest.TestCase):

    def _call(self, confidence_value):
        import asyncio
        from app.assistant.llm_clients import try_llm_enhance

        raw = json.dumps({
            "intent": "recommend",
            "reply": "OK",
            "form_patch": {"color_preference": "白色"},
            "confidence": confidence_value,
        }, ensure_ascii=False, allow_nan=True)

        mock_caller = MagicMock(return_value=raw)
        with (
            patch("app.assistant.llm_clients.resolve_effective_provider",
                  return_value=("mimo", ["mimo"])),
            patch("app.assistant.llm_clients.resolve_provider_config",
                  return_value={"api_key": "k", "default_model": "m", "base_url": None,
                                "auth_type": None, "auth_header_name": None}),
            patch.dict("app.assistant.llm_clients._PROVIDER_CALLERS", {"mimo": mock_caller}),
            patch("app.assistant.llm_clients.load_active_prompt", side_effect=lambda *a, **kw: a[1] if len(a) > 1 else ""),
        ):
            return asyncio.get_event_loop().run_until_complete(
                try_llm_enhance("推荐白色羽绒服", {})
            )

    def test_nan_confidence_produces_finite_result(self):
        result = self._call(float("nan"))
        self.assertIsNotNone(result)
        conf = result["confidence"]
        self.assertFalse(math.isnan(conf), "confidence must not be NaN")
        self.assertFalse(math.isinf(conf), "confidence must not be inf")

    def test_inf_confidence_clamped(self):
        result = self._call(float("inf"))
        self.assertIsNotNone(result)
        self.assertLessEqual(result["confidence"], 1.0)

    def test_normal_confidence_untouched(self):
        result = self._call(0.85)
        self.assertAlmostEqual(result["confidence"], 0.85)


# ---------------------------------------------------------------------------
# Part 10 — End-to-end: process_chat with NaN confidence is JSON-serializable (G1)
# ---------------------------------------------------------------------------

class TestProcessChatNanConfidenceSerializable(unittest.TestCase):

    def test_nan_confidence_response_serializes(self):
        import asyncio
        from app.assistant.orchestrator import process_chat
        from app.assistant.schemas import AssistantChatRequest, AssistantPageContext

        nan_llm_result = {
            "intent": "recommend",
            "reply": "OK",
            "form_patch": {"color_preference": "黑色"},
            "action_type": "fill_recommend_form",
            "requires_confirmation": True,
            "confidence": float("nan"),
            "provider": "mimo",
            "fallback_used": False,
            "errors": [],
        }

        with patch("app.assistant.orchestrator.try_llm_enhance",
                   new=AsyncMock(return_value=nan_llm_result)):
            request = AssistantChatRequest(
                message="推荐黑色羽绒服",
                page_context=AssistantPageContext(),
            )
            response = asyncio.get_event_loop().run_until_complete(process_chat(request))

        # Must be JSON-serializable without raising
        try:
            serialized = json.dumps(response.model_dump(), allow_nan=False)
        except (ValueError, TypeError) as exc:
            self.fail(f"Response is not JSON-serializable: {exc}")

        parsed = json.loads(serialized)
        # Action confidence must be finite
        if parsed.get("action"):
            conf = parsed["action"].get("confidence", 0.0)
            self.assertFalse(math.isnan(conf))


# ---------------------------------------------------------------------------
# Part 11 — try_llm_enhance: reply clamped, form_patch type safety (G4, regression)
# ---------------------------------------------------------------------------

class TestTryLlmEnhanceFieldSafety(unittest.TestCase):

    def _call(self, payload_dict):
        import asyncio
        from app.assistant.llm_clients import try_llm_enhance

        raw = json.dumps(payload_dict, ensure_ascii=False)
        mock_caller = MagicMock(return_value=raw)
        with (
            patch("app.assistant.llm_clients.resolve_effective_provider",
                  return_value=("mimo", ["mimo"])),
            patch("app.assistant.llm_clients.resolve_provider_config",
                  return_value={"api_key": "k", "default_model": "m", "base_url": None,
                                "auth_type": None, "auth_header_name": None}),
            patch.dict("app.assistant.llm_clients._PROVIDER_CALLERS", {"mimo": mock_caller}),
            patch("app.assistant.llm_clients.load_active_prompt", side_effect=lambda *a, **kw: a[1] if len(a) > 1 else ""),
        ):
            return asyncio.get_event_loop().run_until_complete(
                try_llm_enhance("推荐", {})
            )

    def test_oversized_reply_clamped(self):
        result = self._call({
            "intent": "faq", "reply": "x" * 5000,
            "form_patch": {}, "confidence": 0.5,
        })
        self.assertIsNotNone(result)
        self.assertLessEqual(len(result["reply"]), 2000)

    def test_form_patch_as_string_becomes_empty(self):
        result = self._call({
            "intent": "recommend", "reply": "OK",
            "form_patch": "not a dict", "confidence": 0.5,
        })
        self.assertIsNotNone(result)
        self.assertEqual(result["form_patch"], {})

    def test_form_patch_as_list_becomes_empty(self):
        result = self._call({
            "intent": "recommend", "reply": "OK",
            "form_patch": ["color_preference", "黑色"], "confidence": 0.5,
        })
        self.assertIsNotNone(result)
        self.assertEqual(result["form_patch"], {})

    def test_extra_form_patch_keys_filtered(self):
        result = self._call({
            "intent": "recommend", "reply": "OK",
            "form_patch": {"color_preference": "黑色", "excluded_style": "面包服"},
            "confidence": 0.5,
        })
        self.assertIsNotNone(result)
        self.assertNotIn("excluded_style", result["form_patch"])
        self.assertIn("color_preference", result["form_patch"])


# ---------------------------------------------------------------------------
# Part 12 — orchestrator.py action_type=="none" + NaN confidence (latent path)
# ---------------------------------------------------------------------------

class TestProcessChatNoneActionNanConfidence(unittest.TestCase):
    """Regression: orchestrator line that builds AssistantAction(type="none", confidence=…).

    When try_llm_enhance returns a valid reply but no actionable form_patch,
    action_type stays "none" and orchestrator constructs AssistantAction directly
    with the confidence value from the LLM result.  If that value is NaN the
    Pydantic ge/le constraint raises ValidationError — this test guards against
    that regression.
    """

    def test_none_action_nan_confidence_no_validation_error(self):
        import asyncio
        import math
        from app.assistant.orchestrator import process_chat
        from app.assistant.schemas import AssistantChatRequest, AssistantPageContext

        # reply is valid, form_patch is empty → action_type will be "none"
        llm_result = {
            "intent": "faq",
            "reply": "这是一个常见问题的回答。",
            "form_patch": {},
            "action_type": "none",
            "requires_confirmation": False,
            "confidence": float("nan"),
            "provider": "mimo",
            "fallback_used": False,
            "errors": [],
        }

        with patch("app.assistant.orchestrator.try_llm_enhance",
                   new=AsyncMock(return_value=llm_result)):
            request = AssistantChatRequest(
                message="什么是MBTI",
                page_context=AssistantPageContext(),
            )
            # Must not raise ValidationError
            response = asyncio.get_event_loop().run_until_complete(process_chat(request))

        self.assertEqual(response.action.type, "none")

        conf = response.action.confidence
        self.assertFalse(math.isnan(conf), "action.confidence must not be NaN")
        self.assertFalse(math.isinf(conf), "action.confidence must not be inf")
        self.assertGreaterEqual(conf, 0.0)
        self.assertLessEqual(conf, 1.0)

        # Must be JSON-serializable
        try:
            json.dumps(response.model_dump(), allow_nan=False)
        except (ValueError, TypeError) as exc:
            self.fail(f"Response is not JSON-serializable: {exc}")


if __name__ == "__main__":
    unittest.main()
