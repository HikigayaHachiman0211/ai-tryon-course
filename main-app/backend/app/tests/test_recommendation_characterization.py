"""Characterization tests for app.recommendation.

These tests pin the current observable behavior of recommendation.py so
that the planned behavior-preserving split (Task 7, Commits B–E) cannot
silently alter any output.  All imports go through app.recommendation so
the facade re-export strategy keeps them valid after extraction.

No database, no network, no real API keys.
All AI calls are blocked by patching resolve_effective_provider to return
a ["rule"] chain and resolve_provider_config to return an empty api_key.
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from app.database import Product


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_EMPTY_PROVIDER_CFG = {
    "api_key": "",
    "default_model": "test-model",
    "base_url": None,
    "auth_type": None,
    "auth_header_name": None,
    "failure_reason": "",
}


@contextmanager
def _no_ai():
    """Patch provider resolution so AI calls are never attempted (rule fallback)."""
    with (
        patch(
            "app.profile_inference.resolve_effective_provider",
            return_value=("rule", ["rule"]),
        ),
        patch(
            "app.profile_inference.resolve_provider_config",
            return_value=_EMPTY_PROVIDER_CFG,
        ),
    ):
        yield


def _make_product(
    pid: int = 1,
    title: str = "测试羽绒服",
    price: float = 300.0,
    style_type: str = "短款",
    color_family: str = "黑色",
    body_fit: str = "标准常规",
    style_features: list | None = None,
    function_features: list | None = None,
    size_tags: list | None = None,
    size_notes: str | None = None,
    product_url: str | None = None,
    image_path: str = "test/product.jpg",
) -> Product:
    return Product(
        id=pid,
        title=title,
        price=price,
        image_path=image_path,
        style_type=style_type,
        color_family=color_family,
        body_fit=body_fit,
        style_features=style_features if style_features is not None else [],
        function_features=function_features if function_features is not None else [],
        size_tags=size_tags if size_tags is not None else ["M", "L", "XL"],
        size_notes=size_notes,
        product_url=product_url,
    )


def _recommend_kwargs(**overrides):
    """Return a minimal valid kwargs dict for recommend_products."""
    base = dict(
        products=[_make_product()],
        total_catalog_count=1,
        image_bytes=None,
        mime_type=None,
        color_preference="黑色",
        brand_preference=None,
        gender=None,
        mbti=None,
        size="M",
        style_preference=None,
        gemini_api_key=None,
        gemini_model=None,
        price_min=None,
        price_max=None,
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. Public API response shape — recommend_products
# ---------------------------------------------------------------------------

class TestRecommendProductsApiShape(unittest.TestCase):

    def _call(self, **kw):
        from app.recommendation import recommend_products
        with _no_ai():
            return recommend_products(**_recommend_kwargs(**kw))

    def test_top_level_keys(self):
        result = self._call()
        self.assertSetEqual(set(result.keys()), {"filters", "inference", "items"})

    def test_filters_keys(self):
        result = self._call()
        self.assertSetEqual(
            set(result["filters"].keys()),
            {
                "price_min", "price_max", "catalog_total",
                "matched_after_price_filter", "matched_after_gender_filter",
                "user_gender", "brand_preference", "gender_fallback",
            },
        )

    def test_inference_keys(self):
        result = self._call()
        self.assertSetEqual(
            set(result["inference"].keys()),
            {
                "resolved_size", "resolved_style", "body_shape",
                "size_source", "style_source", "reasoning",
                "gemini_model", "gemini_used",
                "ai_provider", "vision_provider", "vision_provider_used",
                "mimo_model", "mimo_used", "mimo_multimodal_used",
                "ai_attempted", "rule_fallback_used", "provider_error_summary",
            },
        )

    def test_item_keys_present_and_no_internal_sort_keys(self):
        result = self._call()
        self.assertTrue(len(result["items"]) > 0)
        item = result["items"][0]
        expected = {
            "id", "title", "price", "image_url", "brand", "platform",
            "product_url", "style_type", "color_family", "body_fit",
            "style_features", "function_features", "size_tags", "size_notes",
            "total_score", "score_breakdown", "radar_chart", "brand_score", "reason",
        }
        self.assertSetEqual(set(item.keys()), expected)
        # Internal ranking keys must be popped before returning
        for forbidden in ("gender_match_priority", "brand_exact_priority", "brand_match_count"):
            self.assertNotIn(forbidden, item)

    def test_items_is_list(self):
        result = self._call()
        self.assertIsInstance(result["items"], list)

    def test_empty_catalog_returns_message_and_no_items(self):
        result = self._call(products=[], total_catalog_count=0)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["message"], "当前价位区间没有匹配商品。")
        self.assertIn("filters", result)
        self.assertIn("inference", result)

    def test_empty_after_gender_filter_returns_message(self):
        # Male-only product, female user → no gender match → empty result with message
        male_product = _make_product(title="男士冬季羽绒服精品款")
        result = self._call(products=[male_product], total_catalog_count=1, gender="female")
        self.assertEqual(result["items"], [])
        self.assertEqual(result["message"], "当前筛选条件下没有匹配所选性别的商品。")

    def test_filters_catalog_total_reflects_arg(self):
        result = self._call(total_catalog_count=99)
        self.assertEqual(result["filters"]["catalog_total"], 99)

    def test_filters_price_range_passthrough(self):
        result = self._call(price_min=100.0, price_max=500.0)
        self.assertEqual(result["filters"]["price_min"], 100.0)
        self.assertEqual(result["filters"]["price_max"], 500.0)


# ---------------------------------------------------------------------------
# 2. Public API response shape — list_catalog_products
# ---------------------------------------------------------------------------

class TestListCatalogProductsApiShape(unittest.TestCase):

    def _call(self, **kw):
        from app.recommendation import list_catalog_products
        base = dict(
            products=[_make_product()],
            query=None,
            gender=None,
            platform=None,
            mode="all",
            offset=0,
            limit=20,
        )
        base.update(kw)
        return list_catalog_products(**base)

    def test_top_level_keys(self):
        result = self._call()
        self.assertSetEqual(
            set(result.keys()),
            {"items", "total", "offset", "limit", "mode", "user_gender", "gender_fallback"},
        )

    def test_item_keys(self):
        result = self._call()
        self.assertTrue(len(result["items"]) > 0)
        item = result["items"][0]
        expected = {
            "id", "title", "price", "image_url", "brand", "platform",
            "product_url", "style_type", "color_family", "body_fit",
            "style_features", "function_features", "size_tags", "size_notes",
            "product_gender", "gender_label", "is_child_product",
        }
        self.assertSetEqual(set(item.keys()), expected)

    def test_pagination_offset_clamped_below_zero(self):
        result = self._call(offset=-5)
        self.assertEqual(result["offset"], 0)

    def test_pagination_limit_clamped_above_120(self):
        result = self._call(limit=999)
        self.assertEqual(result["limit"], 120)

    def test_pagination_limit_clamped_below_one(self):
        result = self._call(limit=0)
        self.assertEqual(result["limit"], 1)

    def test_total_reflects_filtered_count(self):
        products = [_make_product(pid=i, title=f"羽绒服{i}") for i in range(5)]
        result = self._call(products=products, limit=2, offset=0)
        self.assertEqual(result["total"], 5)
        self.assertEqual(len(result["items"]), 2)

    def test_mode_passthrough(self):
        result = self._call(mode="gender")
        self.assertEqual(result["mode"], "gender")


# ---------------------------------------------------------------------------
# 3. Public API response shape — analyze_selected_product
# ---------------------------------------------------------------------------

class TestAnalyzeSelectedProductApiShape(unittest.TestCase):

    def _call(self, **kw):
        from app.recommendation import analyze_selected_product
        base = dict(
            product=_make_product(),
            image_bytes=None,
            mime_type=None,
            color_preference="黑色",
            brand_preference=None,
            gender=None,
            mbti=None,
            size="M",
            style_preference=None,
            gemini_api_key=None,
            gemini_model=None,
            price_min=None,
            price_max=None,
        )
        base.update(kw)
        with _no_ai():
            return analyze_selected_product(**base)

    def test_top_level_keys(self):
        result = self._call()
        self.assertSetEqual(set(result.keys()), {"product", "inference", "analysis"})

    def test_analysis_keys(self):
        result = self._call()
        self.assertSetEqual(
            set(result["analysis"].keys()),
            {
                "total_score", "score_breakdown", "radar_chart", "reason",
                "styling_advice", "brand_score", "budget_note", "brand_note",
                "gender_note", "personality_note",
            },
        )

    def test_product_field_is_catalog_serialized_form(self):
        result = self._call()
        # Must include catalog item keys (with product_gender, gender_label, is_child_product)
        self.assertIn("product_gender", result["product"])
        self.assertIn("gender_label", result["product"])
        self.assertIn("is_child_product", result["product"])

    def test_styling_advice_is_list(self):
        result = self._call()
        self.assertIsInstance(result["analysis"]["styling_advice"], list)

    def test_score_breakdown_is_dict(self):
        result = self._call()
        self.assertIsInstance(result["analysis"]["score_breakdown"], dict)

    def test_radar_chart_is_list_of_dicts(self):
        result = self._call()
        radar = result["analysis"]["radar_chart"]
        self.assertIsInstance(radar, list)
        for entry in radar:
            self.assertIn("dimension", entry)
            self.assertIn("score", entry)


# ---------------------------------------------------------------------------
# 4. Rule-fallback behavior
# ---------------------------------------------------------------------------

class TestRuleFallback(unittest.TestCase):

    def _resolve(self, **kw):
        from app.recommendation import resolve_user_profile
        with _no_ai():
            base = dict(
                image_bytes=None, mime_type=None,
                color_preference="黑色", gender=None, mbti=None,
                size=None, style_preference=None,
                gemini_api_key=None, gemini_model=None,
            )
            base.update(kw)
            return resolve_user_profile(**base)

    def test_rule_fallback_flag_set(self):
        result = self._resolve()
        self.assertTrue(result["rule_fallback_used"])

    def test_ai_provider_is_none_string(self):
        result = self._resolve()
        self.assertEqual(result["ai_provider"], "none")

    def test_reasoning_is_non_empty_string(self):
        result = self._resolve()
        self.assertIsInstance(result["reasoning"], str)
        self.assertGreater(len(result["reasoning"]), 0)

    def test_body_shape_is_non_empty_string(self):
        result = self._resolve()
        self.assertIsInstance(result["body_shape"], str)
        self.assertGreater(len(result["body_shape"]), 0)

    def test_size_from_user_input_preserved(self):
        result = self._resolve(size="L")
        self.assertEqual(result["resolved_size"], "L")
        self.assertEqual(result["size_source"], "user")

    def test_style_from_user_input_preserved(self):
        result = self._resolve(style_preference="短款")
        self.assertEqual(result["resolved_style"], "短款")
        self.assertEqual(result["style_source"], "user")

    def test_ai_not_attempted_when_no_providers(self):
        # With empty chains ["rule"] no AI attempt should be recorded as successful
        result = self._resolve()
        # ai_attempted may be True (attempted but found no provider), rule_fallback_used must be True
        self.assertTrue(result["rule_fallback_used"])
        self.assertFalse(result["mimo_used"])
        self.assertFalse(result["gemini_used"])


# ---------------------------------------------------------------------------
# 5. Ranking and sorting
# ---------------------------------------------------------------------------

class TestRankingAndSorting(unittest.TestCase):

    def _recommend(self, products, **kw):
        from app.recommendation import recommend_products
        with _no_ai():
            return recommend_products(**_recommend_kwargs(products=products, **kw))

    def test_higher_total_score_ranked_first(self):
        # Black color preference → black product scores higher on color dimension.
        # Unique titles prevent deduplication.
        black_product = _make_product(pid=1, title="优质黑色外套甲号款",
                                       color_family="黑色", price=500.0, size_tags=["M"])
        other_product = _make_product(pid=2, title="橘色保暖羽绒服乙号款",
                                       color_family="橘色", price=100.0, size_tags=["M"])
        result = self._recommend(
            [other_product, black_product],
            color_preference="黑色",
            size="M",
        )
        items = result["items"]
        self.assertEqual(len(items), 2)
        self.assertGreaterEqual(items[0]["total_score"], items[1]["total_score"])
        # Black product should be ranked first regardless of higher price
        self.assertEqual(items[0]["id"], 1)

    def test_lower_price_ranked_first_for_equal_scores(self):
        # Same style/color/body → equal scores → cheaper item wins.
        # Unique titles prevent deduplication.
        cheap = _make_product(pid=1, title="短款黑色外套便宜款", price=100.0)
        expensive = _make_product(pid=2, title="短款黑色外套贵价款", price=500.0)
        result = self._recommend([expensive, cheap])
        items = result["items"]
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["id"], 1)  # cheaper first

    def test_gender_match_priority_overrides_lower_score(self):
        # Female user: female product should appear before unisex
        female_product = _make_product(pid=1, title="【女款】冬季羽绒服", price=500.0,
                                        color_family="蓝色")
        unisex_product = _make_product(pid=2, title="男女同款羽绒服精品", price=100.0,
                                        color_family="黑色")
        result = self._recommend(
            [unisex_product, female_product],
            color_preference="黑色",
            gender="female",
        )
        items = result["items"]
        self.assertEqual(len(items), 2)
        # female product wins on gender priority even with worse color score
        self.assertEqual(items[0]["id"], 1)

    def test_brand_exact_priority_overrides_lower_score(self):
        # Preference for 波司登; brand-matched product should come first.
        # Titles must be >18 chars so normalize_brand_name returns None for the
        # title itself, allowing get_product_brand to fall through to style_features.
        bosideng = _make_product(
            pid=1,
            title="这件是一款经典冬季保暖羽绒服新款上市推荐",  # 20 chars → infer_brand_name=None
            style_features=["品牌:波司登"],
            price=999.0,
            color_family="蓝色",
        )
        generic = _make_product(
            pid=2,
            title="这款是另一款非常普通的冬季外套商品推荐",  # 19 chars → infer_brand_name=None
            price=100.0,
            color_family="黑色",
        )
        result = self._recommend(
            [generic, bosideng],
            color_preference="黑色",
            brand_preference="波司登",
        )
        items = result["items"]
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["id"], 1)

    def test_internal_sort_keys_not_in_output(self):
        result = self._recommend([_make_product()])
        for item in result["items"]:
            self.assertNotIn("gender_match_priority", item)
            self.assertNotIn("brand_exact_priority", item)
            self.assertNotIn("brand_match_count", item)


# ---------------------------------------------------------------------------
# 6. Deduplication via extract_product_signature
# ---------------------------------------------------------------------------

class TestProductDedup(unittest.TestCase):

    def _recommend(self, products):
        from app.recommendation import recommend_products
        with _no_ai():
            return recommend_products(**_recommend_kwargs(products=products))

    def test_same_product_code_deduplicated(self):
        # Both products share the same model code in their titles → only first returned
        p1 = _make_product(pid=1, title="冬季羽绒服 BZ-12345 黑色 M码", price=100.0)
        p2 = _make_product(pid=2, title="冬季羽绒服 BZ-12345 白色 L码", price=200.0)
        result = self._recommend([p1, p2])
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["id"], 1)

    def test_different_signatures_both_present(self):
        p1 = _make_product(pid=1, title="冬季羽绒服 AA-11111 黑色", price=100.0)
        p2 = _make_product(pid=2, title="冬季羽绒服 BB-22222 白色", price=200.0)
        result = self._recommend([p1, p2])
        self.assertEqual(len(result["items"]), 2)


# ---------------------------------------------------------------------------
# 7. score_color golden cases
# ---------------------------------------------------------------------------

class TestScoreColor(unittest.TestCase):

    def _fn(self, preferred, product_color):
        from app.recommendation import score_color
        return score_color(preferred, product_color)

    def test_identical_returns_100(self):
        self.assertEqual(self._fn("黑色", "黑色"), 100)

    def test_white_identical(self):
        self.assertEqual(self._fn("白色", "白色"), 100)

    def test_preferred_in_product_returns_98(self):
        # "黑" is a substring of "曜石黑"
        self.assertEqual(self._fn("黑", "曜石黑"), 98)

    def test_product_in_preferred_returns_98(self):
        self.assertEqual(self._fn("深灰蓝色系", "灰"), 98)

    def test_same_group_white_returns_92(self):
        # "白色" and "米白" both map to "white" group
        self.assertEqual(self._fn("白色", "米白"), 92)

    def test_same_group_black_returns_90(self):
        # "黑色" and "曜石黑" both map to "black" group (no substring match here)
        self.assertEqual(self._fn("黑色", "曜石黑"), 90)

    def test_same_group_non_black_white_returns_88(self):
        # "蓝色" and "雾蓝" both in "blue" group
        self.assertEqual(self._fn("蓝色", "雾蓝"), 88)

    def test_neutral_pair_white_gray_returns_76(self):
        self.assertEqual(self._fn("白色", "灰色"), 76)

    def test_neutral_pair_white_brown_returns_68(self):
        self.assertEqual(self._fn("白色", "棕色"), 68)

    def test_neutral_pair_white_black_returns_38(self):
        self.assertEqual(self._fn("白色", "黑色"), 38)

    def test_neutral_pair_black_gray_returns_72(self):
        self.assertEqual(self._fn("黑色", "灰色"), 72)

    def test_neutral_pair_black_brown_returns_58(self):
        self.assertEqual(self._fn("黑色", "棕色"), 58)

    def test_neutral_pair_gray_brown_returns_64(self):
        self.assertEqual(self._fn("灰色", "棕色"), 64)

    def test_one_neutral_one_vivid_returns_52(self):
        # "黑色" is neutral; "蓝色" is not → 52
        self.assertEqual(self._fn("蓝色", "黑色"), 52)

    def test_both_vivid_different_groups_returns_36(self):
        # "红色" and "蓝色" are both non-neutral vivid colors
        self.assertEqual(self._fn("红色", "蓝色"), 36)

    def test_empty_preferred_returns_65(self):
        self.assertEqual(self._fn("", "黑色"), 65)


# ---------------------------------------------------------------------------
# 8. score_body_fit golden cases
# ---------------------------------------------------------------------------

class TestScoreBodyFit(unittest.TestCase):

    def _fn(self, user_size, body_shape, product):
        from app.recommendation import score_body_fit
        return score_body_fit(user_size, body_shape, product)

    def test_regular_user_regular_product_no_tags(self):
        # style_type="面包服" avoids all body-shape bonuses for "标准" body_shape
        p = _make_product(body_fit="标准", style_type="面包服", size_tags=[])
        self.assertEqual(self._fn("M", "标准", p), 93)

    def test_slim_user_slim_product_no_tags(self):
        # style_type="面包服" avoids the +4 bonus for "偏瘦"+"短款"
        p = _make_product(body_fit="修身", style_type="面包服", size_tags=[])
        self.assertEqual(self._fn("S", "偏瘦", p), 94)

    def test_plus_user_plus_product_no_tags(self):
        # body_shape="偏瘦" → not in {微胖, 高壮, O型} so relaxed/plus bonus doesn't fire
        p = _make_product(body_fit="大码", style_type="面包服", size_tags=[])
        self.assertEqual(self._fn("3XL", "偏瘦", p), 96)

    def test_slim_user_plus_product(self):
        # body_shape="标准" → no body-shape bonus for any fit/style combo
        p = _make_product(body_fit="大码", style_type="面包服", size_tags=[])
        self.assertEqual(self._fn("S", "标准", p), 55)

    def test_relaxed_user_slim_product(self):
        p = _make_product(body_fit="修身", size_tags=[])
        self.assertEqual(self._fn("XL", "标准", p), 60)

    def test_size_tag_exact_hit_clamped(self):
        # regular+regular base=93, exact size tag hit +8 = 101 → clamp to 100
        p = _make_product(body_fit="标准", size_tags=["M", "L", "XL"])
        self.assertEqual(self._fn("M", "标准", p), 100)

    def test_size_tag_gap_one_adds_two(self):
        # regular+regular base=93, M vs [XS, S] → gap = min(3-1, 3-2)=1 → +2 → 95
        p = _make_product(body_fit="标准", size_tags=["XS", "S"])
        self.assertEqual(self._fn("M", "标准", p), 95)

    def test_size_tag_large_gap_subtracts(self):
        # relaxed+relaxed base=93, XL vs [XS, S] → gap = min(5-1, 5-2) = 3 → -8 → 85
        p = _make_product(body_fit="宽松", size_tags=["XS", "S"])
        self.assertEqual(self._fn("XL", "标准", p), 85)

    def test_microfit_body_shape_bonus(self):
        # relaxed+relaxed base=93, 微胖+relaxed product → +4 → 97
        p = _make_product(body_fit="宽松", style_type="面包服", size_tags=[])
        self.assertEqual(self._fn("XL", "微胖", p), 97)

    def test_slim_body_shape_bonus(self):
        # slim+slim base=94, 偏瘦+绗缝款 style → +4 → 98
        p = _make_product(body_fit="修身", style_type="绗缝款（排骨款）", size_tags=[])
        self.assertEqual(self._fn("S", "偏瘦", p), 98)

    def test_pear_body_shape_bonus(self):
        # regular+regular base=93, 梨形+中长款大衣 → +4 → 97
        p = _make_product(body_fit="标准", style_type="中长款大衣", size_tags=[])
        self.assertEqual(self._fn("M", "梨形", p), 97)

    def test_none_size_treated_as_regular(self):
        # None size → classify_user_fit("regular"), regular+regular = 93
        p = _make_product(body_fit="标准", size_tags=[])
        self.assertEqual(self._fn(None, "标准", p), 93)


# ---------------------------------------------------------------------------
# 9. score_style golden cases
# ---------------------------------------------------------------------------

class TestScoreStyle(unittest.TestCase):

    def _fn(self, style_preference, product):
        from app.recommendation import score_style
        return score_style(style_preference, product)

    def test_exact_style_type_match_returns_96(self):
        p = _make_product(style_type="短款")
        self.assertEqual(self._fn("短款", p), 96)

    def test_no_preference_returns_70(self):
        p = _make_product(style_type="短款")
        self.assertEqual(self._fn(None, p), 70)

    def test_tokenized_overlap_returns_86(self):
        # Preference "户外", product has function_feature "户外" → overlap=1 → 80+6=86
        p = _make_product(style_type="巴恩风/工装风", function_features=["户外"])
        self.assertEqual(self._fn("户外", p), 86)

    def test_no_token_overlap_no_similarity_returns_52(self):
        # "短款" vs "中长款大衣" — no overlap, low difflib ratio
        p = _make_product(style_type="中长款大衣")
        self.assertEqual(self._fn("短款", p), 52)

    def test_two_token_overlaps_returns_92(self):
        # Preference "面包服运动", product style="面包服", function=["运动"] → overlap=2 → 80+12=92
        p = _make_product(style_type="面包服", function_features=["运动"])
        self.assertEqual(self._fn("面包服运动", p), 92)


# ---------------------------------------------------------------------------
# 10. score_brand golden cases
# ---------------------------------------------------------------------------

class TestScoreBrand(unittest.TestCase):

    def _fn(self, brand_pref, product):
        from app.recommendation import score_brand
        return score_brand(brand_pref, product)

    # Long Chinese prefix ensures infer_brand_name returns None for the full title
    # (len > 18 triggers the None path in normalize_brand_name), so keyword count
    # goes purely through title_text.count(), without triggering exact or partial
    # brand-text match.
    _LONG_PREFIX = "这是一个测试商品标题用于测试"  # 14 CJK chars

    def test_no_preference_returns_none(self):
        p = _make_product(title="普通羽绒服")
        self.assertIsNone(self._fn(None, p))

    def test_empty_preference_returns_none(self):
        p = _make_product(title="普通羽绒服")
        self.assertIsNone(self._fn("", p))

    def test_match_count_1_returns_84(self):
        p = _make_product(title=f"{self._LONG_PREFIX}AATEST羽绒服")
        self.assertEqual(self._fn("AATEST", p), 84)

    def test_match_count_2_returns_92(self):
        p = _make_product(title=f"{self._LONG_PREFIX}AATEST AATEST羽绒服")
        self.assertEqual(self._fn("AATEST", p), 92)

    def test_match_count_4_returns_96(self):
        p = _make_product(title=f"{self._LONG_PREFIX}AATEST AATEST AATEST AATEST")
        self.assertEqual(self._fn("AATEST", p), 96)

    def test_no_match_with_product_brand_returns_34(self):
        # Product has a recognized brand (BBTEST via tag) that doesn't match AATEST
        p = _make_product(title="普通羽绒服", style_features=["品牌:BBTEST"])
        self.assertEqual(self._fn("AATEST", p), 34)

    def test_no_match_no_product_brand_returns_42(self):
        # Title >18 chars → normalize_brand_name returns None → no product_brand.
        # AATEST not in title → match_count=0, product_brand=None → score=42.
        p = _make_product(
            title="这是一个完全没有任何品牌信息的普通商品标题内容",  # 22 chars
            style_features=[],
        )
        self.assertEqual(self._fn("AATEST", p), 42)

    def test_exact_match_returns_high_score(self):
        # Title must be >18 chars so normalize_brand_name returns None for the title,
        # allowing get_product_brand to fall through to the "品牌:" style_features tag.
        p = _make_product(
            title="这件是一款经典冬季保暖羽绒服新款上市推荐",  # 20 chars
            style_features=["品牌:波司登"],
        )
        score = self._fn("波司登", p)
        self.assertGreaterEqual(score, 98)

    def test_brand_score_monotone_with_match_count(self):
        p1 = _make_product(pid=1, title=f"{self._LONG_PREFIX}CCTEST羽绒服")
        p4 = _make_product(pid=4, title=f"{self._LONG_PREFIX}CCTEST CCTEST CCTEST CCTEST")
        s1 = self._fn("CCTEST", p1)
        s4 = self._fn("CCTEST", p4)
        self.assertLess(s1, s4)


# ---------------------------------------------------------------------------
# 11. score_personality
# ---------------------------------------------------------------------------

class TestScorePersonality(unittest.TestCase):

    def _fn(self, mbti, product):
        from app.recommendation import score_personality
        return score_personality(mbti, product)

    def test_none_mbti_returns_none(self):
        p = _make_product()
        self.assertIsNone(self._fn(None, p))

    def test_empty_mbti_returns_none(self):
        p = _make_product()
        self.assertIsNone(self._fn("", p))

    def test_intj_outdoor_product_returns_score(self):
        # INTJ: N→潮流/巴恩/面包; I→通勤/休闲/轻薄; T→通勤/户外/巴恩; J→常规/通勤/商务
        # product with 通勤+户外 features → matches I(通勤), T(通勤/户外), J(通勤) → ≥3 matches
        p = _make_product(style_type="巴恩风/工装风", function_features=["通勤", "户外"])
        score = self._fn("INTJ", p)
        self.assertIsInstance(score, int)
        self.assertGreaterEqual(score, 58)
        self.assertLessEqual(score, 100)

    def test_score_formula_base_plus_matches(self):
        # ENFP: E→运动/潮流/面包; N→潮流/巴恩/面包; F→休闲/面包/中长款; P→运动/轻薄/面包
        # Product style="面包服" → 面包服 token → matches E, N, F, P tokens → 4 unique matches
        p = _make_product(style_type="面包服", size_tags=[])
        score = self._fn("ENFP", p)
        # desired_tokens: E→{运动,潮流,面包服}, N→{潮流,巴恩风/工装风,面包服},
        #                 F→{休闲,面包服,中长款大衣}, P→{运动,轻薄款,面包服}
        # product_tokens for "面包服": {"面包服"}
        # matches = len(desired & {"面包服"}) → 1 (面包服 is in desired)
        self.assertEqual(score, 58 + 1 * 8)  # 66


# ---------------------------------------------------------------------------
# 12. build_score_breakdown golden cases
# ---------------------------------------------------------------------------

class TestBuildScoreBreakdown(unittest.TestCase):

    def _fn(self, **kw):
        from app.recommendation import build_score_breakdown
        return build_score_breakdown(**kw)

    def test_three_score_keys_present(self):
        total, breakdown, radar = self._fn(
            color_score=80, body_score=80, style_score=80,
            brand_score=None, personality_score=None,
        )
        self.assertIn("颜色适配度", breakdown)
        self.assertIn("身材适配度", breakdown)
        self.assertIn("款式适配度", breakdown)
        self.assertNotIn("品牌偏好度", breakdown)
        self.assertNotIn("性格适配度", breakdown)

    def test_three_score_total_uniform_inputs(self):
        # All same score → total should equal that score regardless of weights
        total, _, _ = self._fn(
            color_score=80, body_score=80, style_score=80,
            brand_score=None, personality_score=None,
        )
        self.assertAlmostEqual(total, 80.0, places=1)

    def test_five_score_keys_present(self):
        _, breakdown, _ = self._fn(
            color_score=80, body_score=80, style_score=80,
            brand_score=80, personality_score=80,
        )
        self.assertIn("品牌偏好度", breakdown)
        self.assertIn("性格适配度", breakdown)

    def test_five_score_total_uniform_inputs(self):
        total, _, _ = self._fn(
            color_score=80, body_score=80, style_score=80,
            brand_score=80, personality_score=80,
        )
        self.assertAlmostEqual(total, 80.0, places=1)

    def test_weights_color_dominates(self):
        # color=100, body=0, style=0, no brand/pers → (100*0.34) / 0.80 = 42.5
        total, _, _ = self._fn(
            color_score=100, body_score=0, style_score=0,
            brand_score=None, personality_score=None,
        )
        self.assertAlmostEqual(total, 42.5, places=1)

    def test_weights_with_all_five(self):
        # color=100, body=0, style=0, brand=0, pers=0 → 34/1.0 = 34.0
        total, _, _ = self._fn(
            color_score=100, body_score=0, style_score=0,
            brand_score=0, personality_score=0,
        )
        self.assertAlmostEqual(total, 34.0, places=1)

    def test_radar_chart_structure(self):
        _, breakdown, radar = self._fn(
            color_score=80, body_score=70, style_score=60,
            brand_score=None, personality_score=None,
        )
        self.assertIsInstance(radar, list)
        self.assertEqual(len(radar), len(breakdown))
        for entry in radar:
            self.assertIn("dimension", entry)
            self.assertIn("score", entry)
            self.assertIn(entry["dimension"], breakdown)
            self.assertEqual(entry["score"], breakdown[entry["dimension"]])

    def test_breakdown_scores_match_inputs(self):
        _, breakdown, _ = self._fn(
            color_score=90, body_score=80, style_score=70,
            brand_score=None, personality_score=None,
        )
        self.assertEqual(breakdown["颜色适配度"], 90)
        self.assertEqual(breakdown["身材适配度"], 80)
        self.assertEqual(breakdown["款式适配度"], 70)


# ---------------------------------------------------------------------------
# 13. infer_product_gender
# ---------------------------------------------------------------------------

class TestInferProductGender(unittest.TestCase):

    def _fn(self, title):
        from app.recommendation import infer_product_gender
        return infer_product_gender(title)

    def test_unisex_keyword_wins(self):
        self.assertEqual(self._fn("男女同款冬季羽绒服"), "unisex")

    def test_male_marker_only(self):
        self.assertEqual(self._fn("【男款】冬季羽绒服保暖款"), "male")

    def test_female_marker_only(self):
        self.assertEqual(self._fn("【女款】冬季羽绒服保暖款"), "female")

    def test_both_markers_is_not_unisex(self):
        # Both 【男款】 and 【女款】 present but no unisex keyword → rightmost wins
        result = self._fn("【男款】【女款】冬季羽绒服")
        self.assertIn(result, ("male", "female"))

    def test_male_keyword(self):
        self.assertEqual(self._fn("男士冬季羽绒服"), "male")

    def test_female_keyword(self):
        self.assertEqual(self._fn("女士冬季羽绒服"), "female")

    def test_rightmost_keyword_wins(self):
        # "男士" at start, "女士" later → female wins
        self.assertEqual(self._fn("男士女士都可以穿的冬季羽绒服"), "female")

    def test_no_keyword_returns_unknown(self):
        self.assertEqual(self._fn("冬季保暖外套"), "unknown")

    def test_child_title_has_no_special_gender(self):
        # Child keywords don't affect gender detection (is_child_product is separate)
        result = self._fn("男童冬季羽绒服")
        self.assertIn(result, ("male", "female", "unisex", "unknown"))


# ---------------------------------------------------------------------------
# 14. filter_products_by_gender
# ---------------------------------------------------------------------------

class TestFilterProductsByGender(unittest.TestCase):

    def _fn(self, products, user_gender):
        from app.recommendation import filter_products_by_gender
        return filter_products_by_gender(products, user_gender)

    def test_no_gender_returns_all_no_fallback(self):
        products = [_make_product(pid=i, title="冬季羽绒服") for i in range(3)]
        result, fallback = self._fn(products, None)
        self.assertEqual(len(result), 3)
        self.assertFalse(fallback)

    def test_male_filter_returns_male_and_unisex(self):
        male = _make_product(pid=1, title="男士冬季羽绒服")
        female = _make_product(pid=2, title="女士冬季羽绒服")
        unisex = _make_product(pid=3, title="男女同款羽绒服")
        result, fallback = self._fn([male, female, unisex], "male")
        ids = {p.id for p in result}
        self.assertIn(1, ids)
        self.assertIn(3, ids)
        self.assertNotIn(2, ids)
        self.assertFalse(fallback)

    def test_female_filter_returns_female_and_unisex(self):
        male = _make_product(pid=1, title="男士冬季羽绒服")
        female = _make_product(pid=2, title="女士冬季羽绒服")
        unisex = _make_product(pid=3, title="男女同款羽绒服")
        result, fallback = self._fn([male, female, unisex], "female")
        ids = {p.id for p in result}
        self.assertIn(2, ids)
        self.assertIn(3, ids)
        self.assertNotIn(1, ids)

    def test_fallback_when_only_unknown_gender_products(self):
        # No specific-gender or unisex products → fallback to unknown-gender products
        unknown = _make_product(pid=1, title="冬季外套")  # no gender keyword
        result, fallback = self._fn([unknown], "male")
        self.assertEqual(len(result), 1)
        self.assertTrue(fallback)

    def test_empty_list_returns_empty(self):
        result, fallback = self._fn([], "female")
        self.assertEqual(result, [])
        self.assertFalse(fallback)


# ---------------------------------------------------------------------------
# 15. filter_adult_products
# ---------------------------------------------------------------------------

class TestFilterAdultProducts(unittest.TestCase):

    def _fn(self, products):
        from app.recommendation import filter_adult_products
        return filter_adult_products(products)

    def test_adult_products_returned_no_fallback(self):
        adult = _make_product(pid=1, title="男士羽绒服")
        result, fallback = self._fn([adult])
        self.assertEqual(len(result), 1)
        self.assertFalse(fallback)

    def test_child_products_excluded(self):
        adult = _make_product(pid=1, title="男士羽绒服")
        child = _make_product(pid=2, title="男童冬季羽绒服")
        result, fallback = self._fn([adult, child])
        ids = {p.id for p in result}
        self.assertIn(1, ids)
        self.assertNotIn(2, ids)
        self.assertFalse(fallback)

    def test_all_children_returns_all_with_fallback(self):
        children = [
            _make_product(pid=1, title="男童冬季羽绒服"),
            _make_product(pid=2, title="女童保暖外套"),
        ]
        result, fallback = self._fn(children)
        self.assertEqual(len(result), 2)
        self.assertTrue(fallback)

    def test_empty_list_returns_empty_with_fallback(self):
        # Empty input → no adult products found → fallback=True (same path as all-children)
        result, fallback = self._fn([])
        self.assertEqual(result, [])
        self.assertTrue(fallback)


# ---------------------------------------------------------------------------
# 16. URL helpers
# ---------------------------------------------------------------------------

class TestBuildPublicImageUrl(unittest.TestCase):

    def _fn(self, image_path):
        from app.recommendation import build_public_image_url
        return build_public_image_url(image_path)

    def test_http_url_passthrough(self):
        url = "http://example.com/img.jpg"
        self.assertEqual(self._fn(url), url)

    def test_https_url_passthrough(self):
        url = "https://cdn.example.com/img/product.jpg"
        self.assertEqual(self._fn(url), url)

    def test_relative_path_no_env_uses_static(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PUBLIC_IMAGE_BASE_URL", None)
            result = self._fn("products/coat.jpg")
        self.assertTrue(result.startswith("/static/products/"))
        self.assertIn("coat.jpg", result)

    def test_relative_path_with_env_uses_base_url(self):
        with patch.dict(os.environ, {"PUBLIC_IMAGE_BASE_URL": "https://img.test.com"}):
            result = self._fn("products/coat.jpg")
        self.assertTrue(result.startswith("https://img.test.com/"))
        self.assertIn("coat.jpg", result)

    def test_backslash_path_normalized(self):
        os.environ.pop("PUBLIC_IMAGE_BASE_URL", None)
        result = self._fn(r"products\coat.jpg")
        self.assertNotIn("\\", result)


class TestResolveProductUrl(unittest.TestCase):

    def _fn(self, product):
        from app.recommendation import resolve_product_url
        return resolve_product_url(product)

    def test_with_product_url_returns_it(self):
        p = _make_product(product_url="https://item.jd.com/12345.html")
        self.assertEqual(self._fn(p), "https://item.jd.com/12345.html")

    def test_without_product_url_returns_search_url(self):
        p = _make_product(product_url=None, title="男士羽绒服精品款",
                           image_path="downloaded_jd_images/coat.jpg")
        result = self._fn(p)
        self.assertTrue(result.startswith("http"))
        # Should be a JD or Taobao search URL
        self.assertTrue("jd.com" in result or "taobao.com" in result)

    def test_none_product_url_does_not_return_empty(self):
        p = _make_product(product_url=None)
        result = self._fn(p)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)


# ---------------------------------------------------------------------------
# 17. _sanitize_error_for_log redaction cases
# ---------------------------------------------------------------------------

class TestSanitizeErrorForLog(unittest.TestCase):

    def _fn(self, message):
        from app.recommendation import _sanitize_error_for_log
        return _sanitize_error_for_log(Exception(message))

    def test_bearer_token_redacted(self):
        raw = "Request failed: Authorization: Bearer my-secret-token-abc123"
        result = self._fn(raw)
        self.assertNotIn("my-secret-token-abc123", result)
        self.assertIn("[REDACTED]", result)

    def test_api_key_header_redacted(self):
        raw = "HTTP 401: api-key: abcdefghijklmnop"
        result = self._fn(raw)
        self.assertNotIn("abcdefghijklmnop", result)
        self.assertIn("[REDACTED]", result)

    def test_query_string_key_redacted(self):
        raw = "Error from https://api.example.com/v1?key=AIzaSyD-SECRET"
        result = self._fn(raw)
        self.assertNotIn("AIzaSyD-SECRET", result)
        self.assertIn("[REDACTED]", result)

    def test_base64_data_url_redacted(self):
        raw = "Inline image data:image/jpeg;base64," + "A" * 80
        result = self._fn(raw)
        self.assertNotIn("A" * 80, result)
        self.assertIn("[REDACTED]", result)

    def test_long_message_truncated_to_300(self):
        raw = "x" * 500
        result = self._fn(raw)
        self.assertLessEqual(len(result), 305)  # 300 + "..."

    def test_short_harmless_message_preserved(self):
        raw = "Connection timeout after 30s"
        result = self._fn(raw)
        self.assertIn("timeout", result)

    def test_bearer_equals_sign_variant_redacted(self):
        raw = "Header set: Authorization=Bearer ghp_xxxxxxxxxxxx"
        result = self._fn(raw)
        self.assertNotIn("ghp_xxxxxxxxxxxx", result)


if __name__ == "__main__":
    unittest.main()
