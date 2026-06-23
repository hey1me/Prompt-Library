"""SQLite database connection and schema management for the Prompt Library.

Provides a module-level connection singleton with WAL mode, FTS5-backed schema
initialization, and XDG-compliant database path resolution.
"""

import os
import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS prompts (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    category TEXT NOT NULL,
    tags TEXT DEFAULT '[]',
    model_hint TEXT DEFAULT '',
    variables TEXT DEFAULT '[]',
    version TEXT DEFAULT '1.0',
    created TEXT,
    updated TEXT,
    body TEXT NOT NULL DEFAULT '',
    fetch_count INTEGER DEFAULT 0,
    user_rating REAL DEFAULT 0.0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_prompts_category ON prompts(category);
CREATE INDEX IF NOT EXISTS idx_prompts_updated ON prompts(updated_at);

CREATE VIRTUAL TABLE IF NOT EXISTS prompts_fts USING fts5(
    title, description, tags, body,
    content='prompts',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS prompts_ai AFTER INSERT ON prompts BEGIN
    INSERT INTO prompts_fts(rowid, title, description, tags, body)
    VALUES (new.rowid, new.title, new.description, new.tags, new.body);
END;

CREATE TRIGGER IF NOT EXISTS prompts_ad AFTER DELETE ON prompts BEGIN
    INSERT INTO prompts_fts(prompts_fts, rowid, title, description, tags, body)
    VALUES ('delete', old.rowid, old.title, old.description, old.tags, old.body);
END;

CREATE TRIGGER IF NOT EXISTS prompts_au AFTER UPDATE ON prompts BEGIN
    INSERT INTO prompts_fts(prompts_fts, rowid, title, description, tags, body)
    VALUES ('delete', old.rowid, old.title, old.description, old.tags, old.body);
    INSERT INTO prompts_fts(rowid, title, description, tags, body)
    VALUES (new.rowid, new.title, new.description, new.tags, new.body);
END;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO schema_version (version) VALUES (1);
"""

_connection: sqlite3.Connection | None = None


def _get_xdg_data_path() -> Path:
    """Return the XDG data home directory for the prompt library."""
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        base = Path(xdg)
    else:
        base = Path.home() / ".local" / "share"
    return base / "prompt-library"


def get_db_path() -> Path:
    """Resolve the database path.

    Priority:
    1. PROMPT_LIBRARY_DB env var
    2. ~/.local/share/prompt-library/library.db (XDG default)
    """
    env_path = os.environ.get("PROMPT_LIBRARY_DB")
    if env_path:
        return Path(env_path)
    return _get_xdg_data_path() / "library.db"


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Return a module-level SQLite connection.

    If ``db_path`` is ``None``, uses the resolved default path.
    Pass ``":memory:"`` for testing.

    The connection uses ``check_same_thread=False`` (safe for single-process CLI use)
    and enables WAL journal mode for concurrent reads.
    """
    global _connection

    if _connection is not None:
        if db_path is None:
            return _connection
        # If a specific path is requested, close global and create new
        close_connection()

    if db_path is None:
        db_path = get_db_path()

    if isinstance(db_path, Path):
        db_path = str(db_path)

    # Ensure the parent directory exists (sqlite3.connect does not create it)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Use the global only for the default path
    if db_path == str(get_db_path()) or db_path == ":memory:":
        _connection = conn

    return conn


def close_connection() -> None:
    """Close the module-level database connection if open."""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None


def init_db(conn: sqlite3.Connection | None = None) -> sqlite3.Connection:
    """Initialize the database schema.

    Creates the prompts table, FTS5 virtual table, triggers, and schema_version
    table if they do not already exist.

    Args:
        conn: An existing connection, or ``None`` to open the default.

    Returns:
        The database connection.
    """
    if conn is None:
        conn = get_connection()
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn
