"""FTS5-backed search engine for the Prompt Library.

Replaces the in-memory heuristic scoring with SQLite FTS5 BM25 ranking
combined with a usage-based weight.

Compound scoring formula::

    Final Rank = BM25_text_score + (log10(fetch_count + 1) * user_rating)

Fallback chain:
1. Exact FTS5 AND query on all terms
2. Prefix wildcard (``term*``) on each term with OR
3. LIKE scan on title column (last resort)
"""

import json
import math
import re
import sqlite3
from datetime import date
from typing import Optional

from pl.database import get_connection
from pl.models import Prompt, Variable

_NON_ALPHA = re.compile(r"[^a-z0-9 ]")


def _prompt_from_row(row: sqlite3.Row) -> Prompt:
    """Convert a SQLite row (dict-like access) to a Prompt object."""
    tags = json.loads(row["tags"]) if row["tags"] else []
    variables_raw = json.loads(row["variables"]) if row["variables"] else []
    variables = [Variable(**v) for v in variables_raw]

    created = date.fromisoformat(row["created"]) if row["created"] else None
    updated = date.fromisoformat(row["updated"]) if row["updated"] else None

    return Prompt(
        id=row["id"],
        title=row["title"],
        description=row["description"] or "",
        category=row["category"],
        tags=tags,
        model_hint=row["model_hint"] or "",
        variables=variables,
        version=row["version"] or "1.0",
        created=created,
        updated=updated,
        body=row["body"] or "",
        fetch_count=row["fetch_count"] or 0,
        user_rating=row["user_rating"] or 0.0,
    )


def _parse_fts_query(query: str) -> str:
    """Convert a user's natural-language query into an FTS5 MATCH expression.

    Strips non-alphanumeric characters, lowercases, splits into terms,
    and joins with ``AND``.

    Examples:
        "code review"       -> "code AND review"
        "python api design" -> "python AND api AND design"
        ""                  -> ""
    """
    cleaned = _NON_ALPHA.sub(" ", query.lower()).strip()
    terms = [t for t in cleaned.split() if t]
    if not terms:
        return ""
    return " AND ".join(terms)


def _storage_search(
    query: str,
    category: str = "",
    connection: Optional[sqlite3.Connection] = None,
) -> list:
    """FTS5 search with BM25 ranking and usage-based weight."""
    conn = connection or get_connection()

    fts_query = _parse_fts_query(query)
    if not fts_query:
        return []

    # Register log10 for the ranking formula (portable across SQLite builds)
    try:
        conn.create_function("log10", 1, math.log10)
    except sqlite3.ProgrammingError:
        pass

    sql = """
        SELECT p.*,
               bm25(prompts_fts, 0, 1, 2, 3)
               + (log10(CAST(COALESCE(p.fetch_count, 0) AS REAL) + 1) * COALESCE(p.user_rating, 0.0))
               AS combined
        FROM prompts p
        JOIN prompts_fts ON p.rowid = prompts_fts.rowid
        WHERE prompts_fts MATCH ?
          AND (? = '' OR p.category = ?)
        ORDER BY combined DESC
        LIMIT 20
    """
    try:
        rows = conn.execute(sql, (fts_query, category, category)).fetchall()
        return [_prompt_from_row(r) for r in rows]
    except Exception:
        return []


def _fallback_search(
    query: str,
    category: str = "",
    connection: Optional[sqlite3.Connection] = None,
) -> list:
    """Fallback search using LIKE on title when FTS5 returns no results."""
    conn = connection or get_connection()
    sql = """
        SELECT * FROM prompts
        WHERE (title LIKE ? OR description LIKE ?)
          AND (? = '' OR category = ?)
        ORDER BY
            CASE WHEN title LIKE ? THEN 0 ELSE 1 END,
            title
        LIMIT 20
    """
    like_pattern = f"%{query}%"
    try:
        rows = conn.execute(
            sql,
            (like_pattern, like_pattern, category, category, like_pattern),
        ).fetchall()
        return [_prompt_from_row(r) for r in rows]
    except Exception:
        return []


def search_prompts(
    query: str,
    category: str = "",
    connection: Optional[sqlite3.Connection] = None,
) -> list:
    """Search prompts by keyword using FTS5 full-text search with ranking.

    Args:
        query: The search query string (natural language).
        category: Optional category filter (empty string = no filter).
        connection: Optional SQLite connection (for testing).

    Returns:
        A list of Prompt objects ranked by relevance, or empty list if
        no matches are found.
    """
    if not query or not query.strip():
        return []

    conn = connection or get_connection()

    # Level 1: Full FTS5 AND query with BM25 + usage scoring
    result = _storage_search(query, category=category, connection=conn)

    # Level 2: If no results, try prefix wildcard (term*)
    if not result:
        terms = query.strip().lower().split()
        prefix_query = " OR ".join(f"{t}*" for t in terms)
        result = _storage_search(prefix_query, category=category, connection=conn)

    # Level 3: If still no results, try LIKE on title
    if not result:
        result = _fallback_search(query, category=category, connection=conn)

    return result
