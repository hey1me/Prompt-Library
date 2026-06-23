"""SQLite-backed storage layer for the Prompt Library.

Replaces YAML-file-based storage with a SQLite database using FTS5 full-text
search. All prompt metadata and body text are stored in a single ``prompts``
table with an FTS5 virtual table for search.
"""

import json
import math
import os
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Any, Optional

import yaml

from pl.database import get_connection, init_db as _init_db_schema
from pl.ledger import append as ledger_append, is_enabled as ledger_enabled
from pl.migrations import run_migrations
from pl.models import Prompt, Variable

FRONTMATTER_PATTERN = re.compile(r"^---\s*$", re.MULTILINE)

# Default prompts directory (YAML import/export)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


# ── Initialization ──────────────────────────────────────────────────────────

def init_db(db_path: Optional[str | Path] = None) -> None:
    """Initialize the database, run schema creation, and apply migrations.

    Args:
        db_path: Path to the SQLite database. Defaults to XDG path.
    """
    conn = get_connection(db_path)
    _init_db_schema(conn)
    run_migrations(conn)
    conn.commit()


# ── Internal helpers ────────────────────────────────────────────────────────

def _prompt_from_row(row: dict) -> Prompt:
    """Convert a SQLite row dict to a Prompt model."""
    data = dict(row)
    # Parse JSON fields
    if isinstance(data.get("tags"), str):
        data["tags"] = json.loads(data["tags"])
    if isinstance(data.get("variables"), str):
        raw_vars = json.loads(data["variables"])
        data["variables"] = [Variable(**v) for v in raw_vars]
    # Parse date fields
    for field in ("created", "updated"):
        if isinstance(data.get(field), str):
            try:
                data[field] = date.fromisoformat(data[field])
            except (ValueError, TypeError):
                pass
    # Ensure default values
    data.setdefault("fetch_count", 0)
    data.setdefault("user_rating", 0.0)
    return Prompt(**data)


def _prompt_to_row(prompt: Prompt) -> dict:
    """Convert a Prompt model to a SQLite row dict."""
    return {
        "id": prompt.id,
        "title": prompt.title,
        "description": prompt.description,
        "category": prompt.category,
        "tags": json.dumps(prompt.tags),
        "model_hint": prompt.model_hint,
        "variables": json.dumps([
            {"name": v.name, "description": v.description, "default": v.default}
            for v in prompt.variables
        ]),
        "version": prompt.version,
        "created": str(prompt.created) if prompt.created else None,
        "updated": str(prompt.updated) if prompt.updated else None,
        "body": prompt.body,
        "fetch_count": prompt.fetch_count,
        "user_rating": prompt.user_rating,
    }


def _parse_yaml_frontmatter(filepath: Path) -> tuple[dict, str]:
    """Parse a YAML file with frontmatter separated by ``---``.

    Returns (metadata_dict, body_string).
    """
    content = filepath.read_text(encoding="utf-8")
    parts = FRONTMATTER_PATTERN.split(content, maxsplit=1)
    if len(parts) == 1:
        return {}, content.strip()
    metadata = yaml.safe_load(parts[0].strip()) or {}
    body = parts[1].strip()
    for field in ("created", "updated"):
        raw = metadata.get(field)
        if isinstance(raw, str):
            metadata[field] = date.fromisoformat(raw)
    return metadata, body


def _get_conn(connection=None):
    """Get connection, using module-level default if none provided."""
    if connection is not None:
        return connection
    return get_connection()


# ── Public API ──────────────────────────────────────────────────────────────

def list_prompts(category: Optional[str] = None, *, connection=None) -> list[Prompt]:
    """List all prompts, optionally filtered by category.

    Results are sorted alphabetically by title.
    """
    conn = _get_conn(connection)
    if category:
        rows = conn.execute(
            "SELECT * FROM prompts WHERE category = ? ORDER BY title",
            (category,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM prompts ORDER BY title").fetchall()
    return [_prompt_from_row(r) for r in rows]


def get_prompt(prompt_id: str, *, connection=None) -> Optional[Prompt]:
    """Retrieve a prompt by its unique ID.

    Returns None if no prompt matches.
    """
    conn = _get_conn(connection)
    row = conn.execute(
        "SELECT * FROM prompts WHERE id = ?", (prompt_id,)
    ).fetchone()
    return _prompt_from_row(row) if row else None


def add_prompt(
    prompt: Prompt,
    *,
    connection=None,
    yaml_output: Optional[Path] = None,
) -> Prompt:
    """Add a new prompt to the database.

    Args:
        prompt: The Prompt model to insert.
        connection: Optional SQLite connection (uses default if None).
        yaml_output: If set, also write the prompt as a YAML file to this directory.

    Returns:
        The inserted Prompt.

    Raises:
        FileExistsError: If a prompt with the same ID already exists.
    """
    conn = _get_conn(connection)

    existing = conn.execute(
        "SELECT id FROM prompts WHERE id = ?", (prompt.id,)
    ).fetchone()
    if existing:
        raise FileExistsError(f"Prompt with ID '{prompt.id}' already exists.")

    row = _prompt_to_row(prompt)
    conn.execute(
        """INSERT INTO prompts
           (id, title, description, category, tags, model_hint, variables,
            version, created, updated, body, fetch_count, user_rating)
           VALUES (:id, :title, :description, :category, :tags, :model_hint,
                   :variables, :version, :created, :updated, :body,
                   :fetch_count, :user_rating)""",
        row,
    )
    conn.commit()

    if ledger_enabled():
        ledger_append("CREATE", prompt.id, {"category": prompt.category, "version": prompt.version})

    if yaml_output:
        _write_yaml(prompt, yaml_output)

    return prompt


def update_prompt(
    prompt_id: str,
    fields: dict[str, Any],
    *,
    connection=None,
) -> Prompt:
    """Update a prompt's fields.

    Args:
        prompt_id: The ID of the prompt to update.
        fields: Dict of field names to new values.
        connection: Optional SQLite connection.

    Returns:
        The updated Prompt.

    Raises:
        KeyError: If the prompt ID does not exist.
    """
    conn = _get_conn(connection)

    existing = conn.execute(
        "SELECT id FROM prompts WHERE id = ?", (prompt_id,)
    ).fetchone()
    if not existing:
        raise KeyError(f"No prompt with ID '{prompt_id}'.")

    # Serialize JSON fields if provided
    if "tags" in fields and isinstance(fields["tags"], list):
        fields["tags"] = json.dumps(fields["tags"])
    if "variables" in fields and isinstance(fields["variables"], list):
        fields["variables"] = json.dumps([
            {"name": v.name, "description": v.description, "default": v.default}
            if isinstance(v, Variable) else v
            for v in fields["variables"]
        ])
    if "created" in fields and isinstance(fields["created"], date):
        fields["created"] = str(fields["created"])
    if "updated" in fields and isinstance(fields["updated"], date):
        fields["updated"] = str(fields["updated"])

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [prompt_id]
    conn.execute(f"UPDATE prompts SET {set_clause} WHERE id = ?", values)
    conn.commit()

    if ledger_enabled():
        ledger_append("UPDATE", prompt_id, fields)

    return get_prompt(prompt_id, connection=conn)


def increment_fetch(prompt_id: str, *, connection=None) -> None:
    """Increment the fetch_count for a prompt by 1."""
    conn = _get_conn(connection)
    conn.execute(
        "UPDATE prompts SET fetch_count = fetch_count + 1 WHERE id = ?",
        (prompt_id,),
    )
    conn.commit()

    if ledger_enabled():
        ledger_append("FETCH", prompt_id)


def delete_prompt(prompt_id: str, *, connection=None) -> None:
    """Delete a prompt by its ID.

    Raises:
        KeyError: If the prompt ID does not exist.
    """
    conn = _get_conn(connection)
    existing = conn.execute(
        "SELECT id FROM prompts WHERE id = ?", (prompt_id,)
    ).fetchone()
    if not existing:
        raise KeyError(f"No prompt with ID '{prompt_id}'.")
    conn.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
    conn.commit()

    if ledger_enabled():
        ledger_append("DELETE", prompt_id)


def search(
    query: str,
    category: str = "",
    limit: int = 20,
    *,
    connection=None,
) -> list[Prompt]:
    """Full-text search using FTS5 with BM25 + usage-based ranking.

    The compound scoring formula::

        Final Rank = BM25_text_score + (log10(fetch_count + 1) * user_rating)

    Args:
        query: The search query string.
        category: Optional category filter (empty = no filter).
        limit: Maximum number of results (default 20).
        connection: Optional SQLite connection.

    Returns:
        A list of Prompt objects ranked by relevance.
    """
    conn = _get_conn(connection)

    # Build FTS5 MATCH query: split terms, join with AND
    terms = query.strip().lower().split()
    fts_query = " AND ".join(terms) if terms else query

    sql = """
        SELECT p.*,
               bm25(prompts_fts, 0, 1, 2, 3) AS text_score,
               (log10(max(p.fetch_count, 0) + 1) * max(p.user_rating, 0.0)) AS usage_weight
        FROM prompts p
        JOIN prompts_fts ON p.rowid = prompts_fts.rowid
        WHERE prompts_fts MATCH ?
          AND (? = '' OR p.category = ?)
        ORDER BY text_score + usage_weight DESC
        LIMIT ?
    """

    try:
        rows = conn.execute(sql, (fts_query, category, category, limit)).fetchall()
    except Exception:
        # Fallback: try with prefix wildcards
        fts_fallback = " OR ".join(f"{t}*" for t in terms) if terms else query + "*"
        try:
            rows = conn.execute(sql, (fts_fallback, category, category, limit)).fetchall()
        except Exception:
            rows = []

    return [_prompt_from_row(r) for r in rows]


def import_yaml(
    prompts_dir: Optional[Path] = None,
    *,
    connection=None,
) -> int:
    """Import all YAML prompt files from a directory tree into the database.

    Scans ``prompts_dir`` recursively for ``*.yaml`` files, parses frontmatter,
    and inserts each as a prompt. Malformed files are skipped with a warning.

    Args:
        prompts_dir: Root directory to scan (default: project's prompts/ directory).
        connection: Optional SQLite connection.

    Returns:
        The number of prompts successfully imported.
    """
    if prompts_dir is None:
        prompts_dir = PROMPTS_DIR

    conn = _get_conn(connection)
    imported = 0

    for yaml_file in sorted(prompts_dir.rglob("*.yaml")):
        try:
            metadata, body = _parse_yaml_frontmatter(yaml_file)
            metadata["body"] = body
            prompt = Prompt(**metadata)

            # Use INSERT OR IGNORE for idempotent imports
            row = _prompt_to_row(prompt)
            before = conn.total_changes
            conn.execute(
                """INSERT OR IGNORE INTO prompts
                   (id, title, description, category, tags, model_hint, variables,
                    version, created, updated, body, fetch_count, user_rating)
                   VALUES (:id, :title, :description, :category, :tags, :model_hint,
                           :variables, :version, :created, :updated, :body,
                           :fetch_count, :user_rating)""",
                row,
            )
            if conn.total_changes > before:
                imported += 1
                if ledger_enabled():
                    ledger_append("CREATE", prompt.id, {"category": prompt.category, "source": str(yaml_file)})
        except Exception as exc:
            import sys
            print(f"Warning: Could not import {yaml_file}: {exc}", file=sys.stderr)

    conn.commit()
    return imported


def export_yaml(
    output_dir: Path,
    *,
    connection=None,
) -> int:
    """Export all prompts from the database to YAML files.

    Creates one file per prompt, organized in ``output_dir/<category>/``.

    Args:
        output_dir: Root output directory for YAML files.
        connection: Optional SQLite connection.

    Returns:
        The number of files written.
    """
    conn = _get_conn(connection)
    prompts = list_prompts(connection=conn)
    written = 0

    for prompt in prompts:
        written += _write_yaml(prompt, output_dir)

    return written


def _write_yaml(prompt: Prompt, output_dir: Path) -> int:
    """Write a single prompt to a YAML file in ``output_dir/<category>/``."""
    category_dir = output_dir / prompt.category
    category_dir.mkdir(parents=True, exist_ok=True)
    dest = category_dir / f"{prompt.id}.yaml"

    # Build frontmatter dict
    frontmatter = {
        "id": prompt.id,
        "title": prompt.title,
        "description": prompt.description,
        "category": prompt.category,
        "tags": prompt.tags,
    }
    if prompt.model_hint:
        frontmatter["model_hint"] = prompt.model_hint
    if prompt.variables:
        frontmatter["variables"] = [
            {"name": v.name, "description": v.description, "default": v.default}
            for v in prompt.variables
        ]
    frontmatter["version"] = prompt.version
    if prompt.created:
        frontmatter["created"] = str(prompt.created)
    if prompt.updated:
        frontmatter["updated"] = str(prompt.updated)
    # Export usage data as optional fields
    if prompt.fetch_count:
        frontmatter["fetch_count"] = prompt.fetch_count
    if prompt.user_rating:
        frontmatter["user_rating"] = prompt.user_rating

    yaml_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False, allow_unicode=True)
    content = f"{yaml_str}---\n{prompt.body}\n"
    dest.write_text(content, encoding="utf-8")
    return 1


def get_categories(*, connection=None) -> list[dict]:
    """Return distinct categories with prompt counts.

    Returns a list of dicts: ``[{"name": "development", "count": 5}, ...]``
    """
    conn = _get_conn(connection)
    rows = conn.execute(
        "SELECT category AS name, COUNT(*) AS count FROM prompts GROUP BY category ORDER BY category"
    ).fetchall()
    return [dict(r) for r in rows]


def get_info(*, connection=None) -> dict:
    """Return database statistics.

    Returns a dict with keys: ``total_prompts``, ``total_fetches``, ``db_size_bytes``.
    """
    conn = _get_conn(connection)
    total = conn.execute("SELECT COUNT(*) FROM prompts").fetchone()[0]
    fetches = conn.execute("SELECT COALESCE(SUM(fetch_count), 0) FROM prompts").fetchone()[0]

    # Get DB file size (for :memory:, return 0)
    db_path = conn.execute("PRAGMA database_list").fetchone()
    db_file = db_path[2] if db_path else ""
    try:
        size = os.path.getsize(db_file) if db_file else 0
    except OSError:
        size = 0

    return {
        "total_prompts": total,
        "total_fetches": fetches,
        "db_size_bytes": size,
    }


def optimize(*, connection=None) -> None:
    """Rebuild the FTS index and VACUUM the database for optimal performance."""
    conn = _get_conn(connection)
    conn.execute("INSERT INTO prompts_fts(prompts_fts) VALUES('rebuild')")
    conn.execute("PRAGMA optimize")
    conn.commit()
    # VACUUM must be run outside a transaction
    conn.execute("VACUUM")
