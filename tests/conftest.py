"""Shared fixtures for Prompt Library tests."""

import json
from datetime import date
from pathlib import Path

import pytest

from pl.database import get_connection, close_connection, init_db
from pl.models import Prompt, Variable

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "prompts"


@pytest.fixture
def db_connection():
    """Provide an in-memory SQLite connection with initialized schema."""
    conn = get_connection(":memory:")
    init_db(conn)
    yield conn
    close_connection()


@pytest.fixture
def sample_prompt() -> Prompt:
    """A basic prompt for use in tests."""
    return Prompt(
        id="test-prompt",
        title="Test Prompt",
        description="A test prompt for unit tests",
        category="development",
        tags=["test", "example"],
        model_hint="claude",
        variables=[
            Variable(name="var1", description="First variable", default="default1"),
            Variable(name="var2", description="Second variable"),
        ],
        version="1.0",
        created=date(2026, 1, 1),
        updated=date(2026, 6, 1),
        body="This is a test prompt body with {{var1}} and {{var2}}.",
        fetch_count=0,
        user_rating=0.0,
    )


@pytest.fixture
def sample_prompts() -> list[Prompt]:
    """Multiple prompts for list/search testing."""
    return [
        Prompt(
            id="code-review",
            title="Code Review Checklist",
            description="Systematic code review prompts",
            category="development",
            tags=["review", "code-quality"],
            body="Review the following code for issues.",
            fetch_count=10,
            user_rating=4.5,
        ),
        Prompt(
            id="blog-post",
            title="Blog Post Generator",
            description="Generate blog post outlines",
            category="writing",
            tags=["blog", "content"],
            body="Write a blog post about {{topic}}.",
            fetch_count=5,
            user_rating=3.0,
        ),
        Prompt(
            id="swot-analysis",
            title="SWOT Analysis",
            description="Strategic analysis framework",
            category="analysis",
            tags=["strategy", "planning"],
            body="Conduct a SWOT analysis.",
            fetch_count=2,
            user_rating=0.0,
        ),
        Prompt(
            id="api-design",
            title="REST API Design Review",
            description="Review API endpoint design",
            category="development",
            tags=["api", "rest"],
            body="Review this REST API design.",
            fetch_count=0,
            user_rating=0.0,
        ),
        Prompt(
            id="email-draft",
            title="Email Draft Generator",
            description="Draft professional emails",
            category="writing",
            tags=["email", "professional"],
            body="Draft a professional email.",
            fetch_count=8,
            user_rating=5.0,
        ),
    ]


@pytest.fixture
def populated_db(db_connection, sample_prompts):
    """Database pre-populated with sample prompts."""
    conn = db_connection
    for p in sample_prompts:
        tags_json = json.dumps(p.tags)
        variables_json = json.dumps([
            {"name": v.name, "description": v.description, "default": v.default}
            for v in p.variables
        ])
        conn.execute(
            """INSERT INTO prompts
               (id, title, description, category, tags, model_hint, variables,
                version, created, updated, body, fetch_count, user_rating)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                p.id, p.title, p.description, p.category, tags_json,
                p.model_hint, variables_json, p.version,
                str(p.created) if p.created else None,
                str(p.updated) if p.updated else None,
                p.body, p.fetch_count, p.user_rating,
            ),
        )
    conn.commit()
    return conn


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to the test fixture YAML prompts directory."""
    return FIXTURES_DIR
