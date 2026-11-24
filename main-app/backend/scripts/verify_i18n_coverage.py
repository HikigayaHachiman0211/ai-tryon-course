from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import load_seed_rows, resolve_database_json_path  # noqa: E402
from app.i18n.catalog import product_key_for_row  # noqa: E402

HAN_RE = re.compile(r"[\u3400-\u9fff]")
REQUIRED_FIELDS = ("title", "styleType", "colorFamily", "bodyFit", "styleFeatures", "functionFeatures", "sizeNotes")


def source_hash(row: dict) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify complete three-locale catalog coverage")
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--translations-dir", type=Path, default=BACKEND_ROOT / "app" / "i18n" / "catalog-translations")
    parser.add_argument("--read-model", type=Path, default=BACKEND_ROOT / "read-model" / "catalog.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = resolve_database_json_path(args.source)
    rows = load_seed_rows(source_path)
    expected: dict[str, str] = {}
    seen_keys: dict[str, int] = {}
    for row in rows:
        base_key = product_key_for_row(row)
        collision_index = seen_keys.get(base_key, 0)
        seen_keys[base_key] = collision_index + 1
        expected[product_key_for_row(row, collision_index)] = source_hash(row)
    if len(expected) != len(rows):
        raise SystemExit(f"duplicate product_key values: {len(rows)} source rows -> {len(expected)} keys")

    failures: list[str] = []
    for locale in ("en", "ja"):
        path = args.translations_dir / f"{locale}.json"
        if not path.exists():
            failures.append(f"missing asset: {path}")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("items", {})
        if not isinstance(items, dict):
            failures.append(f"{locale}: items is not an object")
            continue
        if set(items) != set(expected):
            failures.append(f"{locale}: key set mismatch (expected {len(expected)}, got {len(items)})")
        for key, source_digest in expected.items():
            item = items.get(key)
            if not isinstance(item, dict):
                failures.append(f"{locale}:{key}: missing item")
                continue
            for field in REQUIRED_FIELDS:
                value = item.get(field)
                if not value or (isinstance(value, list) and not all(str(v).strip() for v in value)):
                    failures.append(f"{locale}:{key}: missing {field}")
            if item.get("source_hash") != source_digest:
                failures.append(f"{locale}:{key}: stale source_hash")
            if item.get("status") != "validated":
                failures.append(f"{locale}:{key}: status is not validated")
            if locale == "en" and any(HAN_RE.search(str(item.get(field, ""))) for field in REQUIRED_FIELDS if field != "styleFeatures"):
                failures.append(f"{locale}:{key}: unapproved Han character in display")
            if item.get("translation_source") == "needs_review":
                failures.append(f"{locale}:{key}: needs_review")

    if args.read_model.exists():
        read_model = json.loads(args.read_model.read_text(encoding="utf-8"))
        if read_model.get("product_count") != len(rows):
            failures.append("read-model product_count mismatch")
        model_keys = {str(item.get("product_key")) for item in read_model.get("items", [])}
        if model_keys != set(expected):
            failures.append("read-model product_key set mismatch")

    if failures:
        for failure in failures[:100]:
            print(f"[coverage] FAIL {failure}")
        raise SystemExit(1)
    print(f"[coverage] PASS: {len(rows)} products x 3 locales; missing=0 stale=0 needs_review=0")


if __name__ == "__main__":
    main()
