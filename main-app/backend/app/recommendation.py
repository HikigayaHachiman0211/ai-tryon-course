from __future__ import annotations

import base64
import difflib
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from app.catalog_seed import BRAND_ALIASES, extract_brand_tag, get_platform_label, infer_brand_name, infer_platform_key
from app.database import Product, SIZE_ORDER, normalize_size

import re as _re_module
import urllib.parse as _urllib_parse


DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")

DEFAULT_DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_MODELS = [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "deepseek-chat",
    "deepseek-reasoner",
]
DEEPSEEK_API_BASE = "https://api.deepseek.com"

COLOR_GROUPS = {
    "black": ["黑", "曜石黑", "极夜黑", "幻影黑", "静谧黑", "摩卡黑", "深炭黑", "青光黑"],
    "white": ["白", "米白", "极晶白", "月光白", "奶白", "象牙白"],
    "gray": ["灰", "浅灰", "深灰", "中灰", "钛灰", "岩层灰", "岩脊深灰", "灰褐", "灰蓝"],
    "blue": ["蓝", "雾蓝", "雾霾蓝", "光影蓝", "寂静蓝", "墨石蓝", "夜影蓝", "夜泊蓝", "风信蓝", "藏青"],
    "green": ["绿", "豆绿", "潜水绿", "橄榄"],
    "red": ["红", "骐骥红"],
    "orange": ["橘", "落日橘"],
    "brown": ["棕", "咖", "卡其", "米色", "浅咖", "杏色", "暖卡其"],
}

STYLE_TOKEN_MAP = {
    "常规短外套": ["常规", "基础", "百搭"],
    "短款": ["短款", "短版"],
    "轻薄款": ["轻薄", "轻量", "轻盈"],
    "绗缝款（排骨款）": ["绗缝", "排骨", "小龟背", "内胆"],
    "面包服": ["面包服", "泡芙", "蓬松"],
    "中长款大衣": ["大衣", "风衣", "中长款", "毛呢", "西服领"],
    "长款": ["长款", "过膝"],
    "巴恩风/工装风": ["工装", "巴恩", "山系", "露营", "多口袋"],
    "运动": ["运动", "训练"],
    "户外": ["户外", "登山", "防风", "防水"],
    "通勤": ["通勤", "简约", "极简"],
    "商务": ["商务", "行政", "正式"],
    "休闲": ["休闲", "日常", "情侣"],
    "潮流": ["潮流", "时尚", "街头"],
}

STYLE_CHOICES = [
    "常规短外套",
    "短款",
    "轻薄款",
    "绗缝款（排骨款）",
    "面包服",
    "中长款大衣",
    "长款",
    "巴恩风/工装风",
]

UNISEX_GENDER_KEYWORDS = [
    "男女同款",
    "男女款",
    "情侣款",
    "情侣",
    "中性",
    "男女士同款",
    "男女",
]
MALE_GENDER_KEYWORDS = ["【男款】", "男士", "男款", "男装", "男子", "男"]
FEMALE_GENDER_KEYWORDS = ["【女款】", "女士", "女款", "女装", "女子", "女"]
CHILD_KEYWORDS = ["男童", "女童", "儿童", "童装", "婴童", "宝宝", "婴儿", "小童", "大童", "幼童"]


def ensure_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def clamp_score(value: float) -> int:
    return max(1, min(100, int(round(value))))


def build_public_image_url(image_path: str) -> str:
    if image_path.startswith(("http://", "https://")):
        return image_path

    normalized_path = image_path.replace("\\", "/").lstrip("/")
    filename = Path(normalized_path).name
    public_base_url = os.getenv("PUBLIC_IMAGE_BASE_URL")
    if public_base_url:
        return f"{public_base_url.rstrip('/')}/{quote(filename)}"
    return f"/static/products/{quote(normalized_path, safe='/')}"


def get_product_brand(product: Product) -> str | None:
    title_brand = infer_brand_name(product.title)
    if title_brand:
        return title_brand

    tagged_brand = extract_brand_tag(ensure_list(product.style_features))
    if tagged_brand:
        normalized_tagged_brand = infer_brand_name(tagged_brand)
        return normalized_tagged_brand or tagged_brand
    return None


def get_product_platform_key(product: Product) -> str:
    return infer_platform_key(product.image_path)


def get_product_platform(product: Product) -> str:
    return get_platform_label(get_product_platform_key(product))


def get_visible_style_features(product: Product) -> list[str]:
    return [
        feature
        for feature in ensure_list(product.style_features)
        if not str(feature).startswith(("品牌:", "品牌："))
    ]


def generate_product_search_url(product: Product) -> str:
    """Generate a fallback search URL when product_url is missing."""
    platform_key = get_product_platform_key(product)
    # Extract core keywords: remove size tokens and trailing color-only words
    title = product.title
    search_query = _re_module.sub(
        r"\b(?:7XL|6XL|5XL|4XL|3XL|2XL|XXXL|XXL|XL|XS|S|M|L)\b",
        "",
        title,
        flags=_re_module.IGNORECASE,
    ).strip()
    # Limit length for platform search boxes
    if len(search_query) > 60:
        search_query = search_query[:60]
    encoded = _urllib_parse.quote(search_query)
    if platform_key == "taobao":
        return f"https://s.taobao.com/search?q={encoded}"
    return f"https://search.jd.com/Search?keyword={encoded}"


def resolve_product_url(product: Product) -> str:
    """Return the product's direct URL, or a search fallback."""
    if product.product_url:
        return product.product_url
    return generate_product_search_url(product)


def parse_brand_preferences(value: str | None) -> list[str]:
    if not value:
        return []

    normalized_preferences: list[str] = []
    for raw_token in re.split(r"[，,、/|]+", value):
        token = raw_token.strip()
        if not token:
            continue
        normalized = infer_brand_name(token)
        if not normalized:
            normalized = token.upper() if re.fullmatch(r"[A-Za-z0-9& .'-]+", token) else token
        if normalized and normalized not in normalized_preferences:
            normalized_preferences.append(normalized)
    return normalized_preferences


def get_brand_keywords(brand: str) -> list[str]:
    keywords: list[str] = []
    for keyword in [brand, *BRAND_ALIASES.get(brand, [])]:
        normalized = keyword.strip()
        if normalized and normalized not in keywords:
            keywords.append(normalized)
    return keywords


def get_brand_match_details(preferred_brands: list[str], product: Product) -> tuple[int, int]:
    if not preferred_brands:
        return 0, 0

    product_brand = get_product_brand(product)
    normalized_product_brand = infer_brand_name(product_brand) if product_brand else None
    product_brand_text = (product_brand or "").upper()
    title_text = product.title.upper()
    exact_matches = 0
    match_count = 0

    for preferred_brand in preferred_brands:
        keywords = get_brand_keywords(preferred_brand)
        if normalized_product_brand == preferred_brand:
            exact_matches += 1
            match_count += 2
        elif product_brand and any(
            keyword.upper() in product_brand_text or product_brand_text in keyword.upper()
            for keyword in keywords
        ):
            match_count += 1

        for keyword in keywords:
            match_count += title_text.count(keyword.upper())

    return exact_matches, match_count


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


def normalize_platform_filter(value: str | None) -> str | None:
    if not value:
        return None

    normalized = value.strip().lower()
    mapping = {
        "jd": "jd",
        "京东": "jd",
        "taobao": "taobao",
        "tb": "taobao",
        "淘宝": "taobao",
        "all": None,
        "全部": None,
    }
    return mapping.get(normalized)


def classify_color_group(text: str | None) -> str | None:
    if not text:
        return None
    lowered = text.lower()
    for group, keywords in COLOR_GROUPS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            return group
    return None


def tokenize_style_text(text: str | None) -> set[str]:
    if not text:
        return set()

    tokens: set[str] = set()
    for canonical, keywords in STYLE_TOKEN_MAP.items():
        if canonical in text or any(keyword in text for keyword in keywords):
            tokens.add(canonical)
    return tokens


def normalize_style_preference(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower()
    if lowered in {"unknown", "未知", "未提供", "none", "null"}:
        return None
    for style in STYLE_CHOICES:
        if style in value:
            return style
    tokens = tokenize_style_text(value)
    for style in STYLE_CHOICES:
        if style in tokens:
            return style
    return value.strip()


def normalize_body_shape(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized in {"未知", "unknown", "Unknown", "未提供", "none", "null"}:
        return None
    return normalized


def normalize_user_gender(value: str | None) -> str | None:
    if not value:
        return None

    normalized = value.strip().lower()
    if normalized in {"male", "man", "boy", "男", "男性"}:
        return "male"
    if normalized in {"female", "woman", "girl", "女", "女性"}:
        return "female"
    return None


def infer_product_gender(title: str) -> str:
    if any(keyword in title for keyword in UNISEX_GENDER_KEYWORDS):
        return "unisex"

    if "【男款】" in title and "【女款】" not in title:
        return "male"
    if "【女款】" in title and "【男款】" not in title:
        return "female"

    male_positions = [title.rfind(keyword) for keyword in MALE_GENDER_KEYWORDS if keyword in title]
    female_positions = [title.rfind(keyword) for keyword in FEMALE_GENDER_KEYWORDS if keyword in title]

    if male_positions and female_positions:
        return "male" if max(male_positions) > max(female_positions) else "female"
    if male_positions:
        return "male"
    if female_positions:
        return "female"
    return "unknown"


def filter_products_by_gender(products: list[Product], user_gender: str | None) -> tuple[list[Product], bool]:
    normalized_gender = normalize_user_gender(user_gender)
    if not normalized_gender:
        return products, False

    specific_matches = [product for product in products if infer_product_gender(product.title) == normalized_gender]
    unisex_matches = [product for product in products if infer_product_gender(product.title) == "unisex"]
    if specific_matches:
        return [*specific_matches, *unisex_matches], False
    if unisex_matches:
        return unisex_matches, False

    fallback_matches = [product for product in products if infer_product_gender(product.title) == "unknown"]
    return fallback_matches, bool(fallback_matches)


def is_child_product(title: str) -> bool:
    return any(keyword in title for keyword in CHILD_KEYWORDS)


def filter_adult_products(products: list[Product]) -> tuple[list[Product], bool]:
    adult_products = [product for product in products if not is_child_product(product.title)]
    if adult_products:
        return adult_products, False
    return products, True


def get_gender_match_priority(title: str, user_gender: str | None) -> int:
    normalized_gender = normalize_user_gender(user_gender)
    if not normalized_gender:
        return 0

    product_gender = infer_product_gender(title)
    if product_gender == normalized_gender:
        return 2
    if product_gender == "unisex":
        return 1
    return 0


def strip_json_block(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


def call_gemini_profile(
    *,
    image_bytes: bytes,
    mime_type: str | None,
    api_key: str,
    gender: str | None,
    mbti: str | None,
    color_preference: str,
    size: str | None,
    style_preference: str | None,
    model: str,
) -> dict[str, Any] | None:
    prompt = f"""
你是服装搭配分析助手。请结合全身照、用户颜色偏好、MBTI 和已知条件，输出一个 JSON 对象，不要输出 markdown。

已知条件：
- 颜色偏好: {color_preference}
- 用户性别: {gender or '未提供'}
- MBTI: {mbti or '未提供'}
- 用户已提供尺码: {size or '未提供'}
- 用户已提供款式偏好: {style_preference or '未提供'}

返回字段：
{{
  "recommended_size": "XS/S/M/L/XL/2XL/3XL/4XL/5XL/unknown 之一",
  "body_shape": "偏瘦/标准/微胖/高壮/H型/梨形/倒三角/沙漏型/O型/未知 之一",
  "suggested_style": "常规短外套/短款/轻薄款/绗缝款（排骨款）/面包服/中长款大衣/长款/巴恩风/工装风 之一",
  "reasoning": "50字内中文解释"
}}

要求：
- 如果用户已提供尺码或款式偏好，也要结合图像做校验，但仍返回完整 JSON。
- 如果无法可靠判断，请写 unknown 或 未知。
""".strip()

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type or "image/png",
                            "data": base64.b64encode(image_bytes).decode("utf-8"),
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    response = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": api_key},
        json=payload,
        timeout=30.0,
    )
    response.raise_for_status()
    response_json = response.json()

    texts: list[str] = []
    for candidate in response_json.get("candidates", []):
        content = candidate.get("content") or {}
        for part in content.get("parts", []):
            if "text" in part:
                texts.append(part["text"])

    if not texts:
        return None

    return strip_json_block("\n".join(texts))


def call_deepseek_profile(
    *,
    api_key: str,
    gender: str | None,
    mbti: str | None,
    color_preference: str,
    size: str | None,
    style_preference: str | None,
    model: str,
) -> dict[str, Any] | None:
    prompt = f"""你是服装搭配分析助手。请根据用户提供的信息，推断体型特征和推荐方案，输出一个 JSON 对象。

已知条件：
- 颜色偏好: {color_preference}
- 用户性别: {gender or '未提供'}
- MBTI: {mbti or '未提供'}
- 用户已提供尺码: {size or '未提供'}
- 用户已提供款式偏好: {style_preference or '未提供'}

返回字段（JSON 格式）：
{{
  "recommended_size": "XS/S/M/L/XL/2XL/3XL/4XL/5XL/unknown 之一",
  "body_shape": "偏瘦/标准/微胖/高壮/H型/梨形/倒三角/沙漏型/O型/未知 之一",
  "suggested_style": "常规短外套/短款/轻薄款/绗缝款（排骨款）/面包服/中长款大衣/长款/巴恩风/工装风 之一",
  "reasoning": "50字内中文解释"
}}

要求：
- 综合所有已知条件进行推断。
- 如果信息不足无法可靠判断，请写 unknown 或 未知。
""".strip()

    messages = [
        {"role": "system", "content": "你是一个专业的冬季羽绒服搭配分析助手，根据用户信息输出 JSON 格式的推荐结果。"},
        {"role": "user", "content": prompt},
    ]

    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": 512,
        "stream": False,
    }

    response = httpx.post(
        f"{DEEPSEEK_API_BASE}/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json=payload,
        timeout=30.0,
    )
    response.raise_for_status()
    response_json = response.json()

    choices = response_json.get("choices", [])
    if not choices:
        return None

    content = choices[0].get("message", {}).get("content", "")
    if not content:
        return None

    return strip_json_block(content)


def fallback_body_shape(size: str | None) -> str:
    if size in {"XS", "S"}:
        return "偏瘦"
    if size in {"M", "L"}:
        return "标准"
    if size in {"XL", "2XL"}:
        return "微胖"
    if size in {"3XL", "4XL", "5XL", "6XL", "7XL"}:
        return "高壮"
    return "标准"


def fallback_size_from_body_shape(body_shape: str | None) -> str | None:
    if body_shape in {"偏瘦", "H型"}:
        return "S"
    if body_shape in {"标准", "沙漏型", "倒三角"}:
        return "M"
    if body_shape in {"微胖", "梨形", "O型"}:
        return "XL"
    if body_shape == "高壮":
        return "2XL"
    return None


def infer_style_heuristically(body_shape: str | None, mbti: str | None) -> str:
    mbti_value = (mbti or "").upper()

    if body_shape in {"梨形", "O型"}:
        return "中长款大衣"
    if body_shape in {"微胖", "高壮"}:
        return "面包服"
    if body_shape in {"偏瘦", "H型"}:
        return "绗缝款（排骨款）"
    if body_shape == "倒三角":
        return "轻薄款"

    if mbti_value.endswith("J"):
        return "常规短外套"
    if mbti_value.endswith("P"):
        return "巴恩风/工装风"
    if mbti_value[:1] == "E":
        return "面包服"
    return "短款"


def build_inference_reason(body_shape: str, resolved_size: str | None, resolved_style: str, mbti: str | None) -> str:
    parts = [f"综合身型特征判断更接近{body_shape}"]
    if resolved_size:
        parts.append(f"尺码按{resolved_size}估计")
    if mbti:
        parts.append(f"结合 {mbti.upper()} 的气质偏好建议 {resolved_style}")
    else:
        parts.append(f"推荐优先考虑 {resolved_style}")
    return "，".join(parts)


def resolve_user_profile(
    *,
    image_bytes: bytes | None,
    mime_type: str | None,
    color_preference: str,
    gender: str | None,
    mbti: str | None,
    size: str | None,
    style_preference: str | None,
    gemini_api_key: str | None,
    gemini_model: str | None,
    deepseek_api_key: str | None = None,
    deepseek_model: str | None = None,
    ai_provider: str | None = None,
) -> dict[str, Any]:
    gemini_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
    deepseek_key = deepseek_api_key or os.getenv("DEEPSEEK_API_KEY")
    provider = (ai_provider or "auto").strip().lower()
    resolved_size = normalize_size(size)
    resolved_style = normalize_style_preference(style_preference)
    body_shape: str | None = None
    ai_reasoning: str | None = None
    size_source = "user" if resolved_size else "unknown"
    style_source = "user" if resolved_style else "unknown"
    ai_result: dict[str, Any] | None = None
    used_provider = "none"

    needs_ai = not resolved_size or not resolved_style

    # --- Gemini attempt ---
    if needs_ai and provider in ("auto", "gemini") and image_bytes and gemini_key:
        try:
            ai_result = call_gemini_profile(
                image_bytes=image_bytes,
                mime_type=mime_type,
                api_key=gemini_key,
                gender=gender,
                mbti=mbti,
                color_preference=color_preference,
                size=size,
                style_preference=style_preference,
                model=gemini_model or DEFAULT_GEMINI_MODEL,
            )
            if ai_result:
                used_provider = "gemini"
        except Exception as exc:
            ai_reasoning = f"Gemini 分析失败: {exc}"

    # --- Deepseek attempt (fallback in auto, or explicit choice) ---
    if needs_ai and not ai_result and provider in ("auto", "deepseek") and deepseek_key:
        try:
            ai_result = call_deepseek_profile(
                api_key=deepseek_key,
                gender=gender,
                mbti=mbti,
                color_preference=color_preference,
                size=size,
                style_preference=style_preference,
                model=deepseek_model or DEFAULT_DEEPSEEK_MODEL,
            )
            if ai_result:
                used_provider = "deepseek"
                ai_reasoning = None
        except Exception as exc:
            fallback_msg = f"Deepseek 分析失败: {exc}"
            ai_reasoning = f"{ai_reasoning}; {fallback_msg}" if ai_reasoning else fallback_msg

    if not ai_result and needs_ai and ai_reasoning is None:
        ai_reasoning = "未配置 AI 引擎密钥，已回退为规则推断"

    if ai_result:
        body_shape = normalize_body_shape(str(ai_result.get("body_shape") or ""))
        result_reasoning = str(ai_result.get("reasoning") or "").strip()
        if result_reasoning:
            ai_reasoning = result_reasoning
        if not resolved_size:
            resolved_size = normalize_size(str(ai_result.get("recommended_size") or ""))
            if resolved_size:
                size_source = used_provider
        if not resolved_style:
            resolved_style = normalize_style_preference(str(ai_result.get("suggested_style") or ""))
            if resolved_style:
                style_source = used_provider

    if not body_shape:
        body_shape = fallback_body_shape(resolved_size)

    if not resolved_size:
        resolved_size = fallback_size_from_body_shape(body_shape)
        if resolved_size:
            size_source = "heuristic"

    if not resolved_style:
        resolved_style = infer_style_heuristically(body_shape, mbti)
        style_source = "heuristic"

    reasoning = ai_reasoning or build_inference_reason(body_shape, resolved_size, resolved_style, mbti)
    return {
        "resolved_size": resolved_size,
        "resolved_style": resolved_style,
        "body_shape": body_shape,
        "size_source": size_source,
        "style_source": style_source,
        "reasoning": reasoning,
        "gemini_model": gemini_model or DEFAULT_GEMINI_MODEL,
        "gemini_used": used_provider == "gemini",
        "ai_provider": used_provider,
    }


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
    ai_provider: str | None = None,
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
        ai_provider=ai_provider,
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


def get_gender_label(product_gender: str) -> str:
    labels = {
        "male": "男款",
        "female": "女款",
        "unisex": "中性/同款",
        "unknown": "未标注",
    }
    return labels.get(product_gender, "未标注")


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
    ai_provider: str | None = None,
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
        ai_provider=ai_provider,
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
