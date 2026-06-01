from __future__ import annotations

import argparse
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import DATABASE_URL, ensure_database  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Create tables and import database.json into SQLAlchemy database")
    parser.add_argument("--replace", action="store_true", help="Replace all existing product rows")
    parser.add_argument("--database-json", type=str, default=None, help="Override database.json path")
    args = parser.parse_args()

    json_path = Path(args.database_json).resolve() if args.database_json else None
    inserted = ensure_database(seed_if_empty=True, replace=args.replace, database_json_path=json_path)
    print(f"Database URL: {DATABASE_URL}")
    print(f"Imported rows: {inserted}")


if __name__ == "__main__":
    main()
