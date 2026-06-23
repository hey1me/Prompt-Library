"""Schema versioning and migration runner for the Prompt Library.

Migrations are applied sequentially. The current schema version is stored in
the ``schema_version`` table. Each migration is a callable that receives a
``sqlite3.Connection`` and applies incremental schema changes.

To add a new migration:
1. Write a function ``def migrate_v2(conn): ...``
2. Add it to ``MIGRATIONS`` dict: ``MIGRATIONS[2] = migrate_v2``
"""

import sqlite3

# Schema version -> migration function
# Each function receives a sqlite3.Connection and applies changes atomically.
MIGRATIONS: dict[int, callable] = {}


def _migration_v1(conn: sqlite3.Connection) -> None:
    """Initial schema — prompts table, FTS5, triggers, indexes.

    This migration is handled by ``init_db()`` in ``database.py``. The entry
    here exists so the version bookkeeping stays consistent.
    """
    # Schema creation is already handled by database.init_db()
    pass


MIGRATIONS[1] = _migration_v1


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Read the current schema version from the database.

    Returns 0 if the schema_version table does not exist or is empty.
    """
    try:
        row = conn.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()
        return row[0] if row and row[0] else 0
    except sqlite3.OperationalError:
        return 0


def set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Write the schema version to the database."""
    conn.execute(
        "INSERT INTO schema_version (version) VALUES (?)",
        (version,),
    )
    conn.commit()


def run_migrations(conn: sqlite3.Connection) -> int:
    """Apply all pending migrations in order.

    Args:
        conn: An open SQLite connection with a valid schema_version table.

    Returns:
        The number of migrations applied.
    """
    current = get_schema_version(conn)
    applied = 0

    for version in sorted(MIGRATIONS.keys()):
        if version > current:
            MIGRATIONS[version](conn)
            set_schema_version(conn, version)
            applied += 1

    return applied
