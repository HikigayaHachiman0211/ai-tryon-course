"""Product catalog for the try-on workbench — loads from database.json at startup."""

import json
import os
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

_CATALOG: list[dict] = []
_SUPPORTED_LOCALES = ("zh-CN", "en", "ja")
_DEFAULT_LOCALE = "zh-CN"
_STYLE_LABELS = {
    "en": {"户外运动": "Outdoor", "商务通勤": "Business", "日常休闲": "Casual", "时尚潮流": "Fashion", "轻薄便携": "Lightweight", "极寒防护": "Extreme cold", "亲子家庭": "Family"},
    "ja": {"户外运动": "アウトドア", "商务通勤": "ビジネス", "日常休闲": "カジュアル", "时尚潮流": "ファッション", "轻薄便携": "軽量", "极寒防护": "極寒対応", "亲子家庭": "ファミリー"},
}
_STYLE_LABELS.update({
    "常规短外套": {"en": "Regular short jacket", "ja": "レギュラーショートジャケット"},
    "短款": {"en": "Cropped jacket", "ja": "ショートジャケット"},
    "绗缝款（排骨款）": {"en": "Quilted channel jacket", "ja": "キルティングジャケット"},
    "面包服": {"en": "Puffer jacket", "ja": "パファージャケット"},
    "长款": {"en": "Long jacket", "ja": "ロングジャケット"},
    "轻薄款": {"en": "Lightweight jacket", "ja": "ライトウェイトジャケット"},
    "巴恩风/工装风": {"en": "Barn/workwear jacket", "ja": "バーン／ワークウェアジャケット"},
    "中长款大衣": {"en": "Mid-length coat", "ja": "ミドル丈コート"},
    "马甲": {"en": "Down vest", "ja": "ダウンベスト"},
    "派克大衣": {"en": "Parka", "ja": "パーカ"},
})
_COLOR_LABELS = {
    "en": {"黑色": "Black", "白色": "White", "灰色": "Gray", "深蓝": "Navy", "浅蓝": "Light blue", "红色": "Red", "绿色": "Green", "棕色": "Brown", "卡其": "Khaki", "粉色": "Pink", "紫色": "Purple", "橙色": "Orange", "黄色": "Yellow", "米色": "Beige", "银色": "Silver", "金色": "Gold", "酒红": "Wine red"},
    "ja": {"黑色": "黒", "白色": "白", "灰色": "グレー", "深蓝": "ネイビー", "浅蓝": "ライトブルー", "红色": "赤", "绿色": "緑", "棕色": "ブラウン", "卡其": "カーキ", "粉色": "ピンク", "紫色": "紫", "橙色": "オレンジ", "黄色": "黄", "米色": "ベージュ", "银色": "シルバー", "金色": "ゴールド", "酒红": "ワインレッド"},
}
_COLOR_FILTER_NAMES = {
    "丛林绿": ("Jungle green", "ジャングルグリーン"),
    "东北黑": ("Northeast black", "ノースイーストブラック"),
    "中灰色系": ("Medium gray", "ミディアムグレー系"),
    "乌木棕": ("Ebony brown", "エボニーブラウン"),
    "乌龙灰": ("Oolong gray", "ウーロングレー"),
    "乔丹远红": ("Jordan red", "ジョーダンレッド"),
    "云墨黑": ("Cloud ink black", "雲墨ブラック"),
    "优质白": ("Premium white", "プレミアムホワイト"),
    "传奇蓝": ("Legend blue", "レジェンドブルー"),
    "保暖防风翻领高级白": ("Warm windproof lapel white", "保温・防風ラペルホワイト"),
    "光影蓝": ("Light and shadow blue", "ライトシャドーブルー"),
    "军帆绿": ("Military green", "ミリタリーグリーン"),
    "冬季保暖加厚男生白": ("Men's winter insulated white", "メンズ冬用厚手ホワイト"),
    "冬季加厚白": ("Winter insulated white", "冬用厚手ホワイト"),
    "冬季工装帅气男装白": ("Men's winter workwear white", "メンズ冬用ワークホワイト"),
}
_COLOR_CHARACTER_LABELS = {
    "黑": ("Black", "ブラック"), "白": ("White", "ホワイト"),
    "灰": ("Gray", "グレー"), "蓝": ("Blue", "ブルー"),
    "绿": ("Green", "グリーン"), "红": ("Red", "レッド"),
    "棕": ("Brown", "ブラウン"), "咖": ("Brown", "ブラウン"),
    "粉": ("Pink", "ピンク"), "紫": ("Purple", "パープル"),
    "橙": ("Orange", "オレンジ"), "黄": ("Yellow", "イエロー"),
    "米": ("Beige", "ベージュ"), "杏": ("Apricot", "アプリコット"),
    "银": ("Silver", "シルバー"), "金": ("Gold", "ゴールド"),
}
_PLATFORM_LABELS = {"en": {"jd": "JD", "taobao": "Taobao", "unknown": "Unlabeled"}, "ja": {"jd": "JD", "taobao": "Taobao", "unknown": "未分類"}}
_GENDER_LABELS = {"en": {"male": "Men", "female": "Women", "unisex": "Unisex", "unknown": ""}, "ja": {"male": "メンズ", "female": "レディース", "unisex": "ユニセックス", "unknown": ""}}

PUBLIC_IMAGE_BASE_URL = str(os.getenv("PUBLIC_IMAGE_BASE_URL", "") or "").strip()
PUBLIC_IMAGE_PREFIX = str(os.getenv("PUBLIC_IMAGE_PREFIX", "羽绒服_png") or "羽绒服_png").strip().strip("/")
RESULTS_GCS_BUCKET = str(os.getenv("RESULTS_GCS_BUCKET", "") or "").strip()
AZURE_STORAGE_ACCOUNT_NAME = str(os.getenv("AZURE_STORAGE_ACCOUNT_NAME", "") or "").strip()
AZURE_PRODUCT_CONTAINER = str(os.getenv("AZURE_PRODUCT_CONTAINER", "product-assets") or "product-assets").strip().strip("/")
OBJECT_STORAGE_PROVIDER = str(os.getenv("OBJECT_STORAGE_PROVIDER", "") or "").strip().lower()
OSS_REGION = str(os.getenv("OSS_REGION", "") or "").strip()
OSS_PRODUCT_BUCKET = str(os.getenv("OSS_PRODUCT_BUCKET", "") or "").strip()

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


def _normalize_locale(locale: Optional[str]) -> str:
    value = str(locale or "").strip().lower().replace("_", "-")
    if value == "zh" or value.startswith("zh-"):
        return "zh-CN"
    if value == "en" or value.startswith("en-"):
        return "en"
    if value == "ja" or value.startswith("ja-"):
        return "ja"
    return _DEFAULT_LOCALE


def _localized_item(item: dict, locale: str) -> dict:
    target = _normalize_locale(locale)
    display = (item.get("display") or {}).get(target) or {}
    if target == "zh-CN":
        display = display or {
            "title": item.get("title", ""), "styleType": item.get("style_type", ""),
            "colorFamily": item.get("color_family", ""), "bodyFit": item.get("body_fit", ""),
            "styleFeatures": item.get("style_features", []), "functionFeatures": item.get("function_features", []),
            "sizeNotes": item.get("size_notes", ""),
        }
    elif not display:
        style = _localized_filter_label(str(item.get("style_type") or ""), target, kind="style")
        color = _localized_filter_label(str(item.get("color_family") or ""), target, kind="color")
        gender = _GENDER_LABELS.get(target, {}).get(item.get("product_gender", ""), "")
        title = (f"{gender} {style} down jacket — {color} (#{item.get('id', '')})" if target == "en"
                 else f"{gender} {style} ダウンジャケット — {color} (#{item.get('id', '')})")
        features = {
            "保暖": ("Warmth", "保温"), "防风": ("Windproof", "防風"),
            "防水": ("Waterproof", "防水"), "连帽": ("Hooded", "フード付き"),
            "轻薄": ("Lightweight", "軽量"), "加厚": ("Extra insulation", "厚手"),
        }
        index = 0 if target == "en" else 1
        display = {
            "title": title.strip(), "styleType": style, "colorFamily": color,
            "bodyFit": "See the size chart" if target == "en" else "サイズ表をご確認ください",
            "styleFeatures": [features[value][index] for value in item.get("style_features", []) if value in features],
            "functionFeatures": [features[value][index] for value in item.get("function_features", []) if value in features],
            "sizeNotes": "See the size chart." if target == "en" else "サイズ表をご確認ください。",
        }
    result = dict(item)
    result["locale"] = target
    result["title"] = display.get("title", item.get("title", ""))
    result["style_type"] = display.get("styleType", item.get("style_type", ""))
    result["color_family"] = display.get("colorFamily", item.get("color_family", ""))
    result["body_fit"] = display.get("bodyFit", item.get("body_fit", ""))
    result["style_features"] = display.get("styleFeatures", item.get("style_features", []))
    result["function_features"] = display.get("functionFeatures", item.get("function_features", []))
    result["size_notes"] = display.get("sizeNotes", item.get("size_notes", ""))
    result["platform"] = _PLATFORM_LABELS.get(target, {}).get(item.get("platform_key", ""), item.get("platform", ""))
    result["gender_label"] = _GENDER_LABELS.get(target, {}).get(item.get("product_gender", ""), item.get("gender_label", ""))
    result["display"] = display
    result["canonical"] = item.get("canonical") or {
        "product_key": item.get("product_key"), "price": item.get("price"), "image_path": item.get("image_path"),
        "platform": item.get("platform_key"), "gender": item.get("product_gender"), "brand": item.get("brand"),
        "title": item.get("title"), "style_type": item.get("style_type"), "color_family": item.get("color_family"),
    }
    return result


def _localized_filter_label(value: str, locale: str, *, kind: str) -> str:
    if locale == _DEFAULT_LOCALE:
        return value
    if kind == "style":
        return _STYLE_LABELS.get(value, {}).get(locale, "Other style" if locale == "en" else "その他のスタイル")
    color = str(value or "")
    language_index = 0 if locale == "en" else 1
    if color in _COLOR_FILTER_NAMES:
        return _COLOR_FILTER_NAMES[color][language_index]
    for source, labels in _COLOR_LABELS.get(locale, {}).items():
        if source in color:
            return labels
    for character in color:
        if character in _COLOR_CHARACTER_LABELS:
            return _COLOR_CHARACTER_LABELS[character][language_index]
    return "Other color" if locale == "en" else "その他のカラー"


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

    if OBJECT_STORAGE_PROVIDER == "oss":
        if OSS_REGION and OSS_PRODUCT_BUCKET:
            return f"https://{OSS_PRODUCT_BUCKET}.oss-{OSS_REGION}.aliyuncs.com/{quote(filename)}"
        return ""

    if AZURE_STORAGE_ACCOUNT_NAME:
        return f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{quote(AZURE_PRODUCT_CONTAINER, safe='/')}/{quote(filename)}"

    # Compatibility fallback for the historical Cloud Run deployment.
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
    read_model_candidates = [
        Path(__file__).resolve().parents[1] / "read-model" / "catalog.i18n.json",
        Path("/app/read-model/catalog.i18n.json"),
    ]
    for read_model_path in read_model_candidates:
        if read_model_path.exists():
            data = json.loads(read_model_path.read_text(encoding="utf-8"))
            _CATALOG = []
            for row in data.get("items", []):
                zh = (row.get("display") or {}).get("zh-CN", {})
                canonical = row.get("canonical") or {}
                _CATALOG.append({
                    "id": row.get("id"), "product_key": row.get("product_key"), "title": zh.get("title", ""),
                    "price": float(row.get("price", 0) or 0), "image_path": row.get("image_path", ""),
                    "image_url": _build_image_url(row.get("image_path", "")), "product_url": row.get("product_url"),
                    "brand": canonical.get("brand"), "platform_key": canonical.get("platform", "unknown"),
                    "platform": _platform_label(canonical.get("platform", "unknown")), "style_type": zh.get("styleType", ""),
                    "color_family": zh.get("colorFamily", ""), "body_fit": zh.get("bodyFit", ""),
                    "style_features": zh.get("styleFeatures", []), "function_features": zh.get("functionFeatures", []),
                    "size_notes": zh.get("sizeNotes", ""), "product_gender": canonical.get("gender", "unknown"),
                    "gender_label": _gender_label(canonical.get("gender", "unknown")), "display": row.get("display", {}),
                    "canonical": canonical, "search_text": row.get("search_text", ""),
                })
            print(f"[products] loaded {len(_CATALOG)} products from {read_model_path}")
            return
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


def _match_query(item: dict, query: str, locale: str = _DEFAULT_LOCALE) -> bool:
    if not query:
        return True
    localized = (item.get("display") or {}).get(_normalize_locale(locale), {})
    haystack = " ".join([
        item["title"], item.get("brand") or "", item["style_type"],
        item["color_family"], item["body_fit"],
        *item["style_features"], *item["function_features"],
        str(item["id"]), item.get("search_text", ""),
        localized.get("title", ""), localized.get("styleType", ""), localized.get("colorFamily", ""),
        "black blue white red outdoor business casual men women jacket down jd taobao",
        "黒 白 赤 アウトドア ビジネス カジュアル メンズ レディース ダウン",
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
    locale: str = _DEFAULT_LOCALE,
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
        items = [i for i in items if _match_query(i, query, locale)]

    # Sort by price
    items = sorted(items, key=lambda i: (i["price"], i["id"]))

    safe_offset = max(0, offset)
    safe_limit = max(1, min(120, limit))
    paged = items[safe_offset:safe_offset + safe_limit]

    return {
        "locale": _normalize_locale(locale),
        "items": [_localized_item(i, _normalize_locale(locale)) for i in paged],
        "total": len(items),
        "offset": safe_offset,
        "limit": safe_limit,
    }


def get_filter_options(locale: str = _DEFAULT_LOCALE) -> dict[str, Any]:
    """Return available filter values for the frontend."""
    style_types: set[str] = set()
    color_families: set[str] = set()
    for item in _CATALOG:
        if item["style_type"]:
            style_types.add(item["style_type"])
        if item["color_family"]:
            color_families.add(item["color_family"])
    return {
        "style_types": [{"key": value, "label": _localized_filter_label(value, _normalize_locale(locale), kind="style")} for value in sorted(style_types)],
        "color_families": [{"key": value, "label": _localized_filter_label(value, _normalize_locale(locale), kind="color")} for value in sorted(color_families)],
        "locale": _normalize_locale(locale),
        "platforms": [{"key": "jd", "label": _PLATFORM_LABELS.get(_normalize_locale(locale), {}).get("jd", "京东")}, {"key": "taobao", "label": _PLATFORM_LABELS.get(_normalize_locale(locale), {}).get("taobao", "淘宝")}],
        "genders": [{"key": "male", "label": _GENDER_LABELS.get(_normalize_locale(locale), {}).get("male", "男款")}, {"key": "female", "label": _GENDER_LABELS.get(_normalize_locale(locale), {}).get("female", "女款")}],
        "total": len(_CATALOG),
    }
