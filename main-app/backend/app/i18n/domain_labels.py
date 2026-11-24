from __future__ import annotations

import re

from app.catalog_seed import BRAND_ALIASES
from app.database import Product
from app.product_attributes import get_product_brand, get_visible_style_features
from app.recommendation_rules import classify_color_group, ensure_list, infer_product_gender

STYLE_LABELS = {
    "常规短外套": {"zh-CN": "常规短外套", "en": "Regular short jacket", "ja": "レギュラーショートジャケット"},
    "短款": {"zh-CN": "短款", "en": "Cropped jacket", "ja": "ショートジャケット"},
    "绗缝款（排骨款）": {"zh-CN": "绗缝款（排骨款）", "en": "Quilted channel jacket", "ja": "キルティングジャケット"},
    "面包服": {"zh-CN": "面包服", "en": "Puffer jacket", "ja": "パファージャケット"},
    "长款": {"zh-CN": "长款", "en": "Long jacket", "ja": "ロングジャケット"},
    "轻薄款": {"zh-CN": "轻薄款", "en": "Lightweight jacket", "ja": "ライトウェイトジャケット"},
    "巴恩风/工装风": {"zh-CN": "巴恩风/工装风", "en": "Barn/workwear jacket", "ja": "バーン／ワークウェアジャケット"},
    "中长款大衣": {"zh-CN": "中长款大衣", "en": "Mid-length coat", "ja": "ミドル丈コート"},
    "马甲": {"zh-CN": "马甲", "en": "Down vest", "ja": "ダウンベスト"},
    "派克大衣": {"zh-CN": "派克大衣", "en": "Parka", "ja": "パーカ"},
}

BODY_FIT_LABELS = {
    "常规版型，适合大多数标准身材": {"zh-CN": "常规版型，适合大多数标准身材", "en": "Regular fit for most standard builds", "ja": "標準体型に合うレギュラーフィット"},
    "宽松廓形，适合标准到微胖身材，利于叠穿": {"zh-CN": "宽松廓形，适合标准到微胖身材，利于叠穿", "en": "Relaxed silhouette for standard to fuller builds; easy to layer", "ja": "標準体型からふっくら体型まで対応するゆったりシルエット"},
    "蓬松宽松版，适合标准到微胖身材，包裹感更强": {"zh-CN": "蓬松宽松版，适合标准到微胖身材，包裹感更强", "en": "Lofty relaxed fit with extra coverage for standard to fuller builds", "ja": "標準体型からふっくら体型まで包み込むボリュームシルエット"},
    "标准直筒短版，适合标准身材与小个子日常穿搭": {"zh-CN": "标准直筒短版，适合标准身材与小个子日常穿搭", "en": "Straight short fit for standard builds and petite everyday styling", "ja": "標準体型や小柄な方の日常に合うストレートショートフィット"},
    "直筒或微宽松长版，适合高个身材或需要遮臀保暖的人群": {"zh-CN": "直筒或微宽松长版，适合高个身材或需要遮臀保暖的人群", "en": "Straight or slightly relaxed long fit for taller builds or extra coverage", "ja": "高身長の方やヒップまで暖かく覆いたい方に合うロングフィット"},
    "修身版，适合纤细到标准身材": {"zh-CN": "修身版，适合纤细到标准身材", "en": "Slim fit for slim to standard builds", "ja": "細身から標準体型に合うスリムフィット"},
    "大码宽松版，适合高壮或微胖身材": {"zh-CN": "大码宽松版，适合高壮或微胖身材", "en": "Plus relaxed fit for tall, broad, or fuller builds", "ja": "高身長・がっしり体型・ふっくら体型に合う大きめのゆったりフィット"},
    "标准直筒版，适合叠穿，标准身材友好": {"zh-CN": "标准直筒版，适合叠穿，标准身材友好", "en": "Straight standard fit designed for layering", "ja": "レイヤードしやすい標準ストレートフィット"},
}

FEATURE_LABELS = {
    "保暖": {"zh-CN": "保暖", "en": "Warmth", "ja": "保温"},
    "基础保暖": {"zh-CN": "基础保暖", "en": "Essential warmth", "ja": "ベーシックな保温性"},
    "连帽": {"zh-CN": "连帽", "en": "Hooded", "ja": "フード付き"},
    "轻薄": {"zh-CN": "轻薄", "en": "Lightweight", "ja": "軽量"},
    "加厚": {"zh-CN": "加厚", "en": "Extra insulation", "ja": "厚手"},
    "立领": {"zh-CN": "立领", "en": "Stand collar", "ja": "スタンドカラー"},
    "防风": {"zh-CN": "防风", "en": "Windproof", "ja": "防風"},
    "羽绒内胆": {"zh-CN": "羽绒内胆", "en": "Down liner", "ja": "ダウンライナー"},
    "防泼水": {"zh-CN": "防泼水", "en": "Water-repellent", "ja": "撥水"},
    "高蓬松": {"zh-CN": "高蓬松", "en": "High loft", "ja": "高いロフト感"},
    "三防": {"zh-CN": "三防", "en": "Three-way protection", "ja": "三防機能"},
    "防水": {"zh-CN": "防水", "en": "Waterproof", "ja": "防水"},
    "三合一": {"zh-CN": "三合一", "en": "3-in-1", "ja": "3-in-1"},
    "翻领": {"zh-CN": "翻领", "en": "Notched collar", "ja": "ラペルカラー"},
    "石墨烯": {"zh-CN": "石墨烯", "en": "Graphene", "ja": "グラフェン"},
    "两件套": {"zh-CN": "两件套", "en": "Two-piece set", "ja": "2点セット"},
    "可双面穿": {"zh-CN": "可双面穿", "en": "Reversible", "ja": "リバーシブル"},
    "抗静电": {"zh-CN": "抗静电", "en": "Anti-static", "ja": "静電気防止"},
    "可脱卸帽": {"zh-CN": "可脱卸帽", "en": "Detachable hood", "ja": "取り外し可能フード"},
    "抗菌": {"zh-CN": "抗菌", "en": "Antibacterial", "ja": "抗菌"},
    "无缝压胶": {"zh-CN": "无缝压胶", "en": "Seam-sealed", "ja": "シームシール"},
    "圆领": {"zh-CN": "圆领", "en": "Crew neck", "ja": "クルーネック"},
    "防钻绒": {"zh-CN": "防钻绒", "en": "Down-proof", "ja": "ダウンプルーフ"},
    "自发热": {"zh-CN": "自发热", "en": "Self-heating", "ja": "発熱素材"},
}

COLOR_LABELS = {
    "黑色系": {"zh-CN": "黑色系", "en": "Black", "ja": "ブラック系"},
    "黑色": {"zh-CN": "黑色", "en": "Black", "ja": "ブラック"},
    "浅灰色系": {"zh-CN": "浅灰色系", "en": "Light gray", "ja": "ライトグレー系"},
    "深灰色系": {"zh-CN": "深灰色系", "en": "Dark gray", "ja": "ダークグレー系"},
    "中灰色系": {"zh-CN": "中灰色系", "en": "Gray", "ja": "ミディアムグレー系"},
    "灰褐色系": {"zh-CN": "灰褐色系", "en": "Gray-brown", "ja": "グレーブラウン系"},
    "灰蓝色系": {"zh-CN": "灰蓝色系", "en": "Gray-blue", "ja": "グレーブルー系"},
    "白色": {"zh-CN": "白色", "en": "White", "ja": "ホワイト"},
    "米白色系": {"zh-CN": "米白色系", "en": "Off-white", "ja": "オフホワイト系"},
    "卡其棕色系": {"zh-CN": "卡其棕色系", "en": "Khaki brown", "ja": "カーキブラウン系"},
    "深蓝色系": {"zh-CN": "深蓝色系", "en": "Dark blue", "ja": "ダークブルー系"},
    "蓝色": {"zh-CN": "蓝色", "en": "Blue", "ja": "ブルー"},
    "红色系": {"zh-CN": "红色系", "en": "Red", "ja": "レッド系"},
    "绿色": {"zh-CN": "绿色", "en": "Green", "ja": "グリーン"},
    "藏青色": {"zh-CN": "藏青色", "en": "Navy", "ja": "ネイビー"},
}

COLOR_GROUP_LABELS = {
    "black": {"zh-CN": "黑色系", "en": "Black", "ja": "ブラック系"},
    "white": {"zh-CN": "白色系", "en": "White", "ja": "ホワイト系"},
    "gray": {"zh-CN": "灰色系", "en": "Gray", "ja": "グレー系"},
    "blue": {"zh-CN": "蓝色系", "en": "Blue", "ja": "ブルー系"},
    "green": {"zh-CN": "绿色系", "en": "Green", "ja": "グリーン系"},
    "red": {"zh-CN": "红色系", "en": "Red", "ja": "レッド系"},
    "orange": {"zh-CN": "橙色系", "en": "Orange", "ja": "オレンジ系"},
    "brown": {"zh-CN": "棕色系", "en": "Brown", "ja": "ブラウン系"},
}

GENDER_LABELS = {
    "male": {"zh-CN": "男款", "en": "Men's", "ja": "メンズ"},
    "female": {"zh-CN": "女款", "en": "Women's", "ja": "レディース"},
    "unisex": {"zh-CN": "中性/同款", "en": "Unisex", "ja": "ユニセックス"},
    "unknown": {"zh-CN": "未标注", "en": "Unspecified", "ja": "性別未指定"},
}

PLATFORM_LABELS = {
    "jd": {"zh-CN": "京东", "en": "JD", "ja": "JD"},
    "taobao": {"zh-CN": "淘宝", "en": "Taobao", "ja": "Taobao"},
    "": {"zh-CN": "未知平台", "en": "Unknown platform", "ja": "不明なプラットフォーム"},
}

SCORE_DIMENSION_LABELS = {
    "color": {"zh-CN": "颜色适配度", "en": "Color fit", "ja": "カラー適合度"},
    "size": {"zh-CN": "身材适配度", "en": "Body fit", "ja": "体型フィット"},
    "style": {"zh-CN": "款式适配度", "en": "Style fit", "ja": "スタイル適合度"},
    "brand": {"zh-CN": "品牌偏好度", "en": "Brand preference", "ja": "ブランド適合度"},
    "gender": {"zh-CN": "性别适配度", "en": "Gender fit", "ja": "性別適合度"},
    "price": {"zh-CN": "价格适配度", "en": "Price fit", "ja": "価格適合度"},
    "personality": {"zh-CN": "性格适配度", "en": "Personality fit", "ja": "性格適合度"},
}

BODY_SHAPE_LABELS = {
    "偏瘦": {"zh-CN": "偏瘦", "en": "Slim", "ja": "細身"},
    "标准": {"zh-CN": "标准", "en": "Standard", "ja": "標準"},
    "微胖": {"zh-CN": "微胖", "en": "Fuller build", "ja": "ややふっくら"},
    "高壮": {"zh-CN": "高壮", "en": "Tall and broad", "ja": "高身長でがっしり"},
    "梨形": {"zh-CN": "梨形", "en": "Pear shape", "ja": "洋なし型"},
    "O型": {"zh-CN": "O型", "en": "Round shape", "ja": "O型"},
    "H型": {"zh-CN": "H型", "en": "Straight shape", "ja": "H型"},
    "沙漏型": {"zh-CN": "沙漏型", "en": "Hourglass shape", "ja": "砂時計型"},
    "倒三角": {"zh-CN": "倒三角", "en": "Inverted triangle", "ja": "逆三角形"},
}

LEGACY_SCORE_DIMENSION_CODES = {
    "颜色适配度": "color",
    "身材适配度": "size",
    "款式适配度": "style",
    "品牌偏好度": "brand",
    "性别适配度": "gender",
    "价格适配度": "price",
    "性格适配度": "personality",
}


def localized_label(mapping: dict[str, dict[str, str]], source: str, locale: str, fallback: str) -> str:
    return mapping.get(source, {}).get(locale) or mapping.get(source, {}).get("en" if locale == "ja" else "zh-CN") or fallback


def localized_style(value: str, locale: str) -> str:
    return localized_label(STYLE_LABELS, value, locale, "Down jacket" if locale == "en" else "ダウンジャケット" if locale == "ja" else value)


def localized_body_fit(value: str, locale: str) -> str:
    return localized_label(BODY_FIT_LABELS, value, locale, "Standard fit" if locale == "en" else "標準フィット" if locale == "ja" else value)


def localized_feature(value: str, locale: str) -> str:
    return localized_label(FEATURE_LABELS, value, locale, "Other feature" if locale == "en" else "その他の機能" if locale == "ja" else value)


def localized_color(value: str, locale: str) -> str:
    if locale == "zh-CN":
        return value
    if value in COLOR_LABELS:
        return COLOR_LABELS[value][locale]
    group = classify_color_group(value)
    if group and group in COLOR_GROUP_LABELS:
        return COLOR_GROUP_LABELS[group][locale]
    return "Color family" if locale == "en" else "カラーファミリー"


def localized_gender(value: str, locale: str) -> str:
    return GENDER_LABELS.get(value, GENDER_LABELS["unknown"]).get(locale, GENDER_LABELS["unknown"][locale])


def localized_platform(value: str, locale: str) -> str:
    return PLATFORM_LABELS.get(value, PLATFORM_LABELS[""]).get(locale, PLATFORM_LABELS[""][locale])


def display_brand(product: Product, locale: str = "zh-CN") -> str | None:
    brand = get_product_brand(product)
    if not brand:
        return None
    if locale == "zh-CN":
        return brand
    if not re.search(r"[\u3400-\u9fff]", brand) and re.search(r"[A-Za-z]", brand):
        return brand
    aliases = BRAND_ALIASES.get(brand, [])
    latin_alias = next((alias for alias in aliases if re.search(r"[A-Za-z]", alias)), None)
    if latin_alias:
        return latin_alias
    return None


def score_dimension_code(value: str) -> str:
    if value in SCORE_DIMENSION_LABELS:
        return value
    for code, labels in SCORE_DIMENSION_LABELS.items():
        if value in labels.values():
            return code
    return LEGACY_SCORE_DIMENSION_CODES.get(value, "style")


def localized_score_label(code: str, locale: str) -> str:
    labels = SCORE_DIMENSION_LABELS.get(code, SCORE_DIMENSION_LABELS["style"])
    return labels.get(locale, labels["en"])


def localized_body_shape(value: str | None, locale: str) -> str:
    if not value:
        return "" if locale == "zh-CN" else "Unspecified" if locale == "en" else "未指定"
    labels = BODY_SHAPE_LABELS.get(value)
    if labels:
        return labels.get(locale, labels["en"])
    return value if locale == "zh-CN" else "Unspecified" if locale == "en" else "未指定"


def localized_brand(value: str | None, locale: str) -> str:
    if not value:
        return ""
    if locale == "zh-CN":
        return value
    if not re.search(r"[\u3400-\u9fff]", value):
        return value
    aliases = BRAND_ALIASES.get(value, [])
    latin_alias = next((alias for alias in aliases if re.search(r"[A-Za-z]", alias)), None)
    if latin_alias:
        return latin_alias
    return "a selected brand" if locale == "en" else "指定ブランド"


def product_display_fields(product: Product, locale: str, product_key: str) -> dict[str, object]:
    style_features = [localized_feature(item, locale) for item in get_visible_style_features(product)]
    function_features = [localized_feature(item, locale) for item in ensure_list(product.function_features)]
    if locale == "zh-CN":
        size_notes = product.size_notes or "请参考尺码表"
    else:
        safe_tags = [str(tag) for tag in product.size_tags if not re.search(r"[\u3400-\u9fff]", str(tag))]
        tags = ", ".join(safe_tags)
        if not tags:
            size_notes = "See the size chart." if locale == "en" else "サイズ表をご確認ください。"
        else:
            size_notes = (
                f"Size guidance: {tags}. See the size chart."
                if locale == "en"
                else f"サイズ目安：{tags}。サイズ表をご確認ください。"
            )
    style_type = localized_style(product.style_type, locale)
    color_family = localized_color(product.color_family, locale)
    body_fit = localized_body_fit(product.body_fit, locale)

    if locale == "zh-CN":
        title = product.title
    else:
        brand = display_brand(product, locale)
        gender = localized_gender(infer_product_gender(product.title), locale)
        if locale == "en":
            title_prefix = " ".join(item for item in [brand, gender, style_type] if item)
            first_feature = function_features[0] if function_features else (style_features[0] if style_features else "Warmth")
            title = f"{title_prefix} Down Jacket — {color_family} · {first_feature} · #{product_key[:6]}"
        else:
            title_prefix = " ".join(item for item in [brand, gender] if item)
            first_feature = function_features[0] if function_features else (style_features[0] if style_features else "保温性")
            title = f"{title_prefix}用 {style_type}ダウンジャケット — {color_family}・{first_feature}・#{product_key[:6]}"

    return {
        "title": title,
        "styleType": style_type,
        "colorFamily": color_family,
        "bodyFit": body_fit,
        "styleFeatures": style_features,
        "functionFeatures": function_features,
        "sizeNotes": size_notes,
    }
