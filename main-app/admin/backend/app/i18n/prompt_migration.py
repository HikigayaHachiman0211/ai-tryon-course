"""Schema helpers for the prompt locale migration.

The first-generation SQLite schema used ``UNIQUE(name)``.  Adding a locale
column and a second unique index is not enough because SQLite keeps the old
auto-index and translated rows still collide.  This module rebuilds only the
prompt table when that legacy constraint is present, preserving row ids and
all prompt-version foreign keys.
"""

from __future__ import annotations

from sqlalchemy.engine import Connection


def _quoted_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def has_legacy_name_unique(connection: Connection) -> bool:
    """Return whether SQLite still has the old unique index on ``name``."""

    if not connection.dialect.name.startswith("sqlite"):
        return False
    for row in connection.exec_driver_sql("PRAGMA index_list(prompt_configs)").fetchall():
        # SQLite returns (seq, name, unique, origin, partial).
        if len(row) < 3 or not bool(row[2]):
            continue
        index_name = str(row[1])
        columns = connection.exec_driver_sql(
            f"PRAGMA index_info({_quoted_identifier(index_name)})"
        ).fetchall()
        if [str(column[2]) for column in columns] == ["name"]:
            return True
    return False


def rebuild_sqlite_prompt_configs(connection: Connection) -> bool:
    """Remove the legacy name-only constraint while preserving prompt data.

    The caller must already have added any missing columns.  The operation is
    idempotent and returns ``True`` only when a rebuild was performed.
    """

    if not has_legacy_name_unique(connection):
        return False

    # SQLite cannot toggle foreign_keys inside an open transaction.  Commit
    # the column additions first, then rebuild the table with FK checks off.
    connection.commit()
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        connection.exec_driver_sql(
            """
            CREATE TABLE prompt_configs__locale_migration (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL,
                locale VARCHAR(10) NOT NULL DEFAULT 'zh-CN',
                display_name VARCHAR(200) NOT NULL,
                description VARCHAR(500),
                category VARCHAR(50),
                prompt_type VARCHAR(50),
                content TEXT NOT NULL,
                default_content TEXT,
                variables JSON,
                model_name VARCHAR(100) NOT NULL,
                temperature FLOAT DEFAULT 0.2,
                is_active BOOLEAN DEFAULT 1,
                version INTEGER DEFAULT 1,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_by VARCHAR(100)
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO prompt_configs__locale_migration
                (id, name, locale, display_name, description, category,
                 prompt_type, content, default_content, variables, model_name,
                 temperature, is_active, version, updated_at, updated_by)
            SELECT id, name, locale, display_name, description, category,
                   prompt_type, content, default_content, variables, model_name,
                   temperature, is_active, version, updated_at, updated_by
            FROM prompt_configs
            """
        )
        connection.exec_driver_sql("DROP TABLE prompt_configs")
        connection.exec_driver_sql(
            "ALTER TABLE prompt_configs__locale_migration RENAME TO prompt_configs"
        )
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX uq_prompt_configs_name_locale "
            "ON prompt_configs (name, locale)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_prompt_configs_name "
            "ON prompt_configs (name)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_prompt_configs_locale "
            "ON prompt_configs (locale)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_prompt_configs_category "
            "ON prompt_configs (category)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_prompt_configs_prompt_type "
            "ON prompt_configs (prompt_type)"
        )
        connection.commit()
        return True
    finally:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
