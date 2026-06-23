"""Tests for Prompt and Variable models."""

from datetime import date

import pytest
from pydantic import ValidationError

from pl.models import Prompt, Variable


def test_prompt_defaults():
    """Prompt should have sensible defaults for optional fields."""
    p = Prompt(id="test-prompt", title="Test", category="testing", body="Hello")
    assert p.fetch_count == 0
    assert p.user_rating == 0.0
    assert p.tags == []
    assert p.variables == []
    assert p.version == "1.0"
    assert p.description == ""
    assert p.model_hint == ""


def test_prompt_with_fetch_count():
    """fetch_count should round-trip through model creation."""
    p = Prompt(id="test", title="T", category="c", body="b", fetch_count=42, user_rating=3.5)
    assert p.fetch_count == 42
    assert p.user_rating == 3.5


def test_prompt_invalid_id():
    """ID must be kebab-case."""
    with pytest.raises(ValidationError):
        Prompt(id="Invalid ID!", title="T", category="c", body="b")


def test_prompt_valid_ids():
    """Various valid kebab-case IDs."""
    for valid in ("simple", "kebab-case", "with-123", "a", "z".zfill(50)):
        p = Prompt(id=valid, title="T", category="c", body="b")
        assert p.id == valid


def test_prompt_with_variables():
    """Variables should be a list of Variable objects."""
    vars_list = [
        Variable(name="lang", description="Language", default="python"),
        Variable(name="code", description="Code snippet"),
    ]
    p = Prompt(id="test", title="T", category="c", body="b", variables=vars_list)
    assert len(p.variables) == 2
    assert p.variables[0].name == "lang"
    assert p.variables[0].default == "python"
    assert p.variables[1].default is None


def test_prompt_dates():
    """created and updated should accept date objects and strings."""
    p = Prompt(
        id="test", title="T", category="c", body="b",
        created=date(2026, 1, 15),
    )
    assert p.created == date(2026, 1, 15)


def test_variable_model():
    """Variable should have name, description, and optional default."""
    v = Variable(name="x")
    assert v.name == "x"
    assert v.description == ""
    assert v.default is None

    v2 = Variable(name="y", description="desc", default="val")
    assert v2.default == "val"


def test_prompt_serialization():
    """Prompt should serialize to dict with all fields."""
    p = Prompt(
        id="my-prompt", title="My Title", category="dev", body="content",
        tags=["a", "b"], fetch_count=10, user_rating=4.0,
    )
    d = p.model_dump()
    assert d["id"] == "my-prompt"
    assert d["fetch_count"] == 10
    assert d["user_rating"] == 4.0
    assert d["tags"] == ["a", "b"]


def test_prompt_round_trip():
    """Prompt should round-trip through dict serialization."""
    original = Prompt(
        id="round-trip", title="RT", category="test", body="body",
        fetch_count=7, user_rating=2.5, tags=["x"],
    )
    d = original.model_dump()
    restored = Prompt(**d)
    assert restored.model_dump() == original.model_dump()
