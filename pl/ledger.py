"""Append-only transaction ledger for audit and replay.

Provides optional audit logging of all prompt mutations. The ledger is disabled
by default and enabled via the ``PROMPT_LIBRARY_LEDGER=1`` environment variable.

Ledger format (pipe-delimited)::

    # Prompt Library Transaction Ledger
    2026-06-23T10:00:00Z|CREATE|code-review|{"version":"1.0","category":"dev"}
    2026-06-23T10:05:00Z|FETCH|code-review|
    2026-06-23T10:30:00Z|UPDATE|code-review|{"version":"1.1"}
    2026-06-23T11:00:00Z|DELETE|old-prompt|
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator
from dataclasses import dataclass

LEDGER_HEADER = "# Prompt Library Transaction Ledger\n"
_MAX_LEDGER_BYTES = 100 * 1024 * 1024  # 100 MB


@dataclass
class LedgerEntry:
    """A single entry in the transaction ledger."""

    timestamp: str
    action: str      # CREATE, FETCH, UPDATE, DELETE
    prompt_id: str
    payload: dict | None



def is_enabled() -> bool:
    """Check whether the ledger is enabled (``PROMPT_LIBRARY_LEDGER=1``)."""
    val = os.environ.get("PROMPT_LIBRARY_LEDGER", "").strip().lower()
    return val in ("1", "true", "yes")


def get_ledger_path(db_path: Path | None = None) -> Path:
    """Return the ledger file path (same directory as the database)."""
    from pl.database import get_db_path as _get_db_path
    if db_path is None:
        db_path = _get_db_path()
    return db_path.parent / "ledger.log"


def append(
    action: str,
    prompt_id: str,
    payload: dict | None = None,
    ledger_path: Path | None = None,
) -> None:
    """Append a transaction entry to the ledger.

    Args:
        action: One of CREATE, FETCH, UPDATE, DELETE.
        prompt_id: The prompt identifier affected.
        payload: Optional JSON-serializable dict with additional data.
        ledger_path: Override path (for testing). Defaults to same dir as DB.

    Ledger write failures are non-fatal — a warning is logged to stderr
    and execution continues.
    """
    if ledger_path is None:
        ledger_path = get_ledger_path()

    if not ledger_path.parent.exists():
        ledger_path.parent.mkdir(parents=True, exist_ok=True)

    _rotate_if_needed(ledger_path)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload_str = json.dumps(payload, separators=(",", ":")) if payload else ""
    line = f"{timestamp}|{action}|{prompt_id}|{payload_str}\n"

    try:
        if not ledger_path.exists():
            ledger_path.write_text(LEDGER_HEADER, encoding="utf-8")
        with open(ledger_path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError as exc:
        import sys
        print(f"Warning: Ledger write failed — {exc}", file=sys.stderr)


def read_entries(ledger_path: Path) -> Generator[LedgerEntry, None, None]:
    """Yield parsed ledger entries, skipping malformed lines."""
    if not ledger_path.exists():
        return

    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|", 3)
        if len(parts) < 3:
            continue
        timestamp, action, prompt_id = parts[0], parts[1], parts[2]
        payload = None
        if len(parts) == 4 and parts[3]:
            try:
                payload = json.loads(parts[3])
            except json.JSONDecodeError:
                pass
        yield LedgerEntry(timestamp=timestamp, action=action, prompt_id=prompt_id, payload=payload)


def replay_ledger(ledger_path: Path) -> list[LedgerEntry]:
    """Read and return all entries from a ledger (for replay/recovery).

    Returns all entries in chronological order. This can be used to rebuild
    a database from scratch by iterating the entries and re-applying them.
    """
    return list(read_entries(ledger_path))


def _rotate_if_needed(ledger_path: Path) -> None:
    """Rotate the ledger file if it exceeds the maximum size."""
    if not ledger_path.exists():
        return
    try:
        size = ledger_path.stat().st_size
        if size >= _MAX_LEDGER_BYTES:
            rotated = ledger_path.with_suffix(".log.1")
            ledger_path.rename(rotated)
    except OSError:
        pass
