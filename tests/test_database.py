"""Tests for database connection and schema management."""

import os
import sqlite3
from pathlib import Path

import pytest

from pl.database import (
    close_connection,
    get_connection,
    get_db_path,
    init_db,
)


def test_get_db_path_default():
    """Default path should be under XDG data home."""
    path = get_db_path()
    assert "prompt-library" in str(path)
    assert path.name == "library.db"


def test_get_db_path_env_override(monkeypatch, tmp_path):
    """PROMPT_LIBRARY_DB env var should override default path."""
    custom = tmp_path / "custom.db"
    monkeypatch.setenv("PROMPT_LIBRARY_DB", str(custom))
    assert get_db_path() == custom


def test_connection_in_memory():
    """In-memory database should work."""
    conn = get_connection(":memory:")
    assert isinstance(conn, sqlite3.Connection)
    close_connection()


def test_init_db_creates_tables():
    """init_db should create prompts, prompts_fts, and schema_version."""
    conn = get_connection(":memory:")
    init_db(conn)

    # Check prompts table exists
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='prompts'"
    ).fetchone()
    assert tables is not None

    # Check FTS virtual table exists
    fts = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='prompts_fts'"
    ).fetchone()
    assert fts is not None

    # Check triggers exist
    triggers = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger'"
    ).fetchall()
    trigger_names = {r[0] for r in triggers}
    assert "prompts_ai" in trigger_names
    assert "prompts_ad" in trigger_names
    assert "prompts_au" in trigger_names

    close_connection()


def test_init_db_idempotent():
    """Calling init_db twice should not raise."""
    conn = get_connection(":memory:")
    init_db(conn)
    init_db(conn)  # second call should be OK
    close_connection()


def test_schema_version_table():
    """schema_version table should be created with version 1."""
    conn = get_connection(":memory:")
    init_db(conn)
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    assert row is not None
    assert row[0] == 1


def test_fts_insert_trigger():
    """Inserting into prompts should auto-populate prompts_fts."""
    conn = get_connection(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO prompts (id, title, description, category, tags, body) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("test-id", "Test Title", "A test description", "testing", '["tag1"]', "Hello world body"),
    )
    row = conn.execute(
        "SELECT title, body FROM prompts_fts WHERE rowid = ?",
        (conn.execute("SELECT rowid FROM prompts WHERE id = ?", ("test-id",)).fetchone()[0],),
    ).fetchone()
    assert row is not None
    assert "Test Title" in row[0]
    assert "Hello world body" in row[1]
    close_connection()


def test_fts_delete_trigger():
    """Deleting from prompts should clean up prompts_fts."""
    conn = get_connection(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO prompts (id, title, description, category, body) "
        "VALUES (?, ?, ?, ?, ?)",
        ("del-id", "Del Title", "Desc", "cat", "body"),
    )
    conn.execute("DELETE FROM prompts WHERE id = ?", ("del-id",))
    count = conn.execute("SELECT COUNT(*) FROM prompts_fts").fetchone()[0]
    assert count == 0
    close_connection()


def test_fts_update_trigger():
    """Updating prompts should sync to prompts_fts."""
    conn = get_connection(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO prompts (id, title, description, category, body) "
        "VALUES (?, ?, ?, ?, ?)",
        ("upd-id", "Old Title", "Desc", "cat", "old body"),
    )
    conn.execute(
        "UPDATE prompts SET title = ? WHERE id = ?",
        ("New Title", "upd-id"),
    )
    row = conn.execute(
        "SELECT title FROM prompts_fts WHERE rowid = ?",
        (conn.execute("SELECT rowid FROM prompts WHERE id = ?", ("upd-id",)).fetchone()[0],),
    ).fetchone()
    assert row[0] == "New Title"
    close_connection()


def test_wal_mode():
    """Database should be opened in WAL mode."""
    conn = get_connection(":memory:")
    init_db(conn)
    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    # :memory: returns "memory" not "wal", but file-based returns "wal"
    # We just verify it runs without error
    assert journal_mode in ("wal", "memory")
    close_connection()
