from unittest.mock import patch

from app.database import Product
from app.product_attributes import get_product_brand
from app.recommendation import recommend_products


def _products() -> list[Product]:
    return [
        Product(
            id=1,
            title="安德玛（Under Armour）羽绒服外套男子冬季立领运动休闲简约保暖锁温上衣 浅灰 3XL",
            price=839,
            image_path="downloaded_jd_images/example-1.png",
            style_type="常规短外套",
            color_family="浅灰色系",
            body_fit="常规版型，适合大多数标准身材",
            style_features=["品牌:安德玛", "运动"],
            function_features=["保暖", "防风"],
            size_tags=["3XL"],
            size_notes=None,
            product_url="https://example.test/1",
        ),
        Product(
            id=2,
            title="测试黑色羽绒服女款",
            price=499,
            image_path="downloaded_jd_images/example-2.png",
            style_type="短款",
            color_family="黑色",
            body_fit="修身版，适合纤细到标准身材",
            style_features=["休闲"],
            function_features=["保暖"],
            size_tags=["M", "L"],
            size_notes=None,
            product_url="https://example.test/2",
        ),
    ]


def _recommend(locale: str, products: list[Product] | None = None) -> dict:
    with patch(
        "app.recommendation.resolve_user_profile",
        return_value={
            "resolved_size": "M",
            "resolved_style": "短款",
            "body_shape": "标准型",
            "reasoning": "规则推断",
            "gemini_used": False,
        },
    ):
        return recommend_products(
            products=products if products is not None else _products(),
            total_catalog_count=2,
            image_bytes=None,
            mime_type=None,
            color_preference="黑色",
            brand_preference=None,
            gender="female",
            mbti=None,
            size="M",
            style_preference="短款",
            gemini_api_key=None,
            gemini_model=None,
            price_min=None,
            price_max=None,
            locale=locale,
        )


def test_locale_changes_presentation_not_ranking_or_scores() -> None:
    chinese = _recommend("zh-CN")
    english = _recommend("en")
    japanese = _recommend("ja")

    def stable(result: dict) -> list[tuple[str, float, dict]]:
        return [(item["product_key"], item["total_score"], item["canonical"]) for item in result["items"]]

    assert stable(chinese) == stable(english) == stable(japanese)
    assert english["items"][0]["display"]["title"] != chinese["items"][0]["display"]["title"]
    assert "测试" not in english["items"][0]["display"]["title"]


def test_recommendation_preserves_read_model_key() -> None:
    products = _products()
    products[1]._product_key = "stable-source-row-key"
    products[1].style_features = ["品牌:安德玛", "休闲"]
    item = _recommend("zh-CN", products)["items"][0]
    assert item["product_key"] == "stable-source-row-key"
    assert item["canonical"]["product_key"] == item["product_key"]
    assert item["canonical"]["brand"] == get_product_brand(products[1])
    assert item["canonical"]["style_features"] == products[1].style_features
    assert "好み" not in item["reason"]
