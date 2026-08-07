import unittest

from app.assistant.rule_extractor import (
    extract_recommend_fields,
    sanitize_recommend_fields,
)


class AssistantParamExtractionTests(unittest.TestCase):
    def test_negated_bread_style_is_not_added_to_positive_style(self):
        message = (
            "具体身材你看我上传的图片，我想要黑色的羽绒服，"
            "款式的话跟风衣一样帅一点的，不要面包服那种土土的。"
        )

        patch = sanitize_recommend_fields(message, extract_recommend_fields(message))

        self.assertEqual(patch["color_preference"], "黑色")
        self.assertEqual(patch["style_preference"], "中长款大衣")
        self.assertNotIn("面包服", patch["style_preference"])

    def test_only_negated_style_does_not_create_style_preference(self):
        message = "帮我推荐一件黑色羽绒服，但是不要面包服。"

        patch = sanitize_recommend_fields(
            message,
            {"color_preference": "黑色", "style_preference": "面包服"},
        )

        self.assertEqual(patch["color_preference"], "黑色")
        self.assertNotIn("style_preference", patch)

    def test_negated_color_is_ignored_when_positive_color_exists(self):
        message = "不要黑色，我想要白色的短款羽绒服。"

        patch = sanitize_recommend_fields(message, extract_recommend_fields(message))

        self.assertEqual(patch["color_preference"], "白色")
        self.assertEqual(patch["style_preference"], "短款")

    def test_invalid_llm_values_are_removed_or_normalized(self):
        message = "想要女款、预算五百以内、类似风衣的羽绒服。"

        patch = sanitize_recommend_fields(
            message,
            {
                "gender": "woman",
                "color_preference": "赛博霓虹黑",
                "brand_preference": "宇宙第一大牌",
                "size": "超大",
                "price_min": -100,
                "price_max": "500",
                "style_preference": "风衣感",
                "mbti": "abcd",
                "ai_provider": "made-up",
                "vision_provider": "made-up",
                "mimo_model": "made-up",
            },
        )

        self.assertEqual(patch["gender"], "female")
        self.assertEqual(patch["price_max"], 500)
        self.assertEqual(patch["style_preference"], "中长款大衣")
        self.assertNotIn("color_preference", patch)
        self.assertNotIn("brand_preference", patch)
        self.assertNotIn("size", patch)
        self.assertNotIn("price_min", patch)
        self.assertNotIn("mbti", patch)
        self.assertNotIn("ai_provider", patch)
        self.assertNotIn("vision_provider", patch)
        self.assertNotIn("mimo_model", patch)


if __name__ == "__main__":
    unittest.main()
