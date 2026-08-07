from __future__ import annotations

import os
import re
import re as _re_module
import urllib.parse as _urllib_parse
from pathlib import Path
from urllib.parse import quote

from app.catalog_seed import BRAND_ALIASES, extract_brand_tag, get_platform_label, infer_brand_name, infer_platform_key
from app.database import Product
from app.recommendation_rules import ensure_list


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
