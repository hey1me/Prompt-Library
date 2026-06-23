"""Tests for SQLite-backed storage layer."""

import json
from pathlib import Path

import pytest

from pl.models import Prompt, Variable
from pl.storage import (
    add_prompt,
    delete_prompt,
    export_yaml,
    get_categories,
    get_info,
    get_prompt,
    import_yaml,
    increment_fetch,
    init_db,
    list_prompts,
    optimize,
    search,
    update_prompt,
)


class TestInitDB:
    def test_init_db_creates_schema(self, db_connection):
        """init_db should be idempotent and create required tables."""
        # db_connection already calls init_db via conftest
        conn = db_connection
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='prompts'"
        ).fetchone()
        assert tables is not None


class TestCRUD:
    def test_add_and_get_prompt(self, db_connection, sample_prompt):
        """Adding a prompt and retrieving it should return matching data."""
        add_prompt(sample_prompt, connection=db_connection)
        retrieved = get_prompt("test-prompt", connection=db_connection)
        assert retrieved is not None
        assert retrieved.id == "test-prompt"
        assert retrieved.title == "Test Prompt"
        assert retrieved.body == "This is a test prompt body with {{var1}} and {{var2}}."
        assert retrieved.fetch_count == 0
        assert retrieved.user_rating == 0.0

    def test_get_nonexistent(self, db_connection):
        """Getting a nonexistent prompt should return None."""
        assert get_prompt("nonexistent", connection=db_connection) is None

    def test_add_duplicate_id(self, db_connection, sample_prompt):
        """Adding a duplicate ID should raise FileExistsError."""
        add_prompt(sample_prompt, connection=db_connection)
        with pytest.raises(FileExistsError):
            add_prompt(sample_prompt, connection=db_connection)

    def test_update_prompt(self, db_connection, sample_prompt):
        """Updating a prompt should persist changes."""
        add_prompt(sample_prompt, connection=db_connection)
        update_prompt("test-prompt", {"title": "Updated Title", "fetch_count": 5}, connection=db_connection)
        updated = get_prompt("test-prompt", connection=db_connection)
        assert updated.title == "Updated Title"
        assert updated.fetch_count == 5
        # Unchanged fields should remain
        assert updated.category == "development"

    def test_update_nonexistent(self, db_connection):
        """Updating a nonexistent prompt should raise KeyError."""
        with pytest.raises(KeyError):
            update_prompt("nonexistent", {"title": "Nope"}, connection=db_connection)

    def test_delete_prompt(self, db_connection, sample_prompt):
        """Deleting a prompt should remove it."""
        add_prompt(sample_prompt, connection=db_connection)
        delete_prompt("test-prompt", connection=db_connection)
        assert get_prompt("test-prompt", connection=db_connection) is None

    def test_delete_nonexistent(self, db_connection):
        """Deleting a nonexistent prompt should raise KeyError."""
        with pytest.raises(KeyError):
            delete_prompt("nonexistent", connection=db_connection)

    def test_increment_fetch(self, db_connection, sample_prompt):
        """Incrementing fetch_count should increase it by 1."""
        add_prompt(sample_prompt, connection=db_connection)
        increment_fetch("test-prompt", connection=db_connection)
        assert get_prompt("test-prompt", connection=db_connection).fetch_count == 1
        increment_fetch("test-prompt", connection=db_connection)
        increment_fetch("test-prompt", connection=db_connection)
        assert get_prompt("test-prompt", connection=db_connection).fetch_count == 3

    def test_list_prompts(self, populated_db):
        """list_prompts should return all prompts."""
        prompts = list_prompts(connection=populated_db)
        assert len(prompts) == 5

    def test_list_prompts_by_category(self, populated_db):
        """list_prompts should filter by category."""
        dev = list_prompts(category="development", connection=populated_db)
        assert len(dev) == 2
        assert all(p.category == "development" for p in dev)
        writing = list_prompts(category="writing", connection=populated_db)
        assert len(writing) == 2

    def test_list_prompts_empty_category(self, populated_db):
        """list_prompts with nonexistent category should return empty list."""
        prompts = list_prompts(category="nonexistent", connection=populated_db)
        assert prompts == []


class TestSearch:
    def test_search_by_title(self, populated_db):
        """Search should find prompts by title content."""
        results = search("Code Review", connection=populated_db)
        assert len(results) >= 1
        assert any(r.id == "code-review" for r in results)

    def test_search_by_body(self, populated_db):
        """Search should find prompts by body content."""
        results = search("SWOT", connection=populated_db)
        assert len(results) >= 1
        assert results[0].id == "swot-analysis"

    def test_search_by_category(self, populated_db):
        """Search with category filter should narrow results."""
        results = search("review", category="development", connection=populated_db)
        assert all(r.category == "development" for r in results)

    def test_search_no_results(self, populated_db):
        """Search with no matches should return empty list."""
        results = search("xyznonexistent12345", connection=populated_db)
        assert results == []

    def test_search_ranking_usage_weight(self, populated_db):
        """Prompts with higher fetch_count/user_rating should rank higher."""
        # "review" appears in code-review (fetch=10, rating=4.5) and api-design (fetch=0, rating=0)
        results = search("review", connection=populated_db)
        if len(results) >= 2:
            # code-review (higher usage) should rank above api-design
            idx_cr = next(i for i, r in enumerate(results) if r.id == "code-review")
            idx_ad = next(i for i, r in enumerate(results) if r.id == "api-design")
            assert idx_cr < idx_ad

    def test_search_deterministic(self, populated_db):
        """Same search on same data should return same order."""
        r1 = search("draft", connection=populated_db)
        r2 = search("draft", connection=populated_db)
        assert [r.id for r in r1] == [r.id for r in r2]


class TestCategories:
    def test_get_categories(self, populated_db):
        """get_categories should return distinct categories with counts."""
        cats = get_categories(connection=populated_db)
        assert len(cats) == 3
        cat_names = {c["name"] for c in cats}
        assert cat_names == {"development", "writing", "analysis"}

    def test_categories_have_counts(self, populated_db):
        """Categories should include prompt count."""
        cats = get_categories(connection=populated_db)
        for c in cats:
            if c["name"] == "development":
                assert c["count"] == 2
            elif c["name"] == "writing":
                assert c["count"] == 2
            elif c["name"] == "analysis":
                assert c["count"] == 1


class TestImportExport:
    def test_import_yaml(self, db_connection, fixtures_dir):
        """Importing YAML files should populate the database."""
        count = import_yaml(fixtures_dir, connection=db_connection)
        assert count == 6  # All 6 fixture files
        assert get_prompt("code-review", connection=db_connection) is not None
        assert get_prompt("blog-post", connection=db_connection) is not None

    def test_import_yaml_skips_malformed(self, db_connection, tmp_path, caplog):
        """Malformed YAML files should be skipped with a warning."""
        # Create a malformed file
        bad_dir = tmp_path / "bad_prompts" / "test"
        bad_dir.mkdir(parents=True)
        (bad_dir / "bad.yaml").write_text("not: valid: yaml: [[[")
        count = import_yaml(tmp_path / "bad_prompts", connection=db_connection)
        assert count == 0  # 0 imported, but no crash

    def test_export_yaml(self, populated_db, tmp_path, fixtures_dir):
        """Export should write one YAML file per prompt."""
        export_dir = tmp_path / "export"
        export_yaml(export_dir, connection=populated_db)
        files = list(export_dir.rglob("*.yaml"))
        assert len(files) == 5

    def test_export_round_trip(self, db_connection, fixtures_dir, tmp_path):
        """YAML -> DB -> YAML should preserve data."""
        import_yaml(fixtures_dir, connection=db_connection)
        export_dir = tmp_path / "roundtrip"
        export_yaml(export_dir, connection=db_connection)
        exported_files = list(export_dir.rglob("*.yaml"))
        assert len(exported_files) == 6


class TestInfo:
    def test_get_info(self, populated_db, tmp_path):
        """get_info should return database statistics."""
        info = get_info(connection=populated_db)
        assert info["total_prompts"] == 5
        assert info["total_fetches"] == 25  # 10 + 5 + 2 + 0 + 8
        assert "db_size_bytes" in info

    def test_get_info_empty_db(self, db_connection):
        """Empty database should report zero counts."""
        info = get_info(connection=db_connection)
        assert info["total_prompts"] == 0
        assert info["total_fetches"] == 0
        assert "db_size_bytes" in info


class TestOptimize:
    def test_optimize_does_not_crash(self, populated_db):
        """optimize should run without errors."""
        optimize(connection=populated_db)
        # Verify DB is still usable
        prompts = list_prompts(connection=populated_db)
        assert len(prompts) == 5


class TestEdgeCases:
    def test_prompt_with_json_tags(self, db_connection):
        """Tags stored as JSON should parse correctly for special chars."""
        p = Prompt(
            id="special-tags",
            title="Special Tags",
            category="test",
            body="test",
            tags=["tag-with-dash", "tag_with_underscore", "tag.with.dot"],
        )
        add_prompt(p, connection=db_connection)
        retrieved = get_prompt("special-tags", connection=db_connection)
        assert retrieved.tags == ["tag-with-dash", "tag_with_underscore", "tag.with.dot"]

    def test_prompt_with_empty_variables(self, db_connection):
        """Variables should default to empty list."""
        p = Prompt(id="no-vars", title="No Vars", category="test", body="test")
        add_prompt(p, connection=db_connection)
        retrieved = get_prompt("no-vars", connection=db_connection)
        assert retrieved.variables == []
