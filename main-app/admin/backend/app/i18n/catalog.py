from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


STYLE_LABELS = {
    "短款": ("Cropped jacket", "ショートジャケット"),
    "常规短外套": ("Regular short jacket", "レギュラーショートジャケット"),
    "绗缝款（排骨款）": ("Quilted jacket", "キルティングジャケット"),
    "面包服": ("Puffer jacket", "パファージャケット"),
    "长款": ("Long jacket", "ロングジャケット"),
    "轻薄款": ("Lightweight jacket", "ライトウェイトジャケット"),
    "巴恩风/工装风": ("Workwear jacket", "ワークウェアジャケット"),
    "中长款大衣": ("Mid-length coat", "ミドル丈コート"),
    "马甲": ("Down vest", "ダウンベスト"),
    "派克大衣": ("Parka", "パーカ"),
    "户外运动": ("Outdoor", "アウトドア"), "商务通勤": ("Business", "ビジネス"),
    "日常休闲": ("Casual", "カジュアル"), "时尚潮流": ("Fashion", "ファッション"),
    "轻薄便携": ("Lightweight", "軽量"), "极寒防护": ("Extreme cold", "極寒対応"),
    "亲子家庭": ("Family", "ファミリー"),
}
COLOR_LABELS = {
    "黑": ("Black", "ブラック"), "白": ("White", "ホワイト"),
    "灰": ("Gray", "グレー"), "蓝": ("Blue", "ブルー"),
    "绿": ("Green", "グリーン"), "红": ("Red", "レッド"),
    "棕": ("Brown", "ブラウン"), "咖": ("Brown", "ブラウン"),
    "卡其": ("Khaki", "カーキ"), "粉": ("Pink", "ピンク"),
    "紫": ("Purple", "パープル"), "橙": ("Orange", "オレンジ"),
    "黄": ("Yellow", "イエロー"), "米": ("Beige", "ベージュ"),
}
FEATURE_LABELS = {
    "保暖": ("Warmth", "保温"), "防风": ("Windproof", "防風"),
    "防水": ("Waterproof", "防水"), "防泼水": ("Water-repellent", "撥水"),
    "连帽": ("Hooded", "フード付き"), "轻薄": ("Lightweight", "軽量"),
    "加厚": ("Extra insulation", "厚手"), "立领": ("Stand collar", "スタンドカラー"),
}


@lru_cache(maxsize=2)
def load_catalog_translations(locale: str) -> dict[str, dict[str, Any]]:
    here = Path(__file__).resolve()
    candidates = [here.parents[2] / "catalog-translations" / f"{locale}.json"]
    if len(here.parents) > 4:
        candidates.append(here.parents[4] / "backend" / "app" / "i18n" / "catalog-translations" / f"{locale}.json")
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            items = payload.get("items", {})
            if isinstance(items, dict):
                return items
        except (OSError, ValueError, AttributeError):
            continue
    return {}


def _product_keys(product: Any) -> list[str]:
    price = str(product.price)
    try:
        prices = list(dict.fromkeys((f"{float(product.price):g}", price, str(float(product.price)))))
    except (TypeError, ValueError):
        prices = [price]
    def normalize(value: object) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip())
    return [
        hashlib.sha256("\x1f".join((normalize(product.title), normalize(value), normalize(product.image_path))).encode("utf-8")).hexdigest()[:24]
        for value in prices
    ]


def localized_product_display(product: Any, locale: str) -> dict[str, Any] | None:
    if locale not in ("en", "ja"):
        return None
    translations = load_catalog_translations(locale)
    translated = next((translations[key] for key in _product_keys(product) if key in translations), None)
    if translated:
        return {
            "title": translated["title"], "style_type": translated["styleType"],
            "color_family": translated["colorFamily"], "body_fit": translated["bodyFit"],
            "style_features": translated["styleFeatures"], "function_features": translated["functionFeatures"],
            "size_tags": product.size_tags, "size_notes": translated["sizeNotes"],
        }

    index = 0 if locale == "en" else 1
    style = STYLE_LABELS.get(product.style_type, ("Down jacket", "ダウンジャケット"))[index]
    color_source = str(product.color_family or "")
    color = next((labels[index] for key, labels in COLOR_LABELS.items() if key in color_source), "Color unspecified" if locale == "en" else "カラー未指定")
    if locale == "ja" and color_source.endswith("系") and color != "カラー未指定":
        color += "系"
    title = f"{style} down jacket — {color} (#{product.id})" if locale == "en" else f"{style} ダウンジャケット — {color} (#{product.id})"
    def features(values: list[str] | None) -> list[str]:
        return [FEATURE_LABELS[value][index] for value in values or [] if value in FEATURE_LABELS]
    return {
        "title": title, "style_type": style, "color_family": color,
        "body_fit": "See the size chart" if locale == "en" else "サイズ表をご確認ください",
        "style_features": features(product.style_features), "function_features": features(product.function_features),
        "size_tags": product.size_tags, "size_notes": "See the size chart." if locale == "en" else "サイズ表をご確認ください。",
    }
