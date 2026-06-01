from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import build_product, load_seed_rows, resolve_database_json_path  # noqa: E402

DEFAULT_OUTPUT_PATH = BACKEND_ROOT / "read-model" / "catalog.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build main-site catalog read-model artifact")
    parser.add_argument("--source", type=Path, default=None, help="Optional catalog source path (defaults to database.json)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Output read-model JSON path")
    return parser.parse_args()


def serialize_catalog_item(product_id: int, row: dict) -> dict:
    product = build_product(row)
    product.id = product_id
    return {
        "id": product.id,
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
    }


def main() -> None:
    args = parse_args()
    source_path = resolve_database_json_path(args.source)
    rows = load_seed_rows(source_path)
    items = [serialize_catalog_item(product_id, row) for product_id, row in enumerate(rows, start=1)]

    payload = {
        "kind": "catalog-read-model",
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_path": source_path.as_posix(),
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