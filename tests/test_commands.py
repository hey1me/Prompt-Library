"""Integration tests for CLI commands.

Uses Click's CliRunner to invoke commands in isolation with an in-memory
database.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from pl.commands import cli
from pl.storage import import_yaml, get_prompt


@pytest.fixture
def runner():
    """Click test runner."""
    return CliRunner()


@pytest.fixture
def populated_db_args(db_connection, sample_prompts, monkeypatch):
    """Monkey-patch get_connection to return our in-memory DB with prompts."""
    import pl.database
    import pl.storage
    import pl.commands
    
    # Insert sample prompts
    import json
    from datetime import date
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
    
    # Monkey-patch to use our connection
    monkeypatch.setattr(pl.database, "get_connection", lambda db_path=None: conn)
    monkeypatch.setattr(pl.storage, "get_connection", lambda db_path=None: conn)
    monkeypatch.setattr(pl.commands, "get_connection", lambda db_path=None: conn)
    
    yield
    
    # Clean up
    pl.database._connection = None


class TestListCommand:
    def test_list_all(self, runner, populated_db_args):
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "code-review" in result.output
        assert "blog-post" in result.output
        assert "5 prompt(s) found." in result.output

    def test_list_by_category(self, runner, populated_db_args):
        result = runner.invoke(cli, ["list", "--category", "development"])
        assert result.exit_code == 0
        assert "code-review" in result.output
        assert "api-design" in result.output
        assert "blog-post" not in result.output

    def test_list_no_prompts(self, runner, db_connection, monkeypatch):
        import pl.database
        import pl.storage
        import pl.commands
        monkeypatch.setattr(pl.database, "get_connection", lambda db_path=None: db_connection)
        monkeypatch.setattr(pl.storage, "get_connection", lambda db_path=None: db_connection)
        monkeypatch.setattr(pl.commands, "get_connection", lambda db_path=None: db_connection)
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "No prompts found." in result.output


class TestSearchCommand:
    def test_search_found(self, runner, populated_db_args):
        result = runner.invoke(cli, ["search", "analysis"])
        assert result.exit_code == 0
        assert "swot-analysis" in result.output or "requirements-analysis" in result.output

    def test_search_not_found(self, runner, populated_db_args):
        result = runner.invoke(cli, ["search", "xyznonexistent"])
        assert result.exit_code == 0
        assert "No prompts matching" in result.output

    def test_search_with_category(self, runner, populated_db_args):
        result = runner.invoke(cli, ["search", "review", "--category", "development"])
        assert result.exit_code == 0


class TestGetCommand:
    def test_get_found(self, runner, populated_db_args):
        result = runner.invoke(cli, ["get", "code-review"])
        assert result.exit_code == 0
        assert "Code Review Checklist" in result.output
        assert "development" in result.output

    def test_get_not_found(self, runner, populated_db_args):
        result = runner.invoke(cli, ["get", "nonexistent"])
        assert result.exit_code == 0
        assert "no prompt with ID" in result.output


class TestAddCommand:
    def test_add_valid(self, runner, db_connection, fixtures_dir, monkeypatch):
        import pl.database
        import pl.storage
        import pl.commands
        monkeypatch.setattr(pl.database, "get_connection", lambda db_path=None: db_connection)
        monkeypatch.setattr(pl.storage, "get_connection", lambda db_path=None: db_connection)
        monkeypatch.setattr(pl.commands, "get_connection", lambda db_path=None: db_connection)
        yaml_file = fixtures_dir / "development" / "code-review.yaml"
        result = runner.invoke(cli, ["add", str(yaml_file)])
        assert result.exit_code == 0
        assert "Added prompt" in result.output

    def test_add_duplicate(self, runner, populated_db_args, fixtures_dir):
        yaml_file = fixtures_dir / "development" / "code-review.yaml"
        result = runner.invoke(cli, ["add", str(yaml_file)])
        assert result.exit_code == 0
        assert "already exists" in result.output


class TestCategoriesCommand:
    def test_categories(self, runner, populated_db_args):
        result = runner.invoke(cli, ["categories"])
        assert result.exit_code == 0
        assert "development" in result.output
        assert "writing" in result.output
        assert "analysis" in result.output

    def test_categories_with_counts(self, runner, populated_db_args):
        result = runner.invoke(cli, ["categories"])
        assert "2 prompts" in result.output or "1 prompt" in result.output


class TestImportCommand:
    def test_import(self, runner, db_connection, fixtures_dir, monkeypatch):
        import pl.database
        import pl.storage
        import pl.commands
        monkeypatch.setattr(pl.database, "get_connection", lambda db_path=None: db_connection)
        monkeypatch.setattr(pl.storage, "get_connection", lambda db_path=None: db_connection)
        monkeypatch.setattr(pl.commands, "get_connection", lambda db_path=None: db_connection)
        result = runner.invoke(cli, ["import", "--dir", str(fixtures_dir)])
        assert result.exit_code == 0
        assert "Imported" in result.output
        assert "6" in result.output  # 6 fixture files


class TestExportCommand:
    def test_export(self, runner, populated_db_args, tmp_path):
        result = runner.invoke(cli, ["export", "--dir", str(tmp_path / "export")])
        assert result.exit_code == 0
        exported = list((tmp_path / "export").rglob("*.yaml"))
        assert len(exported) == 5


class TestInfoCommand:
    def test_info(self, runner, populated_db_args):
        result = runner.invoke(cli, ["info"])
        assert result.exit_code == 0
        assert "Total prompts" in result.output
        assert "Total fetches" in result.output


class TestOptimizeCommand:
    def test_optimize(self, runner, populated_db_args):
        result = runner.invoke(cli, ["optimize"])
        assert result.exit_code == 0
        assert "Optimization complete" in result.output


class TestIntegration:
    def test_smoke_test_sequence(self, runner, db_connection, fixtures_dir, tmp_path, monkeypatch):
        """Run a full workflow sequence: import -> search -> get -> list -> categories -> export."""
        import pl.database
        import pl.storage
        import pl.commands
        monkeypatch.setattr(pl.database, "get_connection", lambda db_path=None: db_connection)
        monkeypatch.setattr(pl.storage, "get_connection", lambda db_path=None: db_connection)
        monkeypatch.setattr(pl.commands, "get_connection", lambda db_path=None: db_connection)

        # Import
        r1 = runner.invoke(cli, ["import", "--dir", str(fixtures_dir)])
        assert r1.exit_code == 0

        # List
        r2 = runner.invoke(cli, ["list"])
        assert r2.exit_code == 0
        assert "code-review" in r2.output

        # Search
        r3 = runner.invoke(cli, ["search", "code"])
        assert r3.exit_code == 0

        # Get
        r4 = runner.invoke(cli, ["get", "code-review"])
        assert r4.exit_code == 0
        assert "Code Review Checklist" in r4.output

        # Categories
        r5 = runner.invoke(cli, ["categories"])
        assert r5.exit_code == 0

        # Export
        export_dir = tmp_path / "smoke-export"
        r6 = runner.invoke(cli, ["export", "--dir", str(export_dir)])
        assert r6.exit_code == 0
        assert export_dir.exists()

        # Info
        r7 = runner.invoke(cli, ["info"])
        assert r7.exit_code == 0
