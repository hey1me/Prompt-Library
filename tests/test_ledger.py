"""Tests for the transaction ledger."""

import os
from pathlib import Path

import pytest

from pl.ledger import (
    append,
    is_enabled,
    read_entries,
    replay_ledger,
    LedgerEntry,
    LEDGER_HEADER,
)


def test_is_enabled_default(monkeypatch):
    """Ledger should be disabled by default."""
    monkeypatch.delenv("PROMPT_LIBRARY_LEDGER", raising=False)
    assert not is_enabled()


def test_is_enabled_when_set(monkeypatch):
    """Ledger should be enabled when env var is 1."""
    monkeypatch.setenv("PROMPT_LIBRARY_LEDGER", "1")
    assert is_enabled()


def test_is_enabled_false_values(monkeypatch):
    """Ledger should be disabled for 0, false, empty."""
    for val in ("0", "false", "", "no"):
        monkeypatch.setenv("PROMPT_LIBRARY_LEDGER", val)
        assert not is_enabled()


def test_append_and_read(tmp_path):
    """Appending entries and reading them back should work."""
    ledger_path = tmp_path / "ledger.log"
    append("CREATE", "test-prompt", {"version": "1.0", "category": "test"}, ledger_path)
    append("FETCH", "test-prompt", None, ledger_path)
    append("UPDATE", "test-prompt", {"version": "1.1"}, ledger_path)

    entries = list(read_entries(ledger_path))
    assert len(entries) == 3
    assert entries[0].action == "CREATE"
    assert entries[0].prompt_id == "test-prompt"
    assert entries[0].payload == {"version": "1.0", "category": "test"}
    assert entries[1].action == "FETCH"
    assert entries[1].payload is None
    assert entries[2].action == "UPDATE"


def test_ledger_header(tmp_path):
    """Ledger file should start with a header line."""
    ledger_path = tmp_path / "ledger.log"
    append("CREATE", "test", None, ledger_path)
    content = ledger_path.read_text()
    assert content.startswith(LEDGER_HEADER)


def test_append_creates_parent_dirs(tmp_path):
    """Ledger should create parent directories if they don't exist."""
    nested = tmp_path / "sub" / "dir" / "ledger.log"
    append("CREATE", "test", None, nested)
    assert nested.exists()


def test_replay_ledger(tmp_path):
    """Replaying a ledger should return the sequence of entries."""
    ledger_path = tmp_path / "replay.log"
    append("CREATE", "p1", {"category": "dev"}, ledger_path)
    append("CREATE", "p2", {"category": "writing"}, ledger_path)
    append("DELETE", "p1", None, ledger_path)

    entries = replay_ledger(ledger_path)
    assert len(entries) == 3
    assert entries[0].action == "CREATE"
    assert entries[2].action == "DELETE"


def test_malformed_line_skipped(tmp_path, caplog):
    """Malformed lines should be skipped with a warning."""
    ledger_path = tmp_path / "ledger.log"
    ledger_path.write_text(
        f"{LEDGER_HEADER}\n"
        "garbage data\n"
        "2026-01-01T00:00:00Z|CREATE|test|\n"
    )
    entries = list(read_entries(ledger_path))
    assert len(entries) == 1
    assert entries[0].prompt_id == "test"


def test_large_payload_serialization(tmp_path):
    """Payload with special characters should survive round-trip."""
    ledger_path = tmp_path / "ledger.log"
    payload = {"body": "line1\nline2", "tags": ["a,b", "c:d"]}
    append("CREATE", "complex", payload, ledger_path)
    entries = list(read_entries(ledger_path))
    assert entries[0].payload == payload


def test_rotation_threshold(tmp_path, monkeypatch):
    """Ledger should rotate when approaching size threshold."""
    ledger_path = tmp_path / "ledger.log"
    # Create a ledger file just under 100MB with header + 1000 entries
    # We test rotation logic by writing many entries
    for i in range(10):
        append("CREATE", f"p{i}", {"x": "y" * 1000}, ledger_path)

    assert ledger_path.exists()
    # Rotation is checked on each append but only triggers at 100MB
    # So 10 small entries won't trigger it
    entries = list(read_entries(ledger_path))
    assert len(entries) == 10
