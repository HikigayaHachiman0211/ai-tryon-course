"""Re-process brand annotations in database.json.

Fixes:
1. JD entries: extract brand from title (was missing entirely)
2. Taobao entries: re-run brand inference with updated blacklist and aliases

Run from project root:
    python -m backend.scripts.fix_brands
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.catalog_seed import ensure_brand_tag, infer_brand_name, normalize_brand_name  # noqa: E402


def main() -> None:
    db_path = PROJECT_ROOT / "database.json"
    with db_path.open("r", encoding="utf-8") as f:
        data: list[dict] = json.load(f)

    jd_fixed = 0
    tb_fixed = 0
    tb_cleared = 0
    brand_field_fixed = 0

    for row in data:
        title = row.get("商品标题", "")
        image_path = row.get("图片路径", "")
        old_features = row.get("风格特征", [])

        # Extract old brand from 风格特征
        old_brand = None
        for feat in old_features:
            s = str(feat)
            if s.startswith("品牌:"):
                old_brand = s[3:]
            elif s.startswith("品牌："):
                old_brand = s[3:]

        # Re-infer brand from title only (no store_name available in JSON)
        new_brand = infer_brand_name(title)

        # Also validate and fix the top-level 品牌 field
        old_brand_field = str(row.get("品牌") or "").strip()
        if old_brand_field:
            validated = normalize_brand_name(old_brand_field)
            if validated != old_brand_field:
                brand_field_fixed += 1
            row["品牌"] = validated or ""
            # If 品牌 field had a valid brand but title inference missed it, use it
            if validated and not new_brand:
                new_brand = validated

        if new_brand != old_brand:
            row["风格特征"] = ensure_brand_tag(old_features, new_brand)
            if "downloaded_jd" in image_path:
                if new_brand and not old_brand:
                    jd_fixed += 1
            else:
                if old_brand and not new_brand:
                    tb_cleared += 1
                else:
                    tb_fixed += 1

    with db_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"JD brands added: {jd_fixed}")
    print(f"TB brands corrected: {tb_fixed}")
    print(f"TB fake brands cleared: {tb_cleared}")
    print(f"品牌 field fixed: {brand_field_fixed}")
    print(f"Total entries: {len(data)}")


if __name__ == "__main__":
    main()
