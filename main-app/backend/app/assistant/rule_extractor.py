from __future__ import annotations

import re
from typing import Any

from app.assistant.config import DEFAULT_AI_PROVIDER, DEFAULT_MIMO_MODEL


# Gender patterns — longer/more-specific patterns first
GENDER_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(大[一二三]女学生|女大学生|女款|女士|女生|女性|女装)"), "female"),
    (re.compile(r"(大[一二三]男学生|男大学生|男款|男士|男生|男性|男装)"), "male"),
    (re.compile(r"(女|女孩)"), "female"),
    (re.compile(r"(男|男孩)"), "male"),
]

# Color mapping
COLOR_MAP: dict[str, str] = {
    "黑": "黑色", "黑色": "黑色",
    "白": "白色", "白色": "白色", "米白": "米白",
    "灰": "灰色", "灰色": "灰色",
    "蓝": "蓝色", "蓝色": "蓝色", "雾蓝": "雾蓝", "藏青": "藏青",
    "绿": "绿色", "绿色": "绿色", "豆绿": "豆绿", "橄榄": "橄榄",
    "红": "红色", "红色": "红色",
    "棕": "棕色", "咖": "卡其色", "卡其": "卡其色", "米色": "米色",
    "橘": "橘色", "落日橘": "橘色",
    "粉": "粉色", "粉色": "粉色",
}
VALID_COLORS = set(COLOR_MAP.values())

# Chinese number mapping
CN_NUM = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
          "百": 100, "千": 1000, "万": 10000}


def _parse_chinese_number(text: str) -> float | None:
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass

    total = 0.0
    current = 0.0
    for ch in text:
        if ch in CN_NUM:
            val = CN_NUM[ch]
            if val >= 10:
                if current == 0:
                    current = 1
                if val == 10:
                    current *= 10
                elif val == 100:
                    current *= 100
                elif val == 1000:
                    current *= 1000
                elif val == 10000:
                    current *= 10000
            else:
                current = val
        elif ch.isdigit():
            current = float(ch)
        else:
            total += current
            current = 0.0
    total += current
    return total if total > 0 else None


def extract_gender(text: str) -> str | None:
    for pattern, gender in GENDER_PATTERNS:
        if pattern.search(text):
            return gender
    return None


def extract_color(text: str) -> str | None:
    found: list[tuple[int, int, str]] = []
    for keyword, color in COLOR_MAP.items():
        for position in _positive_mentions(text, keyword):
            found.append((position, -len(keyword), color))
    if not found:
        return None
    found.sort()
    return found[-1][2]


def extract_price(text: str) -> tuple[float | None, float | None]:
    price_min: float | None = None
    price_max: float | None = None

    # Pattern: 300到700, 300-700, 300~700
    range_match = re.search(r"(\d+)\s*[到\-~]\s*(\d+)", text)
    if range_match:
        price_min = float(range_match.group(1))
        price_max = float(range_match.group(2))
        if price_min > price_max:
            price_min, price_max = price_max, price_min
        return price_min, price_max

    # Chinese number range: 三百到七百
    cn_range = re.search(r"([一二两三四五六七八九十百千万]+)\s*到\s*([一二两三四五六七八九十百千万]+)", text)
    if cn_range:
        low = _parse_chinese_number(cn_range.group(1))
        high = _parse_chinese_number(cn_range.group(2))
        if low and high:
            if low > high:
                low, high = high, low
            return low, high

    # Pattern: 预算500, 预算五百
    budget_match = re.search(r"预算\s*(\d+)", text)
    if budget_match:
        price_max = float(budget_match.group(1))
        return price_min, price_max

    budget_cn = re.search(r"预算\s*([一二两三四五六七八九十百千万]+)", text)
    if budget_cn:
        val = _parse_chinese_number(budget_cn.group(1))
        if val:
            return price_min, val

    # Pattern: 500以内, 五百以内, 不超过500, 低于500
    max_match = re.search(r"(\d+)\s*(?:以内|以下|以下的|之内)", text)
    if max_match:
        price_max = float(max_match.group(1))
        return price_min, price_max

    max_cn = re.search(r"([一二两三四五六七八九十百千万]+)\s*(?:块|元|人民币)?\s*(?:以内|以下)", text)
    if max_cn:
        val = _parse_chinese_number(max_cn.group(1))
        if val:
            return price_min, val

    exceed_match = re.search(r"(?:不超过|低于|小于)\s*(\d+)", text)
    if exceed_match:
        price_max = float(exceed_match.group(1))
        return price_min, price_max

    exceed_cn = re.search(r"(?:不超过|低于|小于)\s*([一二两三四五六七八九十百千万]+)", text)
    if exceed_cn:
        val = _parse_chinese_number(exceed_cn.group(1))
        if val:
            return price_min, val

    return price_min, price_max


BRAND_LIST = [
    "波司登", "李宁", "安踏", "骆驼", "阿迪达斯", "耐克", "优衣库",
    "太平鸟", "雪中飞", "雅鹿", "鸭鸭", "鸿星尔克", "361°",
    "北面", "始祖鸟", "哥伦比亚", "Under Armour", "安德玛",
    "罗蒙", "南极人", "乔丹", "FILA", "匹克", "海澜之家",
]

# Non-specific brand quality expressions
BRAND_QUALITY_KEYWORDS = ["大品牌", "品牌大", "大牌", "有保障", "质量好", "靠谱品牌", "品质保障", "知名品牌"]
GENERIC_BRAND_TERMS = set(BRAND_QUALITY_KEYWORDS + ["放心品牌", "可靠品牌", "牌子有保障"])
SIZE_ORDER = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL", "6XL", "7XL"]
VALUE_BRAND_CANDIDATES = ["罗蒙", "雅鹿", "鸭鸭", "雪中飞", "南极人", "骆驼", "李宁", "安踏"]
PREMIUM_BRAND_CANDIDATES = ["波司登", "阿迪达斯", "耐克", "FILA", "优衣库", "李宁", "安踏", "骆驼"]
VALID_GENDERS = {"male", "female"}
VALID_AI_PROVIDERS = {"auto", "gemini", "deepseek", "mimo"}
VALID_VISION_PROVIDERS = {"auto", "gemini", "mimo"}
VALID_MIMO_MODELS = {"mimo-v2.5", "mimo-v2.5-pro", "mimo-v2-omni"}
VALID_STYLES = (
    "常规短外套",
    "短款",
    "轻薄款",
    "绗缝款（排骨款）",
    "面包服",
    "中长款大衣",
    "长款",
    "巴恩风/工装风",
    "派克大衣",
    "马甲",
)
STYLE_KEYWORDS: list[tuple[str, str]] = [
    ("类似风衣", "中长款大衣"),
    ("风衣感", "中长款大衣"),
    ("大衣感", "中长款大衣"),
    ("西服领", "中长款大衣"),
    ("中长款", "中长款大衣"),
    ("风衣", "中长款大衣"),
    ("工装", "巴恩风/工装风"),
    ("巴恩", "巴恩风/工装风"),
    ("多口袋", "巴恩风/工装风"),
    ("山系", "巴恩风/工装风"),
    ("露营", "巴恩风/工装风"),
    ("绗缝", "绗缝款（排骨款）"),
    ("排骨", "绗缝款（排骨款）"),
    ("小龟背", "绗缝款（排骨款）"),
    ("内胆", "绗缝款（排骨款）"),
    ("面包服", "面包服"),
    ("泡芙", "面包服"),
    ("蓬松", "面包服"),
    ("轻薄", "轻薄款"),
    ("轻量", "轻薄款"),
    ("轻盈", "轻薄款"),
    ("短款", "短款"),
    ("短版", "短款"),
    ("过膝", "长款"),
    ("长款", "长款"),
    ("派克", "派克大衣"),
    ("马甲", "马甲"),
    ("背心", "马甲"),
    ("通勤", "常规短外套"),
    ("极简", "常规短外套"),
    ("简约", "常规短外套"),
    ("百搭", "常规短外套"),
    ("基础", "常规短外套"),
    ("学生", "常规短外套"),
]
NEGATION_PREFIXES = (
    "不要",
    "不想要",
    "不喜欢",
    "不考虑",
    "不接受",
    "不选择",
    "不选",
    "别给",
    "别推荐",
    "别要",
    "排除",
    "避免",
    "拒绝",
)
NEGATION_SUFFIXES = ("不要", "不考虑", "不接受", "排除", "避开", "算了")
_PATCH_FIELDS = {
    "color_preference",
    "brand_preference",
    "gender",
    "price_min",
    "price_max",
    "mbti",
    "size",
    "style_preference",
    "ai_provider",
    "vision_provider",
    "mimo_model",
    "gemini_model",
    "deepseek_model",
}


def _is_negated_mention(text: str, start: int, end: int) -> bool:
    """Return True when a value mention is inside an explicit exclusion phrase."""
    before = re.split(r"[，。；！？、,\n]", text[max(0, start - 18):start])[-1]
    after = re.split(r"[，。；！？、,\n]", text[end:end + 10])[0]
    prefix_pattern = "|".join(re.escape(item) for item in NEGATION_PREFIXES)
    suffix_pattern = "|".join(re.escape(item) for item in NEGATION_SUFFIXES)
    if re.search(rf"(?:{prefix_pattern})[^，。；！？、,\n]{{0,8}}$", before):
        return True
    return bool(re.match(rf"[^，。；！？、,\n]{{0,4}}(?:{suffix_pattern})", after))


def _positive_mentions(text: str, keyword: str) -> list[int]:
    return [
        match.start()
        for match in re.finditer(re.escape(keyword), text, flags=re.IGNORECASE)
        if not _is_negated_mention(text, match.start(), match.end())
    ]


def extract_brands(text: str) -> list[str]:
    found: list[tuple[int, str]] = []
    for brand in BRAND_LIST:
        positions = _positive_mentions(text, brand)
        if positions:
            found.append((positions[-1], brand))
    return [brand for _, brand in sorted(found)]


def extract_brand_quality(text: str) -> str | None:
    """Extract non-specific brand quality expressions like '大品牌', '有保障'."""
    for keyword in BRAND_QUALITY_KEYWORDS:
        if keyword in text:
            return "品质保障"
    return None


def sanitize_brand_preference(value: Any) -> str | None:
    """Keep only concrete brands supported by the current catalog vocabulary."""
    if not isinstance(value, str):
        return None
    raw_parts = [part.strip() for part in re.split(r"[,，、/|]+", value) if part.strip()]
    kept: list[str] = []
    for part in raw_parts:
        if part in GENERIC_BRAND_TERMS:
            continue
        if any(term in part for term in GENERIC_BRAND_TERMS):
            continue
        canonical = next((brand for brand in BRAND_LIST if brand.lower() == part.lower()), None)
        if canonical and canonical not in kept:
            kept.append(canonical)
    return "，".join(kept) if kept else None


def infer_brand_candidates_for_quality(text: str, price_max: float | None = None) -> str | None:
    if not extract_brand_quality(text):
        return None
    candidates = VALUE_BRAND_CANDIDATES if price_max is not None and price_max <= 350 else PREMIUM_BRAND_CANDIDATES
    return "，".join(candidates)


def _parse_chinese_height(text: str) -> int | None:
    digit_map = {
        "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    }
    match = re.search(r"一\s*米\s*([五六七八九])\s*([零〇一二两三四五六七八九]?)", text)
    if not match:
        return None
    tens = digit_map.get(match.group(1))
    ones = digit_map.get(match.group(2), 0) if match.group(2) else 0
    if tens is None:
        return None
    return 100 + tens * 10 + ones


def extract_body_metrics(text: str) -> tuple[int | None, float | None]:
    height_cm: int | None = None
    weight_kg: float | None = None

    explicit_height = re.search(r"(?:身高\s*)?(1[5-9]\d|20[0-5])\s*(?:cm|厘米|公分)?", text, re.IGNORECASE)
    if explicit_height:
        height_cm = int(explicit_height.group(1))
    else:
        meter_height = re.search(r"1\s*米\s*([5-9])\s*(\d?)", text)
        if meter_height:
            height_cm = 100 + int(meter_height.group(1)) * 10 + (int(meter_height.group(2)) if meter_height.group(2) else 0)
        else:
            height_cm = _parse_chinese_height(text)

    explicit_weight = re.search(r"(\d{2,3}(?:\.\d+)?)\s*(?:公斤|kg|千克)", text, re.IGNORECASE)
    if explicit_weight:
        weight_kg = float(explicit_weight.group(1))
    else:
        cn_weight = re.search(r"([一二两三四五六七八九十百千万]+)\s*(?:公斤|千克)", text)
        if cn_weight:
            parsed = _parse_chinese_number(cn_weight.group(1))
            if parsed:
                weight_kg = parsed

    return height_cm, weight_kg


def _size_index(size: str) -> int:
    try:
        return SIZE_ORDER.index(size)
    except ValueError:
        return -1


def _max_size(*sizes: str | None) -> str | None:
    valid = [size for size in sizes if size in SIZE_ORDER]
    if not valid:
        return None
    return max(valid, key=_size_index)


def infer_size_from_body_metrics(text: str) -> str | None:
    height_cm, weight_kg = extract_body_metrics(text)
    if height_cm is None:
        return None

    if height_cm <= 160:
        base = "S"
    elif height_cm <= 170:
        base = "M"
    elif height_cm <= 175:
        base = "L"
    elif height_cm <= 180:
        base = "XL"
    elif height_cm <= 185:
        base = "2XL"
    else:
        base = "3XL"

    if weight_kg is None:
        if "微胖" in text or "偏胖" in text or "胖" in text:
            return _max_size(base, "2XL" if height_cm >= 175 else "XL")
        return base

    bmi = weight_kg / ((height_cm / 100) ** 2)
    if bmi >= 28:
        upgraded = SIZE_ORDER[min(_size_index(base) + 2, len(SIZE_ORDER) - 1)]
    elif bmi >= 23.5:
        upgraded = SIZE_ORDER[min(_size_index(base) + 1, len(SIZE_ORDER) - 1)]
    else:
        upgraded = base

    if height_cm >= 178 and weight_kg >= 75:
        upgraded = _max_size(upgraded, "2XL") or upgraded
    if height_cm >= 180 and weight_kg >= 90:
        upgraded = _max_size(upgraded, "3XL") or upgraded
    return upgraded


def extract_size(text: str) -> str | None:
    # Chinese size expressions: 大码, 加大码
    if "加大码" in text or "加加大" in text:
        return "3XL"
    if "大码" in text:
        return "2XL"

    # Letter sizes — also match embedded in Chinese like "大概XL", "个人穿XL"
    size_match = re.search(r"(?:大概|个人穿|尺码|穿|要|是)?\s*(XS|S|M|L|XL|2XL|3XL|4XL|5XL|6XL|7XL|XXL|XXXL)\b", text, re.IGNORECASE)
    if size_match:
        raw = size_match.group(1).upper()
        aliases = {"XXL": "2XL", "XXXL": "3XL"}
        return aliases.get(raw, raw)

    metric_size = infer_size_from_body_metrics(text)
    if metric_size:
        return metric_size

    # Height-based size: 身高170, 一米七五, 180
    height_match = re.search(r"身高\s*(\d{3})", text)
    if height_match:
        h = int(height_match.group(1))
        if h <= 160:
            return "S"
        if h <= 170:
            return "M"
        if h <= 175:
            return "L"
        if h <= 180:
            return "XL"
        if h <= 185:
            return "2XL"
        return "3XL"

    # Bare number like 180, 175
    bare_height = re.search(r"(?<!\d)(1[5-9]\d)(?!\d)", text)
    if bare_height:
        h = int(bare_height.group(1))
        if 150 <= h <= 200:
            if h <= 160:
                return "S"
            if h <= 170:
                return "M"
            if h <= 175:
                return "L"
            if h <= 180:
                return "XL"
            if h <= 185:
                return "2XL"
            return "3XL"

    # Chinese height: 一米七五, 一米八
    cn_height = re.search(r"一米([七八五])", text)
    if cn_height:
        digit_map = {"五": 155, "七": 170, "八": 180}
        return "L" if digit_map.get(cn_height.group(1), 0) <= 175 else "XL"

    return None


def sanitize_recommend_fields(text: str, form_patch: dict[str, Any]) -> dict[str, Any]:
    """Post-process LLM/rule fields so structured filters stay catalog-compatible."""
    cleaned = {key: value for key, value in (form_patch or {}).items() if key in _PATCH_FIELDS}

    gender = extract_gender(text)
    if gender:
        cleaned["gender"] = gender
    elif cleaned.get("gender") not in VALID_GENDERS:
        cleaned.pop("gender", None)

    color = extract_color(text)
    if color:
        cleaned["color_preference"] = color
    elif cleaned.get("color_preference") not in VALID_COLORS:
        cleaned.pop("color_preference", None)

    price_min, price_max = extract_price(text)
    if price_min is not None:
        cleaned["price_min"] = price_min
    else:
        cleaned.pop("price_min", None)
    if price_max is not None:
        cleaned["price_max"] = price_max
    else:
        cleaned.pop("price_max", None)

    if (
        isinstance(cleaned.get("price_min"), (int, float))
        and isinstance(cleaned.get("price_max"), (int, float))
        and cleaned["price_min"] > cleaned["price_max"]
    ):
        cleaned["price_min"], cleaned["price_max"] = cleaned["price_max"], cleaned["price_min"]

    explicit_brands = extract_brands(text)
    if explicit_brands:
        cleaned["brand_preference"] = "，".join(explicit_brands)
    else:
        cleaned.pop("brand_preference", None)

    if not cleaned.get("brand_preference"):
        brand_candidates = infer_brand_candidates_for_quality(text, cleaned.get("price_max"))
        if brand_candidates:
            cleaned["brand_preference"] = brand_candidates

    size = extract_size(text)
    if size in SIZE_ORDER:
        cleaned["size"] = size
    else:
        cleaned.pop("size", None)

    style = extract_style(text)
    if style:
        cleaned["style_preference"] = style
    else:
        cleaned.pop("style_preference", None)

    mbti = extract_mbti(text)
    if mbti:
        cleaned["mbti"] = mbti
    else:
        cleaned.pop("mbti", None)

    ai_provider, mimo_model = extract_ai_provider(text)
    vision_provider = extract_vision_provider(text)
    if ai_provider in VALID_AI_PROVIDERS:
        cleaned["ai_provider"] = ai_provider
    else:
        cleaned.pop("ai_provider", None)
    if vision_provider in VALID_VISION_PROVIDERS:
        cleaned["vision_provider"] = vision_provider
    else:
        cleaned.pop("vision_provider", None)
    if mimo_model in VALID_MIMO_MODELS:
        cleaned["mimo_model"] = mimo_model
    else:
        cleaned.pop("mimo_model", None)

    for model_field in ("gemini_model", "deepseek_model"):
        cleaned.pop(model_field, None)

    return cleaned


MBTI_TYPES = {
    "INTJ", "INTP", "ENTJ", "ENTP",
    "INFJ", "INFP", "ENFJ", "ENFP",
    "ISTJ", "ISFJ", "ESTJ", "ESFJ",
    "ISTP", "ISFP", "ESTP", "ESFP",
}


def extract_mbti(text: str) -> str | None:
    upper = text.upper()
    for mbti in MBTI_TYPES:
        if mbti in upper:
            return mbti
    return None


def extract_style(text: str) -> str | None:
    found: list[tuple[int, str]] = []
    for keyword, style in STYLE_KEYWORDS:
        for position in _positive_mentions(text, keyword):
            found.append((position, style))
    if not found:
        return None
    found.sort(key=lambda item: item[0])
    return found[0][1]


AI_PROVIDER_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(小米|MiMo|mimo|小米大模型)", re.IGNORECASE), "mimo"),
    (re.compile(r"(Gemini|gemini|谷歌)", re.IGNORECASE), "gemini"),
    (re.compile(r"(Deepseek|deepseek|深度求索)", re.IGNORECASE), "deepseek"),
]

# Vision-specific patterns: detect image analysis engine preference
VISION_PROVIDER_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(Gemini|gemini|谷歌).*(图|照|看图|分析照|图像|识别)", re.IGNORECASE), "gemini"),
    (re.compile(r"(图|照|看图|分析照|图像|识别).*(Gemini|gemini|谷歌)", re.IGNORECASE), "gemini"),
    (re.compile(r"(小米|MiMo|mimo).*(图|照|看图|分析照|图像|识别)", re.IGNORECASE), "mimo"),
    (re.compile(r"(图|照|看图|分析照|图像|识别).*(小米|MiMo|mimo)", re.IGNORECASE), "mimo"),
]


def extract_ai_provider(text: str) -> tuple[str | None, str | None]:
    for pattern, provider in AI_PROVIDER_MAP:
        if pattern.search(text):
            if provider == "mimo":
                return provider, "mimo-v2.5"
            return provider, None
    return None, None


def extract_vision_provider(text: str) -> str | None:
    """Extract vision provider preference from user message."""
    for pattern, provider in VISION_PROVIDER_MAP:
        if pattern.search(text):
            return provider
    return None


def is_recommend_intent(text: str) -> bool:
    """Check if the message looks like a recommendation request."""
    recommend_keywords = [
        "推荐", "想要", "想买", "找", "有没有", "适合", "帮我",
        "羽绒服", "外套", "颜色", "尺码", "预算", "价格",
        "黑色", "白色", "男款", "女款", "品牌",
    ]
    for kw in recommend_keywords:
        if kw in text:
            return True
    return False


def extract_recommend_fields(text: str) -> dict[str, Any]:
    """Extract structured recommendation fields from natural language text."""
    gender = extract_gender(text)
    color = extract_color(text)
    price_min, price_max = extract_price(text)
    brands = extract_brands(text)
    brand_quality = extract_brand_quality(text)
    size = extract_size(text)
    mbti = extract_mbti(text)
    style = extract_style(text)
    ai_provider, mimo_model = extract_ai_provider(text)
    vision_provider = extract_vision_provider(text)

    form_patch: dict[str, Any] = {}

    if gender:
        form_patch["gender"] = gender
    if color:
        form_patch["color_preference"] = color
    if price_min is not None:
        form_patch["price_min"] = price_min
    if price_max is not None:
        form_patch["price_max"] = price_max

    # Brand: specific brands take priority; quality expressions as fallback
    if brands:
        form_patch["brand_preference"] = "，".join(brands)
    elif brand_quality:
        brand_candidates = infer_brand_candidates_for_quality(text, price_max)
        if brand_candidates:
            form_patch["brand_preference"] = brand_candidates

    if style:
        form_patch["style_preference"] = style

    if size:
        form_patch["size"] = size
    if mbti:
        form_patch["mbti"] = mbti
    # Only fill provider fields when user explicitly mentions them.
    # Don't default-fill — let the backend use its configured defaults.
    if ai_provider:
        form_patch["ai_provider"] = ai_provider
    if vision_provider:
        form_patch["vision_provider"] = vision_provider
        # Sync ai_provider if user explicitly set vision provider but not ai_provider
        if not ai_provider:
            form_patch["ai_provider"] = vision_provider
    if mimo_model:
        form_patch["mimo_model"] = mimo_model

    return form_patch
