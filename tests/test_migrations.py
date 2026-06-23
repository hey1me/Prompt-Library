"""Tests for schema migrations."""

import sqlite3

import pytest

from pl.database import get_connection, close_connection, init_db
from pl.migrations import get_schema_version, set_schema_version, run_migrations, MIGRATIONS


def test_get_schema_version_after_init():
    """After init_db, schema version should be 1."""
    conn = get_connection(":memory:")
    init_db(conn)
    assert get_schema_version(conn) == 1
    close_connection()


def test_set_schema_version():
    """Setting schema version should persist."""
    conn = get_connection(":memory:")
    init_db(conn)
    set_schema_version(conn, 5)
    assert get_schema_version(conn) == 5
    close_connection()


def test_run_migrations_on_fresh_db():
    """Running migrations on a fresh DB should apply all."""
    conn = get_connection(":memory:")
    init_db(conn)
    applied = run_migrations(conn)
    # No new migrations to apply since init_db already ran version 1
    assert applied == 0
    assert get_schema_version(conn) == 1
    close_connection()


def test_migration_idempotency():
    """Running migrations twice should be a no-op."""
    conn = get_connection(":memory:")
    init_db(conn)
    run_migrations(conn)
    applied = run_migrations(conn)
    assert applied == 0
    close_connection()


def test_migration_list_not_empty():
    """MIGRATIONS should contain at least version 1."""
    assert len(MIGRATIONS) >= 1
    assert 1 in MIGRATIONS
    assert callable(MIGRATIONS[1])


def test_migration_functions_are_callable():
    """All migration values should be callable with (conn) signature."""
    for version, func in MIGRATIONS.items():
        assert callable(func)
        # Quick smoke test on a blank connection
        conn = get_connection(":memory:")
        conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO schema_version (version) VALUES (0)")
        func(conn)
        conn.commit()
        close_connection()
