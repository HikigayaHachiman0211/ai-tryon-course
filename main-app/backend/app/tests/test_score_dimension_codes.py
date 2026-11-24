from app.product_scoring import build_score_breakdown


def test_score_dimensions_have_stable_codes_and_keep_numeric_values() -> None:
    total, breakdown, radar = build_score_breakdown(
        color_score=90,
        body_score=80,
        style_score=70,
        brand_score=60,
        personality_score=None,
    )
    assert total > 0
    assert set(breakdown) == {"颜色适配度", "身材适配度", "款式适配度", "品牌偏好度"}
    assert [point["code"] for point in radar] == ["color", "size", "style", "brand"]
    assert [point["score"] for point in radar] == [90, 80, 70, 60]
