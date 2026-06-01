"""Annotation engine — confidence computation and batch annotation logic."""
from __future__ import annotations

import json
import re
from typing import Any

from app.database import Product


# Commonly confused brand patterns
_MULTI_BRAND_PATTERN = re.compile(r"[xX×]\s|联名|合作款")
_DEFAULT_STYLE = "常规短外套"
_CONFLICTING_STYLE_KEYWORDS = [
    ("面包", "排骨"),
    ("面包", "绗缝"),
    ("轻薄", "加厚"),
]
_DEFAULT_STYLE_FEATURES = {"休闲"}
_DEFAULT_FUNCTION_FEATURES = {"基础保暖", "保暖"}


def compute_annotation_confidence(product: Product) -> float:
    """Pure function: compute annotation confidence for a product. Returns 0.0-1.0."""
    title = product.title or ""
    style_type = product.style_type or ""
    color_family = product.color_family or ""
    style_features = product.style_features or []
    function_features = product.function_features or []

    confidence = 0.85  # default: high confidence if all signals clear

    # Rule 1: Style type is default fallback
    if style_type == _DEFAULT_STYLE:
        confidence = min(confidence, 0.40)

    # Rule 2: Conflicting style keywords in title
    title_lower = title.lower()
    for kw_a, kw_b in _CONFLICTING_STYLE_KEYWORDS:
        if kw_a in title_lower and kw_b in title_lower:
            confidence = min(confidence, 0.30)
            break

    # Rule 3: Multi-brand confusion
    if _MULTI_BRAND_PATTERN.search(title):
        confidence = min(confidence, 0.55)

    # Rule 4: Brand tag extracted via fuzzy match (check style_features for brand tags)
    brand_tags = [f for f in style_features if isinstance(f, str) and f.startswith("品牌:")]
    if not brand_tags:
        confidence = min(confidence, 0.50)

    # Rule 5: Style/function features are near-default
    feature_set = {f for f in style_features if isinstance(f, str) and not f.startswith("品牌:")}
    if feature_set <= _DEFAULT_STYLE_FEATURES:
        confidence = min(confidence, 0.45)

    func_set = set(function_features) if function_features else set()
    if func_set <= _DEFAULT_FUNCTION_FEATURES:
        confidence = min(confidence, 0.45)

    # Rule 6: Color might be from visual analysis (no color keyword in title)
    color_in_title = color_family and color_family.replace("色系", "").replace("色", "") in title
    if color_family and not color_in_title:
        confidence = min(confidence, 0.50)

    return round(confidence, 2)


def derive_priority(confidence: float) -> int:
    """Derive annotation priority from confidence. 0=normal, 1=medium, 2=high."""
    if confidence < 0.4:
        return 2
    if confidence < 0.7:
        return 1
    return 0
