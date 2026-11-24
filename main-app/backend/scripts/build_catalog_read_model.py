from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import build_product, load_seed_rows, resolve_database_json_path  # noqa: E402
from app.i18n.catalog import product_key_for_row  # noqa: E402
from app.i18n.domain_labels import product_display_fields  # noqa: E402
from app.product_attributes import get_product_brand, get_product_platform_key  # noqa: E402
from app.recommendation_rules import infer_product_gender  # noqa: E402

DEFAULT_OUTPUT_PATH = BACKEND_ROOT / "read-model" / "catalog.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build main-site catalog read-model artifact")
    parser.add_argument("--source", type=Path, default=None, help="Optional catalog source path (defaults to database.json)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Output read-model JSON path")
    return parser.parse_args()


def serialize_catalog_item(product_id: int, row: dict, collision_index: int = 0) -> dict:
    product = build_product(row)
    product.id = product_id
    key = product_key_for_row(row, collision_index)
    displays = {locale: product_display_fields(product, locale, key) for locale in ("zh-CN", "en", "ja")}
    search_text = {
        locale: " ".join(
            [
                str(display["title"]),
                str(display["styleType"]),
                str(display["colorFamily"]),
                str(display["bodyFit"]),
                *[str(value) for value in display["styleFeatures"]],
                *[str(value) for value in display["functionFeatures"]],
            ]
        )
        for locale, display in displays.items()
    }
    return {
        "id": product.id,
        "product_key": key,
        "title": product.title,
        "price": product.price,
        "image_path": product.image_path,
        "style_type": product.style_type,
        "color_family": product.color_family,
        "body_fit": product.body_fit,
        "style_features": list(product.style_features),
        "function_features": list(product.function_features),
        "size_tags": list(product.size_tags),
        "size_notes": product.size_notes,
        "product_url": product.product_url,
        "canonical": {
            "product_key": key,
            "price": product.price,
            "image_path": product.image_path,
            "platform": get_product_platform_key(product),
            "gender": infer_product_gender(product.title),
            "brand": get_product_brand(product),
        },
        "display": displays,
        "search_text": search_text,
    }


def main() -> None:
    args = parse_args()
    source_path = resolve_database_json_path(args.source)
    rows = load_seed_rows(source_path)
    source_name = source_path.relative_to(PROJECT_ROOT).as_posix() if source_path.is_relative_to(PROJECT_ROOT) else source_path.name
    seen_keys: dict[str, int] = {}
    items = []
    for product_id, row in enumerate(rows, start=1):
        base_key = product_key_for_row(row)
        collision_index = seen_keys.get(base_key, 0)
        seen_keys[base_key] = collision_index + 1
        items.append(serialize_catalog_item(product_id, row, collision_index))

    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    payload = {
        "kind": "catalog-read-model",
        "version": 2,
        "generator": "build_catalog_read_model.py:v2",
        "product_key_algorithm": "sha256(normalize(title)\\x1fnormalize(price)\\x1fnormalize(image_path))[:24]; duplicate source triples use sha256(base\\x1foccurrence)[:24]",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_path": source_name,
        "source_sha256": source_sha256,
        "locales": ["zh-CN", "en", "ja"],
        "product_count": len(items),
        "items": items,
    }

    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Read-model source: {source_path}")
    print(f"Read-model products: {len(items)}")
    print(f"Read-model written to: {output_path}")


if __name__ == "__main__":
    main()
