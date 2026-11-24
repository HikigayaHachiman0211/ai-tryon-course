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

from app.catalog_repository import _build_catalog_products_from_read_model  # noqa: E402
from app.database import build_product, load_seed_rows, resolve_database_json_path  # noqa: E402
from app.i18n.catalog import product_key_for_row  # noqa: E402
from app.i18n.domain_labels import product_display_fields  # noqa: E402

TRANSLATION_DIR = BACKEND_ROOT / "app" / "i18n" / "catalog-translations"


def source_hash(row: dict) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build complete deterministic catalog translation assets")
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=TRANSLATION_DIR)
    return parser.parse_args()


def build_items(rows: list[dict], locale: str) -> dict[str, dict]:
    items: dict[str, dict] = {}
    seen_keys: dict[str, int] = {}
    for product_id, row in enumerate(rows, start=1):
        product = build_product(row)
        product.id = product_id
        base_key = product_key_for_row(row)
        collision_index = seen_keys.get(base_key, 0)
        seen_keys[base_key] = collision_index + 1
        key = product_key_for_row(row, collision_index)
        display = product_display_fields(product, locale, key)
        items[key] = {
            **display,
            "source_hash": source_hash(row),
            "locale": locale,
            "translation_source": "deterministic-descriptor",
            "model": "catalog-domain-dictionary-v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "validated",
        }
    if len(items) != len(rows):
        raise RuntimeError(f"duplicate product_key values: {len(rows)} source rows -> {len(items)} assets")
    return items


def main() -> None:
    args = parse_args()
    source_path = resolve_database_json_path(args.source)
    rows = load_seed_rows(source_path)
    source_name = source_path.relative_to(PROJECT_ROOT).as_posix() if source_path.is_relative_to(PROJECT_ROOT) else source_path.name
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for locale in ("en", "ja"):
        payload = {
            "kind": "catalog-translations",
            "version": 1,
            "locale": locale,
            "generator": "build_catalog_translations.py:v1",
            "source_path": source_name,
            "source_record_count": len(rows),
            "items": build_items(rows, locale),
        }
        target = args.output_dir / f"{locale}.json"
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
        print(f"{locale}: {len(rows)} assets -> {target}")


if __name__ == "__main__":
    main()
