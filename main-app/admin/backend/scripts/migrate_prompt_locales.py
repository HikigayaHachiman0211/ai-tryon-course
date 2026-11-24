#!/usr/bin/env python3
"""Explicit prompt-locale migration and audit helper.

Run this against a copied database first. The script is intentionally dry-run
by default; production execution requires an operator-supplied backup marker
and ``--apply`` so a deployment cannot silently change prompt data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect, text

from app.i18n.prompt_migration import has_legacy_name_unique, rebuild_sqlite_prompt_configs


def checksum(connection, *, has_locale: bool = True) -> str:
    locale_column = "locale" if has_locale else "'' AS locale"
    rows = connection.execute(text(
        f"SELECT name, {locale_column}, content, version FROM prompt_configs "
        "ORDER BY name, id"
    )).mappings().all()
    payload = json.dumps([dict(row) for row in rows], ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit/migrate prompt_configs locale rows")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--apply", action="store_true", help="apply the idempotent column/index migration")
    parser.add_argument("--backup-marker", help="path to an operator-created backup marker; required with --apply")
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL or --database-url is required")
    if args.apply and not args.backup_marker:
        raise SystemExit("--apply requires --backup-marker after a verified database backup")

    engine = create_engine(args.database_url)
    with engine.begin() as connection:
        inspector = inspect(connection)
        if not inspector.has_table("prompt_configs"):
            raise SystemExit("prompt_configs does not exist; run the normal schema bootstrap first")
        columns = {column["name"] for column in inspector.get_columns("prompt_configs")}
        before = checksum(connection, has_locale="locale" in columns)
        legacy_name_unique = has_legacy_name_unique(connection)
        print(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rows": connection.execute(text("SELECT COUNT(*) FROM prompt_configs")).scalar_one(),
            "locales": connection.execute(text("SELECT locale, COUNT(*) FROM prompt_configs GROUP BY locale")).all()
            if "locale" in columns else [],
            "checksum_before": before,
            "legacy_name_unique": legacy_name_unique,
            "apply": args.apply,
        }, ensure_ascii=False, default=str))
        if not args.apply:
            print("DRY RUN: add locale DEFAULT 'zh-CN' and unique (name, locale); create English/Japanese rows via init_db")
            return
        if "locale" not in columns:
            connection.execute(text("ALTER TABLE prompt_configs ADD COLUMN locale VARCHAR(10) NOT NULL DEFAULT 'zh-CN'"))
        if legacy_name_unique and connection.dialect.name.startswith("sqlite"):
            rebuild_sqlite_prompt_configs(connection)
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_prompt_configs_name_locale "
            "ON prompt_configs (name, locale)"
        ))
        after = checksum(connection, has_locale=True)
        print(json.dumps({"checksum_after": after, "rollback_sql": "DROP INDEX uq_prompt_configs_name_locale; -- restore the verified backup"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
