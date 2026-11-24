from __future__ import annotations

import hashlib
import re
from typing import Any

from app.database import Product
from app.product_attributes import (
    build_public_image_url,
    get_product_brand,
    get_product_platform_key,
    get_product_platform,
    resolve_product_url,
)
from app.recommendation_rules import infer_product_gender
from .domain_labels import (
    display_brand,
    localized_gender,
    localized_platform,
    localized_score_label,
    localized_body_shape,
    localized_color,
    localized_style,
    product_display_fields,
    score_dimension_code,
)
from .catalog_assets import get_catalog_translation


def _normalize_key_part(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def product_key_from_row(row: dict[str, Any]) -> str:
    source = "\x1f".join(
        [
            _normalize_key_part(row.get("商品标题")),
            _normalize_key_part(row.get("价格")),
            _normalize_key_part(row.get("图片路径")),
        ]
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]


def product_key_for_row(row: dict[str, Any], collision_index: int = 0) -> str:
    """Return the guide-defined key and a deterministic collision variant.

    The source dataset contains repeated rows with the same title/price/image
    triple.  The base key remains exactly the specified SHA-256 value; only a
    repeated occurrence receives a digest of the base plus its stable source
    occurrence so the read model can still represent every source record.
    """
    base = product_key_from_row(row)
    if collision_index <= 0:
        return base
    return hashlib.sha256(f"{base}\x1f{collision_index}".encode("utf-8")).hexdigest()[:24]


def product_key_for_product(product: Product) -> str:
    existing = getattr(product, "_product_key", None)
    if existing:
        return str(existing)
    source = "\x1f".join(
        [
            _normalize_key_part(product.title),
            _normalize_key_part(f"{product.price:g}"),
            _normalize_key_part(product.image_path),
        ]
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]


def build_product_display(product: Product, locale: str) -> dict[str, object]:
    return product_display_fields(product, locale, product_key_for_product(product))


def localize_product_payload(product: Product, locale: str) -> dict[str, Any]:
    product_key = product_key_for_product(product)
    display = get_catalog_translation(product_key, locale) or product_display_fields(product, locale, product_key)
    display = {key: display[key] for key in ("title", "styleType", "colorFamily", "bodyFit", "styleFeatures", "functionFeatures", "sizeNotes") if key in display}
    product_gender = infer_product_gender(product.title)
    platform_key = get_product_platform_key(product)
    return {
        "id": product.id,
        "product_key": product_key,
        "locale": locale,
        "canonical": {
            "id": product.id,
            "product_key": product_key,
            "price": product.price,
            "image_url": build_public_image_url(product.image_path),
            "product_url": resolve_product_url(product),
            "platform": platform_key,
            "gender": product_gender,
            "brand": get_product_brand(product),
            "title": product.title,
            "image_path": product.image_path,
            "style_type": product.style_type,
            "color_family": product.color_family,
            "body_fit": product.body_fit,
            "style_features": list(product.style_features or []),
            "function_features": list(product.function_features or []),
            "size_tags": list(product.size_tags or []),
            "size_notes": product.size_notes,
        },
        "display": display,
        "title": display["title"],
        "price": product.price,
        "image_url": build_public_image_url(product.image_path),
        "brand": display_brand(product, locale),
        "platform": localized_platform(platform_key, locale),
        "product_url": resolve_product_url(product),
        "style_type": display["styleType"],
        "color_family": display["colorFamily"],
        "body_fit": display["bodyFit"],
        "style_features": display["styleFeatures"],
        "function_features": display["functionFeatures"],
        "size_tags": list(product.size_tags or []),
        "size_notes": display["sizeNotes"],
        "product_gender": product_gender,
        "gender_label": localized_gender(product_gender, locale),
        "is_child_product": any(token in product.title for token in ("男童", "女童", "儿童", "童装", "婴童", "宝宝", "婴儿", "小童", "大童", "幼童")),
    }


def _product_from_payload(item: dict[str, Any]) -> Product:
    canonical = item.get("canonical") if isinstance(item.get("canonical"), dict) else {}
    def source(key: str, default: Any = None) -> Any:
        return canonical.get(key, item.get(key, default))

    product = Product(
        id=int(source("id") or 0),
        title=str(source("title") or "Down jacket"),
        price=float(source("price") or 0),
        image_path=str(source("image_path", source("image_url", "")) or ""),
        style_type=str(source("style_type") or ""),
        color_family=str(source("color_family") or ""),
        body_fit=str(source("body_fit") or ""),
        style_features=list(source("style_features") or []),
        function_features=list(source("function_features") or []),
        size_tags=list(source("size_tags") or []),
        size_notes=source("size_notes"),
        product_url=source("product_url"),
    )
    if source("product_key"):
        setattr(product, "_product_key", str(source("product_key")))
    return product


def localize_product_item(item: dict[str, Any], locale: str) -> dict[str, Any]:
    product = _product_from_payload(item)
    localized = localize_product_payload(product, locale)
    original = item.get("canonical") if isinstance(item.get("canonical"), dict) else {}
    localized["canonical"].update(original)
    canonical = localized["canonical"]
    if item.get("reason") and "reason" not in canonical and item.get("locale") in (None, "zh-CN"):
        canonical["reason"] = item["reason"]
    if item.get("locale") in (None, "zh-CN") and "reason" in item:
        localized["reason"] = item["reason"]
    elif canonical.get("reason"):
        localized["reason"] = canonical["reason"]
    for key in ("id", "product_key", "price", "image_url", "product_url"):
        if key in canonical:
            localized[key] = canonical[key]
    if "gender" in canonical:
        localized["product_gender"] = canonical["gender"]
        localized["gender_label"] = localized_gender(canonical["gender"], locale)
    if "platform" in canonical:
        localized["platform"] = localized_platform(canonical["platform"], locale)
    if "is_child_product" in item:
        localized["is_child_product"] = item["is_child_product"]
    for key in ("total_score", "brand_score", "gender_match_priority", "brand_exact_priority", "brand_match_count"):
        if key in item:
            localized[key] = item[key]
    if "score_breakdown" in item:
        localized["score_breakdown"] = {
            localized_score_label(score_dimension_code(str(key)), locale): value
            for key, value in dict(item["score_breakdown"]).items()
        }
    if "radar_chart" in item:
        localized["radar_chart"] = [
            {
                **point,
                "code": score_dimension_code(str(point.get("code") or point.get("dimension") or "")),
                "label": localized_score_label(score_dimension_code(str(point.get("code") or point.get("dimension") or "")), locale),
            }
            for point in item["radar_chart"]
        ]
    return localized


def localized_reason(
    item: dict[str, Any],
    locale: str,
    *,
    preferred_color: str | None = None,
    resolved_style: str | None = None,
) -> str:
    if locale == "zh-CN":
        original_reason = (item.get("canonical") or {}).get("reason") or item.get("reason")
        if original_reason:
            return str(original_reason)
    display = item.get("display") or {}
    color = display.get("colorFamily") or ("所选颜色" if locale == "zh-CN" else "the selected color" if locale == "en" else "選択した色")
    style = display.get("styleType") or ("该款式" if locale == "zh-CN" else "this style" if locale == "en" else "このスタイル")
    features = display.get("functionFeatures") or display.get("styleFeatures") or []
    feature = features[0] if features else ("warmth" if locale == "en" else "保暖性" if locale == "zh-CN" else "保温性")
    requested_color = (localized_color(preferred_color, locale) if preferred_color and locale != "zh-CN" else preferred_color) or color
    if resolved_style and locale != "zh-CN":
        resolved_style = localized_style(resolved_style, locale)
    if locale == "zh-CN":
        parts = [f"{color}与您偏好的{requested_color}搭配协调。"]
        if resolved_style:
            parts.append(f"{style}接近您偏好的{resolved_style}。")
        parts.append(f"主要特点：{feature}。")
        return "".join(parts)
    if locale == "en":
        parts = [f"The {color} color family works well with your {requested_color} preference."]
        if resolved_style:
            parts.append(f"The {style} direction is close to {resolved_style}.")
        parts.append(f"Key feature: {feature}.")
        return " ".join(parts)
    color_family = color if str(color).endswith("系") else f"{color}系"
    parts = [f"{color_family}は{requested_color}の好みと合わせやすいカラーです。"]
    if resolved_style:
        parts.append(f"{style}の方向性は{resolved_style}に近い選択です。")
    parts.append(f"主な機能：{feature}。")
    return "".join(parts)


def localize_recommendation_result(result: dict[str, Any], locale: str) -> dict[str, Any]:
    localized = dict(result)
    localized["locale"] = locale
    localized_items: list[dict[str, Any]] = []
    for raw_item in result.get("items") or []:
        item = localize_product_item(dict(raw_item), locale)
        item["reason"] = localized_reason(
            item,
            locale,
            preferred_color=str(result.get("request", {}).get("color_preference") or ""),
            resolved_style=str(result.get("inference", {}).get("resolved_style") or ""),
        )
        localized_items.append(item)
    localized["items"] = localized_items
    inference = dict(result.get("inference") or {})
    resolved_style = str(inference.get("resolved_style") or "")
    inference["reasoning"] = (
        inference.get("reasoning")
        if locale == "zh-CN"
        else f"Recommended size: {inference.get('resolved_size') or 'standard'}; style direction: {localized_style(resolved_style, locale)}."
        if locale == "en"
        else f"おすすめサイズ：{inference.get('resolved_size') or '標準'}。スタイル：{localized_style(resolved_style, locale)}。"
    )
    inference["display"] = {
        "size": inference.get("resolved_size") or "",
        "style": localized_style(resolved_style, locale),
        "bodyShape": localized_body_shape(inference.get("body_shape"), locale),
    }
    localized["inference"] = inference
    if localized.get("message") and locale != "zh-CN":
        localized["message"] = {
            "en": "No products matched the current filters.",
            "ja": "現在の条件に一致する商品がありません。",
        }[locale]
    return localized


def localize_style_lab_result(result: dict[str, Any], locale: str) -> dict[str, Any]:
    localized = dict(result)
    localized["locale"] = locale
    product = localize_product_item(dict(result.get("product") or {}), locale)
    localized["product"] = product
    analysis = dict(result.get("analysis") or {})
    if "score_breakdown" in analysis:
        analysis["score_breakdown"] = {
            localized_score_label(score_dimension_code(str(key)), locale): value
            for key, value in dict(analysis["score_breakdown"]).items()
        }
    if "radar_chart" in analysis:
        analysis["radar_chart"] = [
            {
                **point,
                "code": score_dimension_code(str(point.get("code") or point.get("dimension") or "")),
                "label": localized_score_label(score_dimension_code(str(point.get("code") or point.get("dimension") or "")), locale),
            }
            for point in analysis["radar_chart"]
        ]
    if analysis.get("reason") and "canonical_reason" not in analysis and result.get("locale") in (None, "zh-CN"):
        analysis["canonical_reason"] = analysis["reason"]
    reason_source = analysis.get("canonical_reason") if locale == "zh-CN" else analysis.get("reason")
    analysis["reason"] = localized_reason({**product, "reason": reason_source,
                                            "canonical": {**product["canonical"], "reason": reason_source}}, locale)
    if locale != "zh-CN":
        if locale == "en":
            analysis["styling_advice"] = [
                "The color family is easy to coordinate with your selected preference.",
                f"The {product['display']['styleType']} silhouette supports flexible winter layering.",
                f"Key feature: {(product['display']['functionFeatures'] or ['Warmth'])[0]}.",
            ]
            analysis["budget_note"] = "The price is shown in CNY." if analysis.get("budget_note") else None
            analysis["brand_note"] = "Brand preference match is available." if analysis.get("brand_note") else None
            analysis["gender_note"] = "Gender fit is shown in the product details." if analysis.get("gender_note") else None
            analysis["personality_note"] = "Personality fit is included in the score." if analysis.get("personality_note") else None
        else:
            analysis["styling_advice"] = [
                "好みのカラーと合わせやすい色系統です。",
                f"{product['display']['styleType']}のシルエットは冬の重ね着に向いています。",
                f"主な機能：{(product['display']['functionFeatures'] or ['保温'])[0]}。",
            ]
            analysis["budget_note"] = "価格はCNYで表示されます。" if analysis.get("budget_note") else None
            analysis["brand_note"] = "ブランド適合度は商品詳細に表示されます。" if analysis.get("brand_note") else None
            analysis["gender_note"] = "性別適合度は商品詳細に表示されます。" if analysis.get("gender_note") else None
            analysis["personality_note"] = "性格適合度はスコアに含まれます。" if analysis.get("personality_note") else None
    localized["analysis"] = analysis
    if isinstance(result.get("inference"), dict):
        inference = dict(result["inference"])
        resolved_style = str(inference.get("resolved_style") or "")
        inference["reasoning"] = (
            inference.get("reasoning")
            if locale == "zh-CN"
            else f"Recommended size: {inference.get('resolved_size') or 'standard'}; style direction: {localized_style(resolved_style, locale)}."
            if locale == "en"
            else f"おすすめサイズ：{inference.get('resolved_size') or '標準'}。スタイル：{localized_style(resolved_style, locale)}。"
        )
        inference["display"] = {
            "size": inference.get("resolved_size") or "",
            "style": localized_style(resolved_style, locale),
            "bodyShape": localized_body_shape(inference.get("body_shape"), locale),
        }
        localized["inference"] = inference
    return localized
