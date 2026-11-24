from app.database import build_product
from app.i18n.catalog import (build_product_display, localize_product_item, localize_product_payload, localize_style_lab_result,
                              localize_recommendation_result, localized_reason, product_key_from_row)
from app.product_attributes import build_public_image_url


ROW = {
    "商品标题": "安德玛（Under Armour）羽绒服外套男子冬季立领运动休闲简约保暖锁温上衣 浅灰 3XL",
    "价格": 839,
    "图片路径": "downloaded_jd_images/example.png",
    "款式类型": "常规短外套",
    "精准颜色色系": "浅灰色系",
    "版型与身材适配度": "常规版型，适合大多数标准身材",
    "风格特征": ["品牌:安德玛", "运动"],
    "功能属性": ["保暖", "防风"],
}


def test_product_key_is_deterministic_and_not_a_list_position() -> None:
    assert product_key_from_row(ROW) == product_key_from_row(dict(ROW))
    assert len(product_key_from_row(ROW)) == 24
    assert product_key_from_row(ROW) != product_key_from_row({**ROW, "价格": 840})


def test_product_display_has_complete_non_chinese_target_fields() -> None:
    product = build_product(ROW)
    display = build_product_display(product, "en")

    assert set(display) == {
        "title",
        "styleType",
        "colorFamily",
        "bodyFit",
        "styleFeatures",
        "functionFeatures",
        "sizeNotes",
    }
    assert display["title"]
    assert display["styleType"] == "Regular short jacket"
    assert display["colorFamily"] == "Light gray"
    assert display["functionFeatures"] == ["Warmth", "Windproof"]
    assert "适合" not in display["bodyFit"]


def test_japanese_display_uses_japanese_templates_without_source_fallback() -> None:
    product = build_product(ROW)
    display = build_product_display(product, "ja")
    assert "ダウンジャケット" in display["title"]
    assert display["styleType"] == "レギュラーショートジャケット"
    assert display["functionFeatures"] == ["保温", "防風"]


def test_japanese_recommendation_reason_localizes_canonical_preferences() -> None:
    product = localize_product_payload(build_product(ROW), "zh-CN")
    result = {"items": [product], "request": {"color_preference": "黑色"}, "inference": {"resolved_style": "短款"}}
    reason = localize_recommendation_result(result, "ja")["items"][0]["reason"]
    assert "黑色" not in reason
    assert "短款" not in reason
    assert "ブラック" in reason
    assert "ショートジャケット" in reason
    assert "系系" not in reason


def test_current_result_can_be_relocalized_without_changing_product_identity() -> None:
    from starlette.requests import Request
    from app import main

    assert hasattr(main, "localize_current_result")
    assert hasattr(main, "LocalizeResultRequest")
    product = localize_product_payload(build_product(ROW), "zh-CN")
    product["total_score"] = 87
    original = {"locale": "zh-CN", "items": [product], "inference": {"resolved_style": "短款"}, "user_photo_url": "/photo"}
    request = Request({"type": "http", "headers": [(b"accept-language", b"en")]})
    body = main.LocalizeResultRequest(kind="recommend", result=original, locale="ja")
    result = main.localize_current_result(request, body)
    assert result["locale"] == "ja"
    assert result["items"][0]["product_key"] == product["product_key"]
    assert result["items"][0]["total_score"] == 87
    assert result["user_photo_url"] == "/photo"
    assert "ダウンジャケット" in result["items"][0]["title"]


def test_score_dimensions_survive_repeated_language_switches() -> None:
    product = localize_product_payload(build_product(ROW), "zh-CN")
    product["score_breakdown"] = {"颜色适配度": 82, "款式适配度": 73, "价格适配度": 64}
    result = {"locale": "zh-CN", "items": [product], "inference": {}}
    for locale in ("en", "ja", "zh-CN"):
        result = localize_recommendation_result(result, locale)
        assert sorted(result["items"][0]["score_breakdown"].values()) == [64, 73, 82]


def test_product_and_chinese_reason_survive_repeated_localization(monkeypatch) -> None:
    monkeypatch.delenv("PUBLIC_IMAGE_BASE_URL", raising=False)
    product = build_product({**ROW, "图片路径": "downloaded_jd_images/example%20file.png"})
    product.id = 42
    product._product_key = "stable-collision-key"
    initial = localize_product_payload(product, "zh-CN")
    initial["reason"] = "原始中文推荐理由"
    result = {"items": [initial], "inference": {}}
    result = localize_recommendation_result(result, "zh-CN")
    expected = result["items"][0]["canonical"]
    assert result["items"][0]["reason"] == "原始中文推荐理由"
    for locale in ("en", "ja", "zh-CN"):
        result = localize_recommendation_result(result, locale)
        item = result["items"][0]
        assert item["canonical"] == expected
        assert item["id"] == 42 and item["product_key"] == "stable-collision-key"
        assert item["image_url"] == expected["image_url"]
        assert item["price"] == expected["price"]
    assert result["items"][0]["reason"] == "原始中文推荐理由"
    assert "主な機能" not in localized_reason({"display": {}}, "zh-CN")
    legacy = localize_recommendation_result({"items": [{"title": "Jacket", "price": 1, "locale": "en", "reason": "English only"}]}, "zh-CN")
    assert "English only" not in legacy["items"][0]["reason"]
    assert "主要特点" in legacy["items"][0]["reason"]


def test_image_urls_remain_stable_when_already_public(monkeypatch) -> None:
    monkeypatch.delenv("PUBLIC_IMAGE_BASE_URL", raising=False)
    for value in ("/static/products/test/a%20b.png", "https://cdn.example/a%20b.png"):
        assert build_public_image_url(value) == value
    assert build_public_image_url("test/a%20b.png") == "/static/products/test/a%20b.png"


def test_style_lab_keeps_its_own_chinese_reason_across_locales() -> None:
    product = localize_product_payload(build_product(ROW), "zh-CN")
    product["canonical"]["reason"] = "商品推荐理由"
    result = {
        "locale": "zh-CN",
        "product": product,
        "inference": {"resolved_size": "XL", "resolved_style": "短款", "body_shape": "标准"},
        "analysis": {"reason": "独立搭配分析理由"},
    }
    for locale in ("en", "ja", "zh-CN"):
        result = localize_style_lab_result(result, locale)
        if locale == "en":
            assert result["inference"]["display"]["style"]
    assert result["analysis"]["reason"] == "独立搭配分析理由"


def test_duplicate_source_rows_keep_distinct_read_model_keys() -> None:
    products = [build_product(ROW), build_product(ROW)]
    for index, product in enumerate(products):
        product.id = index + 1
        product._product_key = f"stable-row-{index}"
    localized = [localize_product_item(localize_product_payload(product, "en"), "ja") for product in products]
    assert [item["product_key"] for item in localized] == ["stable-row-0", "stable-row-1"]
