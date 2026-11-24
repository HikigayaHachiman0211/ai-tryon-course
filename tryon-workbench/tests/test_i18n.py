from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from app import products

ROOT = Path(__file__).resolve().parents[1]


def test_workbench_runtime_and_resources_have_three_locale_contract():
    subprocess.run(["node", "--check", str(ROOT / "static/js/i18n.js")], check=True)
    subprocess.run(["node", "--check", str(ROOT / "static/js/script.js")], check=True)
    bundles = [json.loads((ROOT / "static/i18n" / f"{locale}.json").read_text(encoding="utf-8")) for locale in ("zh-CN", "en", "ja")]
    assert [bundle["meta"]["title"] for bundle in bundles]
    assert set(bundles[0]["legacy"]) == set(bundles[1]["legacy"]) == set(bundles[2]["legacy"])
    assert "localechange" in (ROOT / "static/js/i18n.js").read_text(encoding="utf-8")


def test_workbench_catalog_uses_shared_read_model_and_localizes_display():
    products.load_catalog()
    zh = products.list_products(limit=5, locale="zh-CN")
    en = products.list_products(limit=5, locale="en")
    ja = products.list_products(limit=5, locale="ja")
    assert zh["locale"] == "zh-CN"
    assert [row["product_key"] for row in zh["items"]] == [row["product_key"] for row in en["items"]] == [row["product_key"] for row in ja["items"]]
    assert [row["price"] for row in zh["items"]] == [row["price"] for row in en["items"]]
    assert all(not re.search(r"[\u3400-\u9fff]", str(row["title"])) for row in en["items"])


def test_workbench_task_locale_and_stable_codes_are_present():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    script = (ROOT / "static/js/script.js").read_text(encoding="utf-8")
    assert "fd.append('locale'" in script
    assert '"status_code"' in source
    assert '"message_code"' in source
    assert '"locale": target_locale' in source


def test_workbench_filter_options_are_localized_and_keep_stable_keys():
    products.load_catalog()
    options = products.get_filter_options("en")
    for field in ("style_types", "color_families"):
        assert options[field]
        assert all(set(item) >= {"key", "label"} for item in options[field])
        assert all(not re.search(r"[\u3400-\u9fff]", item["label"]) for item in options[field])


def test_japanese_color_filters_distinguish_catalog_color_names(monkeypatch):
    colors = ["丛林绿", "中灰色系", "乌木棕", "云墨黑", "优质白", "传奇蓝", "乔丹远红"]
    monkeypatch.setattr(products, "_CATALOG", [{"style_type": "", "color_family": color} for color in colors])
    options = products.get_filter_options("ja")["color_families"]
    labels = {option["key"]: option["label"] for option in options}
    assert set(labels) == set(colors)
    assert len(set(labels.values())) == len(colors)
    assert all(label != "その他のカラー" for label in labels.values())
    assert "グリーン" in labels["丛林绿"]
    assert "ブラック" in labels["云墨黑"]
    assert "ホワイト" in labels["优质白"]


def test_japanese_catalog_fallback_localizes_products_without_read_model():
    item = {"id": 12, "title": "中文商品", "style_type": "短款", "color_family": "黑色系",
            "body_fit": "常规", "style_features": [], "function_features": ["防风"],
            "platform_key": "jd", "product_gender": "male", "price": 100}
    localized = products._localized_item(item, "ja")
    assert "ダウンジャケット" in localized["title"]
    assert localized["style_type"] == "ショートジャケット"
    assert "ブラック" in localized["color_family"] or "黒" in localized["color_family"]
    assert localized["canonical"]["price"] == 100


def test_workbench_runtime_keys_used_by_script_exist_in_all_bundles():
    script = (ROOT / "static/js/script.js").read_text(encoding="utf-8")
    bundles = [json.loads((ROOT / "static/i18n" / f"{locale}.json").read_text(encoding="utf-8")) for locale in ("zh-CN", "en", "ja")]
    keys = set(re.findall(r"uiText\(['\"](runtime\.[\w.]+)", script))
    assert keys
    for key in keys:
        for bundle in bundles:
            value = bundle
            for part in key.split("."):
                value = value[part]
            assert value


def test_workbench_root_redirect_preserves_locale_query_parameter():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert 'target = "/static/index.html"' in source
    assert 'target = f"{target}?{request.url.query}"' in source
