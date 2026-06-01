"""Generate a combined database.json containing both JD and Taobao product data.

Run from the project root (Project4.15-AI-Try-on-with-frontend):
    python -m backend.scripts.generate_combined_database
Or directly:
    cd backend && python scripts/generate_combined_database.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.catalog_seed import (  # noqa: E402
    find_taobao_workbook,
    load_taobao_seed_rows,
)
from app.database import extract_size_notes, extract_size_tags  # noqa: E402


def main() -> None:
    output_path = PROJECT_ROOT / "database.json"

    # Load existing JD data
    jd_data: list[dict] = []
    if output_path.exists():
        with output_path.open("r", encoding="utf-8") as f:
            jd_data = json.load(f)
    print(f"JD rows loaded: {len(jd_data)}")

    # Check if JD data already contains Taobao entries
    existing_taobao = [r for r in jd_data if str(r.get("图片路径", "")).startswith("img羽绒服")]
    if existing_taobao:
        print(f"database.json already contains {len(existing_taobao)} Taobao entries. Skipping merge.")
        print(f"Total: {len(jd_data)}")
        return

    # Load Taobao data
    taobao_workbook = find_taobao_workbook()
    if taobao_workbook is None:
        print("ERROR: No Taobao workbook (img羽绒服*/*.xlsx) found.")
        print("Make sure the img羽绒服* directory is in the workspace root.")
        sys.exit(1)

    print(f"Loading Taobao data from: {taobao_workbook}")
    taobao_data = load_taobao_seed_rows(taobao_workbook)
    print(f"Taobao rows loaded: {len(taobao_data)}")

    # Merge
    combined = jd_data + taobao_data
    print(f"Combined total: {len(combined)}")

    # Write
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
    print(f"Written to: {output_path}")


if __name__ == "__main__":
    main()
