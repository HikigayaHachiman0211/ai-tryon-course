from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException


def test_sample_models_endpoint_serves_valid_images_and_rejects_traversal(client) -> None:
    from app.main import get_sample_model_image

    response = client.get("/sample-models/male/mannequin-male-1.png")
    assert response.status_code == 200
    assert len(response.content) > 100

    invalid_gender = client.get("/sample-models/other/mannequin-male-1.png")
    assert invalid_gender.status_code == 400

    missing_file = client.get("/sample-models/male/does-not-exist.webp")
    assert missing_file.status_code == 404

    dotdot = client.get("/sample-models/male/..")
    assert dotdot.status_code in (400, 404)

    backslash_traversal = client.get("/sample-models/male/..%5C..%5Cmain.py")
    assert backslash_traversal.status_code == 400

    nested_path = client.get("/sample-models/male/nested/mannequin-male-1.png")
    assert nested_path.status_code == 404

    with pytest.raises(HTTPException) as exc_info:
        get_sample_model_image("male", "../main.py")
    assert exc_info.value.status_code == 400


def test_recommend_and_style_lab_accept_urlencoded_without_photo(client) -> None:
    stub_profile = {
        "resolved_size": "L",
        "resolved_style": "短款",
        "body_shape": "标准型",
        "size_source": "user_input",
        "style_source": "user_input",
        "reasoning": "规则推断",
        "gemini_model": "",
        "gemini_used": False,
        "ai_provider": "rule",
        "rule_fallback_used": True,
    }
    products = client.get("/api/products", params={"limit": 1}).json()["items"]
    stub_product = client.app
    del stub_product

    from conftest import _make_stub_product

    with (
        patch("app.recommendation.resolve_user_profile", return_value=stub_profile),
        patch("app.main.get_catalog_product", return_value=_make_stub_product(products[0]["id"])),
        patch("app.admin_report.report_request_log", return_value=None),
        patch("app.admin_report.report_user_profile", return_value=None),
    ):
        rec_res = client.post(
            "/api/recommend",
            data={
                "color_preference": "黑色",
                "gender": "male",
                "locale": "zh-CN",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert rec_res.status_code == 200
        rec_json = rec_res.json()
        assert len(rec_json["items"]) >= 1

        lab_res = client.post(
            "/api/style-lab/analyze",
            data={
                "product_id": str(products[0]["id"]),
                "color_preference": "黑色",
                "gender": "male",
                "locale": "en",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert lab_res.status_code == 200
        lab_json = lab_res.json()
        assert lab_json["locale"] == "en"
        assert "analysis" in lab_json
