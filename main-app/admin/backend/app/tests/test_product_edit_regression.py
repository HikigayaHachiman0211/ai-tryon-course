from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.routers import products


def test_product_update_preserves_or_replaces_image(monkeypatch):
    product = SimpleNamespace(id=1, title="外套", price=10, image_path="old.png", product_url=None,
                              style_type="日常休闲", color_family="黑色", body_fit="常规",
                              style_features=["简约"], function_features=["保暖"], size_tags=[], size_notes=None)
    db = SimpleNamespace(get=lambda *_: product, commit=lambda: None, refresh=lambda _: None)
    monkeypatch.setattr(products, "get_settings", lambda: SimpleNamespace(PUBLIC_IMAGE_BASE_URL="https://example.test"))
    monkeypatch.setattr(products, "request_locale", lambda *_args, **_kwargs: "en")

    products.update_product(1, products.ProductUpdate(price=20), None, db=db)
    assert product.image_path == "old.png"
    result = products.update_product(1, products.ProductUpdate(image_path="new.png"), None, db=db)
    assert product.image_path == "new.png" and result["image_url"].endswith("/new.png")
    assert result["canonical"]["color_family"] == "黑色"
    for value in (None, "", "  "):
        with pytest.raises(ValidationError):
            products.ProductUpdate(image_path=value)


def test_japanese_product_display_preserves_canonical_fields(monkeypatch):
    product = SimpleNamespace(id=12, title="示例商品", price=100, image_path="jacket.png", product_url=None,
                              style_type="短款", color_family="黑色系", body_fit="常规",
                              style_features=[], function_features=["防风"], size_tags=["M"], size_notes=None)
    monkeypatch.setattr(products, "get_settings", lambda: SimpleNamespace(PUBLIC_IMAGE_BASE_URL="https://example.test"))
    result = products._serialize(product, "ja")
    assert result["canonical"]["title"] == "示例商品"
    assert result["canonical"]["style_type"] == "短款"
    assert result["canonical"]["color_family"] == "黑色系"
    assert "ダウンジャケット" in result["display"]["title"]
    assert result["display"]["style_type"] == "ショートジャケット"
    assert "ブラック" in result["display"]["color_family"]


def test_admin_uses_catalog_translation_when_available(monkeypatch):
    from app.i18n import catalog

    product = SimpleNamespace(id=12, title="原始标题", price=100.0, image_path="jacket.png", product_url=None,
                              style_type="短款", color_family="黑色系", body_fit="常规",
                              style_features=[], function_features=[], size_tags=["M"], size_notes=None)
    overlay = {"title": "翻訳済みの商品", "styleType": "ショートジャケット", "colorFamily": "ブラック系",
               "bodyFit": "標準", "styleFeatures": [], "functionFeatures": [], "sizeNotes": "サイズ表"}
    monkeypatch.setattr(catalog, "load_catalog_translations", lambda _: {catalog._product_keys(product)[0]: overlay})
    monkeypatch.setattr(products, "get_settings", lambda: SimpleNamespace(PUBLIC_IMAGE_BASE_URL="https://example.test"))
    result = products._serialize(product, "ja")
    assert result["title"] == overlay["title"]
    assert result["canonical"]["title"] == product.title


def test_annotation_display_uses_japanese_without_losing_editable_values(monkeypatch):
    from app.routers import annotations

    product = SimpleNamespace(id=12, title="示例商品", price=100, image_path="jacket.png", product_url=None,
                              style_type="短款", color_family="黑色系", body_fit="常规",
                              style_features=[], function_features=[], size_tags=["M"], size_notes=None,
                              annotation_status="unreviewed", annotation_confidence=0.3,
                              last_annotated_at=None, last_annotated_by=None)
    monkeypatch.setattr(products, "get_settings", lambda: SimpleNamespace(PUBLIC_IMAGE_BASE_URL="https://example.test"))
    result = annotations._serialize_product_with_task(product, None, "ja")
    assert result["title"] != product.title
    assert result["style_type"] == "ショートジャケット"
    assert result["canonical"]["style_type"] == "短款"
    assert result["canonical"]["color_family"] == "黑色系"
