from __future__ import annotations

import difflib
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.catalog_seed import BRAND_ALIASES, extract_brand_tag, get_platform_label, infer_brand_name, infer_platform_key
from app.database import Product, SIZE_ORDER, normalize_size
from app.ai_runtime_config import resolve_effective_provider, resolve_provider_config
from app.llm_parsing import (
    coerce_text as _coerce_text,
    has_known_profile_field as _has_known_profile_field,
)

import re as _re_module
import urllib.parse as _urllib_parse

from app.profile_providers import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_DEEPSEEK_MODEL,
    DEEPSEEK_MODELS,
    DEEPSEEK_API_BASE,
    DEFAULT_MIMO_API_BASE,
    DEFAULT_MIMO_MODEL,
    MIMO_API_BASE,
    MIMO_API_KEY,
    MIMO_AUTH_HEADER,
    MIMO_MODELS,
    _sanitize_error_for_log,
    normalize_vision_provider,
    strip_json_block,
    call_gemini_profile,
    call_gemini_text_profile,
    call_deepseek_profile,
    call_mimo_profile,
)

from app.recommendation_rules import (
    COLOR_GROUPS,
    STYLE_TOKEN_MAP,
    STYLE_CHOICES,
    UNISEX_GENDER_KEYWORDS,
    MALE_GENDER_KEYWORDS,
    FEMALE_GENDER_KEYWORDS,
    CHILD_KEYWORDS,
    ensure_list,
    clamp_score,
    classify_color_group,
    tokenize_style_text,
    normalize_style_preference,
    normalize_body_shape,
    normalize_user_gender,
    normalize_platform_filter,
    infer_product_gender,
    is_child_product,
    filter_products_by_gender,
    filter_adult_products,
    get_gender_match_priority,
    get_gender_label,
)

from app.product_attributes import (
    build_public_image_url,
    get_product_brand,
    get_product_platform_key,
    get_product_platform,
    get_visible_style_features,
    generate_product_search_url,
    resolve_product_url,
    parse_brand_preferences,
    get_brand_keywords,
    get_brand_match_details,
)


from app.product_scoring import (
    build_score_breakdown,
    classify_user_fit,
    detect_fit_bucket,
    score_body_fit,
    score_brand,
    score_color,
    score_personality,
    score_size_tag_alignment,
    score_style,
)

from app.profile_inference import (
    build_inference_reason,
    fallback_body_shape,
    fallback_size_from_body_shape,
    infer_style_heuristically,
    resolve_user_profile,
)


def build_brand_note(brand_preference: str | None, product: Product, brand_score: int | None) -> str | None:
    preferred_brands = parse_brand_preferences(brand_preference)
    if not preferred_brands or brand_score is None:
        return None

    product_brand = get_product_brand(product)
    preference_text = "、".join(preferred_brands)
    if not product_brand:
        return f"你更偏好 {preference_text} 这类品牌，这件商品暂未识别出明确品牌，建议点开详情页再确认店铺与吊牌信息。"
    if brand_score >= 95:
        return f"这件商品品牌为 {product_brand}，与你偏好的 {preference_text} 高度一致。"
    if brand_score >= 70:
        return f"这件商品品牌为 {product_brand}，和你偏好的 {preference_text} 有一定重合度。"
    return f"这件商品品牌为 {product_brand}，与当前偏好的 {preference_text} 不算最匹配。"


def build_item_reason(
    product: Product,
    *,
    preferred_color: str,
    resolved_style: str,
    brand_preference: str | None,
    color_score: int,
    body_score: int,
    style_score: int,
    brand_score: int | None,
    personality_score: int | None,
) -> str:
    reasons: list[str] = []
    brand_note = build_brand_note(brand_preference, product, brand_score)
    if brand_note and brand_score is not None and brand_score >= 70:
        reasons.append(brand_note)
    if color_score >= 85:
        reasons.append(f"商品色系为{product.color_family}，与偏好的{preferred_color}更接近")
    elif color_score >= 65:
        reasons.append(f"商品色系为{product.color_family}，可与偏好的{preferred_color}形成相近搭配")
    else:
        reasons.append(f"这件商品的亮点不在颜色，而在版型和功能表现")

    if style_score >= 85:
        reasons.append(f"款式定位为{product.style_type}，与建议的{resolved_style}一致")
    elif style_score >= 70:
        reasons.append(f"款式定位为{product.style_type}，与建议方向比较接近")

    feature_tags = ensure_list(product.function_features) or get_visible_style_features(product)
    if feature_tags:
        reasons.append(f"功能亮点包括{'、'.join(feature_tags[:2])}")
    elif body_score >= 85:
        reasons.append(f"版型描述与当前身型更匹配：{product.body_fit}")

    if product.size_notes:
        reasons.append(f"尺码参考：{product.size_notes}")
    if personality_score is not None and personality_score >= 80:
        reasons.append("风格气质和 MBTI 偏好匹配度高")
    return "；".join(reasons[:3]) if reasons else "整体得分均衡，适合作为备选"


def extract_product_signature(title: str) -> str:
    code_match = re.search(r"\b[A-Z][A-Z0-9-]{4,}\b", title)
    if code_match:
        return code_match.group(0)

    normalized = re.sub(r"\b(?:XS|S|M|L|XL|2XL|3XL|4XL|5XL|6XL|7XL)\b", "", title.upper())
    normalized = re.sub(r"\d+[./]?\d*", "", normalized)
    normalized = re.sub(r"[\s【】\[\]（）()，,.-]+", "", normalized)
    return normalized[:36]


def recommend_products(
    *,
    products: list[Product],
    total_catalog_count: int,
    image_bytes: bytes | None,
    mime_type: str | None,
    color_preference: str,
    brand_preference: str | None,
    gender: str | None,
    mbti: str | None,
    size: str | None,
    style_preference: str | None,
    gemini_api_key: str | None,
    gemini_model: str | None,
    deepseek_api_key: str | None = None,
    deepseek_model: str | None = None,
    mimo_api_key: str | None = None,
    mimo_model: str | None = None,
    ai_provider: str | None = None,
    vision_provider: str | None = None,
    price_min: float | None,
    price_max: float | None,
) -> dict[str, Any]:
    normalized_gender = normalize_user_gender(gender)
    price_filtered_count = len(products)
    inference = resolve_user_profile(
        image_bytes=image_bytes,
        mime_type=mime_type,
        color_preference=color_preference,
        gender=normalized_gender,
        mbti=mbti,
        size=size,
        style_preference=style_preference,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        deepseek_api_key=deepseek_api_key,
        deepseek_model=deepseek_model,
        mimo_api_key=mimo_api_key,
        mimo_model=mimo_model,
        ai_provider=ai_provider,
        vision_provider=vision_provider,
    )

    if not products:
        return {
            "filters": {
                "price_min": price_min,
                "price_max": price_max,
                "catalog_total": total_catalog_count,
                "matched_after_price_filter": 0,
                "matched_after_gender_filter": 0,
                "user_gender": normalized_gender,
                "brand_preference": brand_preference,
                "gender_fallback": False,
            },
            "inference": inference,
            "items": [],
            "message": "当前价位区间没有匹配商品。",
        }

    preferred_brands = parse_brand_preferences(brand_preference)
    brand_candidate_pool, _ = filter_adult_products(products)
    products, gender_fallback = filter_products_by_gender(products, normalized_gender)
    products, audience_fallback = filter_adult_products(products)
    if preferred_brands and not any(get_brand_match_details(preferred_brands, product)[1] > 0 for product in products):
        fallback_brand_matches = [
            product
            for product in brand_candidate_pool
            if get_brand_match_details(preferred_brands, product)[1] > 0
        ]
        if fallback_brand_matches:
            products = fallback_brand_matches
            gender_fallback = True
    if not products:
        return {
            "filters": {
                "price_min": price_min,
                "price_max": price_max,
                "catalog_total": total_catalog_count,
                "matched_after_price_filter": price_filtered_count,
                "matched_after_gender_filter": 0,
                "user_gender": normalized_gender,
                "brand_preference": brand_preference,
                "gender_fallback": gender_fallback or audience_fallback,
            },
            "inference": inference,
            "items": [],
            "message": "当前筛选条件下没有匹配所选性别的商品。",
        }

    ranked_items: list[dict[str, Any]] = []
    for product in products:
        color_score = score_color(color_preference, product.color_family)
        body_score = score_body_fit(inference["resolved_size"], inference["body_shape"], product)
        style_score = score_style(inference["resolved_style"], product)
        brand_score = score_brand(brand_preference, product)
        brand_exact_priority, brand_match_count = get_brand_match_details(preferred_brands, product)
        personality_score = score_personality(mbti, product)
        total_score, breakdown, radar_chart = build_score_breakdown(
            color_score=color_score,
            body_score=body_score,
            style_score=style_score,
            brand_score=brand_score,
            personality_score=personality_score,
        )
        ranked_items.append(
            {
                "id": product.id,
                "title": product.title,
                "price": product.price,
                "image_url": build_public_image_url(product.image_path),
                "brand": get_product_brand(product),
                "platform": get_product_platform(product),
                "product_url": resolve_product_url(product),
                "style_type": product.style_type,
                "color_family": product.color_family,
                "body_fit": product.body_fit,
                "style_features": get_visible_style_features(product),
                "function_features": ensure_list(product.function_features),
                "size_tags": ensure_list(product.size_tags),
                "size_notes": product.size_notes,
                "gender_match_priority": get_gender_match_priority(product.title, normalized_gender),
                "brand_exact_priority": brand_exact_priority,
                "brand_match_count": brand_match_count,
                "total_score": total_score,
                "score_breakdown": breakdown,
                "radar_chart": radar_chart,
                "brand_score": brand_score,
                "reason": build_item_reason(
                    product,
                    preferred_color=color_preference,
                    resolved_style=inference["resolved_style"],
                    brand_preference=brand_preference,
                    color_score=color_score,
                    body_score=body_score,
                    style_score=style_score,
                    brand_score=brand_score,
                    personality_score=personality_score,
                ),
            }
        )

    sorted_items = sorted(
        ranked_items,
        key=lambda item: (
            -item["gender_match_priority"],
            -item["brand_exact_priority"],
            -item["brand_match_count"],
            -(item["brand_score"] or 0),
            -item["total_score"],
            item["price"],
        ),
    )
    top_items: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()
    for item in sorted_items:
        signature = extract_product_signature(item["title"])
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        top_items.append(item)

    for item in top_items:
        item.pop("gender_match_priority", None)
        item.pop("brand_exact_priority", None)
        item.pop("brand_match_count", None)
    return {
        "filters": {
            "price_min": price_min,
            "price_max": price_max,
            "catalog_total": total_catalog_count,
            "matched_after_price_filter": price_filtered_count,
            "matched_after_gender_filter": len(products),
            "user_gender": normalized_gender,
            "brand_preference": brand_preference,
            "gender_fallback": gender_fallback or audience_fallback,
        },
        "inference": inference,
        "items": top_items,
    }


def serialize_product_catalog_item(product: Product) -> dict[str, Any]:
    product_gender = infer_product_gender(product.title)
    return {
        "id": product.id,
        "title": product.title,
        "price": product.price,
        "image_url": build_public_image_url(product.image_path),
        "brand": get_product_brand(product),
        "platform": get_product_platform(product),
        "product_url": resolve_product_url(product),
        "style_type": product.style_type,
        "color_family": product.color_family,
        "body_fit": product.body_fit,
        "style_features": get_visible_style_features(product),
        "function_features": ensure_list(product.function_features),
        "size_tags": ensure_list(product.size_tags),
        "size_notes": product.size_notes,
        "product_gender": product_gender,
        "gender_label": get_gender_label(product_gender),
        "is_child_product": is_child_product(product.title),
    }


def matches_product_query(product: Product, query: str | None) -> bool:
    if not query:
        return True

    normalized_query = query.strip().lower()
    if not normalized_query:
        return True

    haystack = " ".join(
        [
            product.title,
            get_product_brand(product) or "",
            product.style_type,
            product.color_family,
            product.body_fit,
            *get_visible_style_features(product),
            *ensure_list(product.function_features),
        ]
    ).lower()
    return all(token in haystack for token in normalized_query.split())


def list_catalog_products(
    *,
    products: list[Product],
    query: str | None,
    gender: str | None,
    platform: str | None,
    mode: str,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    normalized_gender = normalize_user_gender(gender)
    normalized_platform = normalize_platform_filter(platform)
    filtered_products, _ = filter_adult_products(products)
    gender_fallback = False

    if mode == "gender" and normalized_gender:
        gender_products = [
            product
            for product in filtered_products
            if infer_product_gender(product.title) in {normalized_gender, "unisex"}
        ]
        if gender_products:
            filtered_products = gender_products
        else:
            gender_fallback = True

    if normalized_platform:
        filtered_products = [
            product for product in filtered_products if get_product_platform_key(product) == normalized_platform
        ]

    filtered_products = [product for product in filtered_products if matches_product_query(product, query)]
    filtered_products = sorted(
        filtered_products,
        key=lambda product: (
            -get_gender_match_priority(product.title, normalized_gender),
            product.price,
            product.id,
        ),
    )

    safe_offset = max(0, offset)
    safe_limit = max(1, min(limit, 120))
    paged_items = filtered_products[safe_offset : safe_offset + safe_limit]
    return {
        "items": [serialize_product_catalog_item(product) for product in paged_items],
        "total": len(filtered_products),
        "offset": safe_offset,
        "limit": safe_limit,
        "mode": mode,
        "user_gender": normalized_gender,
        "gender_fallback": gender_fallback,
    }


def build_budget_note(product: Product, price_min: float | None, price_max: float | None) -> str | None:
    if price_min is None and price_max is None:
        return None
    if price_min is not None and product.price < price_min:
        return f"这件单品价格低于你设定的预算下限 ¥{price_min:.0f}，适合作为更省预算的替代方案。"
    if price_max is not None and product.price > price_max:
        return f"这件单品价格高于你设定的预算上限 ¥{price_max:.0f}，如果优先控制预算可以再看更轻量的备选。"
    return "这件单品价格落在你的预算区间内。"


def build_gender_note(product: Product, user_gender: str | None) -> str | None:
    normalized_gender = normalize_user_gender(user_gender)
    if not normalized_gender:
        return None

    product_gender = infer_product_gender(product.title)
    if product_gender == normalized_gender:
        return f"这件商品标注为{get_gender_label(product_gender)}，与当前选择一致。"
    if product_gender == "unisex":
        return "这件商品是中性/同款设计，可作为更灵活的搭配选择。"
    if product_gender == "unknown":
        return "这件商品未明确标注性别，建议结合版型和尺码再确认上身效果。"
    return f"这件商品标注为{get_gender_label(product_gender)}，与当前选择不完全一致，建议重点确认版型和肩袖比例。"


def build_personality_note(mbti: str | None, product: Product, personality_score: int | None) -> str | None:
    if not mbti or personality_score is None:
        return None

    if personality_score >= 85:
        return f"{mbti.upper()} 的气质偏好和这件单品的 {product.style_type} 调性匹配度很高。"
    if personality_score >= 70:
        return f"{mbti.upper()} 的风格取向和这件单品整体相容，适合作为稳定不出错的搭配。"
    return f"这件单品与 {mbti.upper()} 的气质偏好不算最强匹配，但可以靠内搭或配饰把风格拉回到你更舒适的区间。"


def build_style_lab_advice(
    product: Product,
    *,
    preferred_color: str,
    resolved_style: str,
    brand_preference: str | None,
    color_score: int,
    body_score: int,
    style_score: int,
    brand_score: int | None,
    personality_score: int | None,
    price_min: float | None,
    price_max: float | None,
    mbti: str | None,
    user_gender: str | None,
) -> list[str]:
    advice: list[str] = []

    if color_score >= 90:
        advice.append(f"颜色上更安全，这件 {product.color_family} 单品和你偏好的 {preferred_color} 同属接近色系。")
    elif color_score >= 70:
        advice.append(f"颜色不算完全同色，但 {product.color_family} 仍能和你偏好的 {preferred_color} 形成比较顺眼的冬季搭配。")
    else:
        advice.append(f"如果你想更贴近 {preferred_color} 偏好，可以再找更亮或更浅的色系替代。")

    if body_score >= 88:
        advice.append(f"版型对当前身型友好，{product.body_fit}。")
    else:
        advice.append(f"版型匹配度一般，建议重点留意 {product.style_type} 的肩线、衣长和蓬松量。")

    if style_score >= 85:
        advice.append(f"风格方向和你当前建议的 {resolved_style} 基本一致，属于高容错搭配。")
    else:
        advice.append(f"这件更偏向 {product.style_type}，如果你想贴近 {resolved_style}，可以靠下装和鞋履把整体气质拉回来。")

    brand_note = build_brand_note(brand_preference, product, brand_score)
    if brand_note:
        advice.append(brand_note)

    feature_tags = ensure_list(product.function_features)
    if feature_tags:
        advice.append(f"单品亮点在 {'、'.join(feature_tags[:3])}，适合在通勤、户外或降温场景中优先考虑。")

    budget_note = build_budget_note(product, price_min, price_max)
    if budget_note:
        advice.append(budget_note)

    personality_note = build_personality_note(mbti, product, personality_score)
    if personality_note:
        advice.append(personality_note)

    gender_note = build_gender_note(product, user_gender)
    if gender_note:
        advice.append(gender_note)

    deduped: list[str] = []
    for item in advice:
        if item not in deduped:
            deduped.append(item)
    return deduped[:5]


def analyze_selected_product(
    *,
    product: Product,
    image_bytes: bytes | None,
    mime_type: str | None,
    color_preference: str,
    brand_preference: str | None,
    gender: str | None,
    mbti: str | None,
    size: str | None,
    style_preference: str | None,
    gemini_api_key: str | None,
    gemini_model: str | None,
    deepseek_api_key: str | None = None,
    deepseek_model: str | None = None,
    mimo_api_key: str | None = None,
    mimo_model: str | None = None,
    ai_provider: str | None = None,
    vision_provider: str | None = None,
    price_min: float | None,
    price_max: float | None,
) -> dict[str, Any]:
    normalized_gender = normalize_user_gender(gender)
    inference = resolve_user_profile(
        image_bytes=image_bytes,
        mime_type=mime_type,
        color_preference=color_preference,
        gender=normalized_gender,
        mbti=mbti,
        size=size,
        style_preference=style_preference,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        deepseek_api_key=deepseek_api_key,
        deepseek_model=deepseek_model,
        mimo_api_key=mimo_api_key,
        mimo_model=mimo_model,
        ai_provider=ai_provider,
        vision_provider=vision_provider,
    )

    color_score = score_color(color_preference, product.color_family)
    body_score = score_body_fit(inference["resolved_size"], inference["body_shape"], product)
    style_score = score_style(inference["resolved_style"], product)
    brand_score = score_brand(brand_preference, product)
    personality_score = score_personality(mbti, product)
    total_score, breakdown, radar_chart = build_score_breakdown(
        color_score=color_score,
        body_score=body_score,
        style_score=style_score,
        brand_score=brand_score,
        personality_score=personality_score,
    )

    return {
        "product": serialize_product_catalog_item(product),
        "inference": inference,
        "analysis": {
            "total_score": total_score,
            "score_breakdown": breakdown,
            "radar_chart": radar_chart,
            "reason": build_item_reason(
                product,
                preferred_color=color_preference,
                resolved_style=inference["resolved_style"],
                brand_preference=brand_preference,
                color_score=color_score,
                body_score=body_score,
                style_score=style_score,
                brand_score=brand_score,
                personality_score=personality_score,
            ),
            "styling_advice": build_style_lab_advice(
                product,
                preferred_color=color_preference,
                resolved_style=inference["resolved_style"],
                brand_preference=brand_preference,
                color_score=color_score,
                body_score=body_score,
                style_score=style_score,
                brand_score=brand_score,
                personality_score=personality_score,
                price_min=price_min,
                price_max=price_max,
                mbti=mbti,
                user_gender=normalized_gender,
            ),
            "brand_score": brand_score,
            "budget_note": build_budget_note(product, price_min, price_max),
            "brand_note": build_brand_note(brand_preference, product, brand_score),
            "gender_note": build_gender_note(product, normalized_gender),
            "personality_note": build_personality_note(mbti, product, personality_score),
        },
    }
