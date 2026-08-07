from __future__ import annotations

from typing import Any

from app.database import Product


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


def get_gender_label(product_gender: str) -> str:
    labels = {
        "male": "男款",
        "female": "女款",
        "unisex": "中性/同款",
        "unknown": "未标注",
    }
    return labels.get(product_gender, "未标注")
