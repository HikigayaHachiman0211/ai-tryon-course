"""Product catalog for the try-on workbench — loads from database.json at startup."""

import json
import os
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

_CATALOG: list[dict] = []

PUBLIC_IMAGE_BASE_URL = str(os.getenv("PUBLIC_IMAGE_BASE_URL", "") or "").strip()
PUBLIC_IMAGE_PREFIX = str(os.getenv("PUBLIC_IMAGE_PREFIX", "羽绒服_png") or "羽绒服_png").strip().strip("/")
RESULTS_GCS_BUCKET = str(os.getenv("RESULTS_GCS_BUCKET", "") or "").strip()

MALE_GENDER_KEYWORDS = ["【男款】", "男士", "男款", "男装", "男子", "男"]
FEMALE_GENDER_KEYWORDS = ["【女款】", "女士", "女款", "女装", "女子", "女"]
UNISEX_GENDER_KEYWORDS = ["男女同款", "男女款", "情侣款", "情侣", "中性", "男女士同款", "男女"]
CHILD_KEYWORDS = ["男童", "女童", "儿童", "童装", "婴童", "宝宝", "婴儿", "小童", "大童", "幼童"]

BRAND_NAMES = [
    "波司登", "鸭鸭", "安踏", "李宁", "耐克", "阿迪达斯", "优衣库", "骆驼",
    "北面", "The North Face", "Columbia", "始祖鸟", "迪卡侬", "海澜之家",
    "太平鸟", "雪中飞", "雅鹿", "千仞岗", "花花公子", "稻草人", "罗蒙",
    "南极人", "恒源祥", "森马", "特步", "匹克", "361度", "鸿星尔克",
    "猫人", "红豆", "七匹狼", "劲霸", "九牧王", "报喜鸟",
    "Under Armour", "安德玛", "Nike", "Adidas", "Puma", "New Balance",
    "迪凯希", "迪凯布", "迪凯瑞", "迪凯纳",
]


def _infer_gender(title: str) -> str:
    if any(kw in title for kw in UNISEX_GENDER_KEYWORDS):
        return "unisex"
    if "【男款】" in title and "【女款】" not in title:
        return "male"
    if "【女款】" in title and "【男款】" not in title:
        return "female"
    male_pos = [title.rfind(kw) for kw in MALE_GENDER_KEYWORDS if kw in title]
    female_pos = [title.rfind(kw) for kw in FEMALE_GENDER_KEYWORDS if kw in title]
    if male_pos and female_pos:
        return "male" if max(male_pos) > max(female_pos) else "female"
    if male_pos:
        return "male"
    if female_pos:
        return "female"
    return "unknown"


def _gender_label(g: str) -> str:
    return {"male": "男款", "female": "女款", "unisex": "男女同款"}.get(g, "")


def _is_child(title: str) -> bool:
    return any(kw in title for kw in CHILD_KEYWORDS)


def _infer_platform(image_path: str) -> str:
    p = (image_path or "").replace("\\", "/").lstrip("/").lower()
    if p.startswith("downloaded_jd_images/"):
        return "jd"
    if p.startswith("img羽绒服") or p.startswith("img\u7fbd\u7ed2\u670d"):
        return "taobao"
    return "unknown"


def _platform_label(key: str) -> str:
    return {"jd": "京东", "taobao": "淘宝"}.get(key, "未标注")


def _extract_brand(title: str, style_features: list) -> Optional[str]:
    for feat in style_features:
        s = str(feat)
        if s.startswith("品牌:") or s.startswith("品牌："):
            return s.split(":", 1)[-1].split("：", 1)[-1].strip()
    for brand in BRAND_NAMES:
        if brand in title:
            return brand
    return None


def _build_image_url(image_path: str) -> str:
    if image_path.startswith(("http://", "https://")):
        return image_path

    normalized = image_path.replace("\\", "/").lstrip("/")
    filename = Path(normalized).name

    if not filename:
        return ""

    if PUBLIC_IMAGE_BASE_URL:
        return f"{PUBLIC_IMAGE_BASE_URL.rstrip('/')}/{quote(filename)}"

    # Fallback for Cloud Run: build public GCS URL when PUBLIC_IMAGE_BASE_URL is absent.
    if RESULTS_GCS_BUCKET:
        if PUBLIC_IMAGE_PREFIX:
            return f"https://storage.googleapis.com/{RESULTS_GCS_BUCKET}/{quote(PUBLIC_IMAGE_PREFIX, safe='/')}/{quote(filename)}"
        return f"https://storage.googleapis.com/{RESULTS_GCS_BUCKET}/{quote(filename)}"

    return ""


def _visible_features(features: list) -> list[str]:
    return [str(f) for f in features if not str(f).startswith(("品牌:", "品牌："))]


def load_catalog(path: Optional[str] = None):
    """Load database.json into memory. Called once at startup."""
    global _CATALOG
    if path is None:
        candidates = [
            Path(__file__).resolve().parents[1] / "database.json",
            Path("/app/database.json"),
        ]
        for c in candidates:
            if c.exists():
                path = str(c)
                break
    if not path or not Path(path).exists():
        print("[products] database.json not found, catalog empty")
        return
    with open(path, "r", encoding="utf-8") as f:
        rows = json.load(f)
    catalog = []
    for idx, row in enumerate(rows, 1):
        title = str(row.get("商品标题", "")).strip()
        if not title:
            continue
        if _is_child(title):
            continue
        image_path = str(row.get("图片路径", ""))
        style_features = row.get("风格特征") or []
        func_features = row.get("功能属性") or []
        gender = _infer_gender(title)
        platform_key = _infer_platform(image_path)
        catalog.append({
            "id": idx,
            "title": title,
            "price": float(row.get("价格", 0)),
            "image_url": _build_image_url(image_path),
            "image_path": image_path,
            "brand": _extract_brand(title, style_features),
            "platform_key": platform_key,
            "platform": _platform_label(platform_key),
            "style_type": str(row.get("款式类型", "")),
            "color_family": str(row.get("精准颜色色系", "")),
            "body_fit": str(row.get("版型与身材适配度", "")),
            "style_features": _visible_features(style_features),
            "function_features": [str(f) for f in func_features],
            "product_gender": gender,
            "gender_label": _gender_label(gender),
        })
    _CATALOG = catalog
    print(f"[products] loaded {len(_CATALOG)} products from {path}")


def _match_query(item: dict, query: str) -> bool:
    if not query:
        return True
    haystack = " ".join([
        item["title"], item.get("brand") or "", item["style_type"],
        item["color_family"], item["body_fit"],
        *item["style_features"], *item["function_features"],
        str(item["id"]),
    ]).lower()
    return all(tok in haystack for tok in query.lower().split())


def list_products(
    *,
    query: Optional[str] = None,
    gender: Optional[str] = None,
    platform: Optional[str] = None,
    style_type: Optional[str] = None,
    color: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    offset: int = 0,
    limit: int = 60,
) -> dict[str, Any]:
    items = _CATALOG

    # Gender filter
    if gender:
        g = gender.strip().lower()
        if g in ("male", "男", "男款"):
            items = [i for i in items if i["product_gender"] in ("male", "unisex")]
        elif g in ("female", "女", "女款"):
            items = [i for i in items if i["product_gender"] in ("female", "unisex")]

    # Platform filter
    if platform:
        p = platform.strip().lower()
        if p in ("jd", "京东"):
            items = [i for i in items if i["platform_key"] == "jd"]
        elif p in ("taobao", "淘宝"):
            items = [i for i in items if i["platform_key"] == "taobao"]

    # Style type filter
    if style_type:
        st = style_type.strip()
        items = [i for i in items if st in i["style_type"]]

    # Color filter
    if color:
        c = color.strip()
        items = [i for i in items if c in i["color_family"]]

    # Price filter
    if price_min is not None:
        items = [i for i in items if i["price"] >= price_min]
    if price_max is not None:
        items = [i for i in items if i["price"] <= price_max]

    # Text query search
    if query:
        items = [i for i in items if _match_query(i, query)]

    # Sort by price
    items = sorted(items, key=lambda i: (i["price"], i["id"]))

    safe_offset = max(0, offset)
    safe_limit = max(1, min(120, limit))
    paged = items[safe_offset:safe_offset + safe_limit]

    return {
        "items": paged,
        "total": len(items),
        "offset": safe_offset,
        "limit": safe_limit,
    }


def get_filter_options() -> dict[str, Any]:
    """Return available filter values for the frontend."""
    style_types: set[str] = set()
    color_families: set[str] = set()
    for item in _CATALOG:
        if item["style_type"]:
            style_types.add(item["style_type"])
        if item["color_family"]:
            color_families.add(item["color_family"])
    return {
        "style_types": sorted(style_types),
        "color_families": sorted(color_families),
        "platforms": [{"key": "jd", "label": "京东"}, {"key": "taobao", "label": "淘宝"}],
        "genders": [{"key": "male", "label": "男款"}, {"key": "female", "label": "女款"}],
        "total": len(_CATALOG),
    }
