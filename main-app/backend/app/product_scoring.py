from __future__ import annotations

import difflib

from app.database import Product, SIZE_ORDER
from app.recommendation_rules import classify_color_group, clamp_score, ensure_list, tokenize_style_text
from app.product_attributes import (
    get_brand_match_details,
    get_product_brand,
    get_visible_style_features,
    parse_brand_preferences,
)


def score_brand(brand_preference: str | None, product: Product) -> int | None:
    preferred_brands = parse_brand_preferences(brand_preference)
    if not preferred_brands:
        return None

    product_brand = get_product_brand(product)
    exact_matches, match_count = get_brand_match_details(preferred_brands, product)
    if exact_matches:
        return clamp_score(96 + exact_matches * 2 + min(match_count, 2))
    if match_count >= 4:
        return 96
    if match_count >= 2:
        return 92
    if match_count == 1:
        return 84

    if product_brand:
        return 34
    return 42


def score_color(preferred_color: str, product_color: str) -> int:
    if not preferred_color:
        return 65

    if preferred_color == product_color:
        return 100

    if preferred_color in product_color or product_color in preferred_color:
        return 98

    preferred_group = classify_color_group(preferred_color)
    product_group = classify_color_group(product_color)
    if preferred_group and preferred_group == product_group:
        if preferred_group == "white":
            return 92
        if preferred_group == "black":
            return 90
        return 88

    neutral_pair_scores = {
        frozenset({"white", "gray"}): 76,
        frozenset({"white", "brown"}): 68,
        frozenset({"white", "black"}): 38,
        frozenset({"black", "gray"}): 72,
        frozenset({"black", "brown"}): 58,
        frozenset({"gray", "brown"}): 64,
    }
    pair = frozenset({preferred_group, product_group})
    if pair in neutral_pair_scores:
        return neutral_pair_scores[pair]

    neutral_groups = {"black", "white", "gray", "brown"}
    if preferred_group in neutral_groups or product_group in neutral_groups:
        return 52

    return 36


def detect_fit_bucket(body_fit: str) -> str:
    if "修身" in body_fit:
        return "slim"
    if "大码" in body_fit or "高壮" in body_fit:
        return "plus"
    if "宽松" in body_fit or "蓬松" in body_fit:
        return "relaxed"
    if "标准" in body_fit or "常规" in body_fit or "直筒" in body_fit:
        return "regular"
    return "regular"


def classify_user_fit(size: str | None) -> str:
    if size in {"XS", "S"}:
        return "slim"
    if size in {"M", "L"}:
        return "regular"
    if size in {"XL", "2XL"}:
        return "relaxed"
    if size in {"3XL", "4XL", "5XL", "6XL", "7XL"}:
        return "plus"
    return "regular"


def score_size_tag_alignment(user_size: str | None, product_sizes: list[str]) -> int:
    if not user_size or not product_sizes:
        return 0

    if user_size in product_sizes:
        return 8

    user_rank = SIZE_ORDER.get(user_size)
    candidate_ranks = [SIZE_ORDER.get(size) for size in product_sizes if size in SIZE_ORDER]
    if not user_rank or not candidate_ranks:
        return 0

    gap = min(abs(user_rank - rank) for rank in candidate_ranks)
    if gap == 1:
        return 2
    if gap >= 3:
        return -8
    return -3


def score_body_fit(user_size: str | None, body_shape: str, product: Product) -> int:
    user_fit = classify_user_fit(user_size)
    product_fit = detect_fit_bucket(product.body_fit)

    base_scores = {
        "slim": {"slim": 94, "regular": 87, "relaxed": 74, "plus": 55},
        "regular": {"slim": 80, "regular": 93, "relaxed": 86, "plus": 72},
        "relaxed": {"slim": 60, "regular": 82, "relaxed": 93, "plus": 88},
        "plus": {"slim": 48, "regular": 70, "relaxed": 88, "plus": 96},
    }
    score = base_scores[user_fit][product_fit]
    score += score_size_tag_alignment(user_size, ensure_list(product.size_tags))

    if body_shape in {"微胖", "高壮", "O型"} and product_fit in {"relaxed", "plus"}:
        score += 4
    if body_shape in {"偏瘦", "H型"} and product.style_type in {"绗缝款（排骨款）", "短款", "轻薄款"}:
        score += 4
    if body_shape == "梨形" and product.style_type in {"中长款大衣", "长款", "常规短外套"}:
        score += 4
    if body_shape == "倒三角" and product.style_type in {"轻薄款", "常规短外套", "绗缝款（排骨款）"}:
        score += 4

    return clamp_score(score)


def score_style(style_preference: str | None, product: Product) -> int:
    if not style_preference:
        return 70

    preferred_tokens = tokenize_style_text(style_preference)
    product_tokens = tokenize_style_text(
        " ".join([product.style_type, *get_visible_style_features(product), *ensure_list(product.function_features)])
    )

    if style_preference == product.style_type:
        return 96

    overlap = len(preferred_tokens & product_tokens)
    if overlap:
        return clamp_score(80 + overlap * 6)

    similarity = difflib.SequenceMatcher(None, style_preference, product.style_type).ratio()
    if similarity >= 0.65:
        return 78

    return 52


def score_personality(mbti: str | None, product: Product) -> int | None:
    if not mbti:
        return None

    mbti_value = mbti.upper()
    product_tokens = tokenize_style_text(
        " ".join([product.style_type, *get_visible_style_features(product), *ensure_list(product.function_features)])
    )

    desired_tokens: set[str] = set()
    if mbti_value[1:2] == "N":
        desired_tokens.update({"潮流", "巴恩风/工装风", "面包服"})
    else:
        desired_tokens.update({"常规短外套", "户外", "通勤"})

    if mbti_value[:1] == "E":
        desired_tokens.update({"运动", "潮流", "面包服"})
    else:
        desired_tokens.update({"通勤", "休闲", "轻薄款"})

    if mbti_value[2:3] == "T":
        desired_tokens.update({"通勤", "户外", "巴恩风/工装风"})
    else:
        desired_tokens.update({"休闲", "面包服", "中长款大衣"})

    if mbti_value[3:4] == "J":
        desired_tokens.update({"常规短外套", "通勤", "商务"})
    else:
        desired_tokens.update({"运动", "轻薄款", "面包服"})

    matches = len(desired_tokens & product_tokens)
    return clamp_score(58 + matches * 8)


def build_score_breakdown(
    *,
    color_score: int,
    body_score: int,
    style_score: int,
    brand_score: int | None,
    personality_score: int | None,
) -> tuple[float, dict[str, int], list[dict[str, int]]]:
    weighted_scores = {
        "颜色适配度": (color_score, 0.34),
        "身材适配度": (body_score, 0.28),
        "款式适配度": (style_score, 0.18),
    }
    if brand_score is not None:
        weighted_scores["品牌偏好度"] = (brand_score, 0.1)
    if personality_score is not None:
        weighted_scores["性格适配度"] = (personality_score, 0.1)

    total_weight = sum(weight for _, weight in weighted_scores.values())
    total_score = sum(score * weight for score, weight in weighted_scores.values()) / total_weight
    breakdown = {label: score for label, (score, _) in weighted_scores.items()}
    radar = [{"dimension": label, "score": score} for label, score in breakdown.items()]
    return round(total_score, 2), breakdown, radar
