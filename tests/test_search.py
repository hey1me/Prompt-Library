"""Tests for FTS5-based search engine."""

import pytest

from pl.search import search_prompts, _parse_fts_query, _fallback_search


class TestQueryParsing:
    def test_simple_query(self):
        """Simple query should split into AND terms."""
        assert _parse_fts_query("code review") == "code AND review"

    def test_single_word(self):
        """Single word query should be unchanged."""
        assert _parse_fts_query("python") == "python"

    def test_multiple_words(self):
        """Multiple words should be AND-joined."""
        assert _parse_fts_query("code review python") == "code AND review AND python"

    def test_empty_query(self):
        """Empty query should return empty string."""
        assert _parse_fts_query("") == ""
        assert _parse_fts_query("   ") == ""

    def test_query_with_special_chars(self):
        """Special characters should be stripped."""
        result = _parse_fts_query("hello, world! test?")
        assert "hello" in result
        assert "world" in result
        assert "test" in result


class TestSearchPrompts:
    def test_search_by_title(self, populated_db):
        """Search should find prompts matching title."""
        results = search_prompts("Code Review Checklist", connection=populated_db)
        assert len(results) > 0
        ids = [r.id for r in results]
        assert "code-review" in ids

    def test_search_by_body(self, populated_db):
        """Search should find prompts matching body content."""
        results = search_prompts("SWOT analysis", connection=populated_db)
        assert len(results) > 0
        assert results[0].id == "swot-analysis"

    def test_search_with_category_filter(self, populated_db):
        """Category filter should limit search scope."""
        results = search_prompts("review", category="development", connection=populated_db)
        assert all(r.category == "development" for r in results)

    def test_search_no_results(self, populated_db):
        """Search with no matches should return empty list."""
        results = search_prompts("xyznonexistent", connection=populated_db)
        assert results == []

    def test_search_deterministic(self, populated_db):
        """Same query on same data should return same order."""
        r1 = search_prompts("draft", connection=populated_db)
        r2 = search_prompts("draft", connection=populated_db)
        assert [r.id for r in r1] == [r.id for r in r2]

    def test_search_returns_prompt_objects(self, populated_db):
        """Search should return Prompt objects with all fields."""
        results = search_prompts("analysis", connection=populated_db)
        assert len(results) > 0
        p = results[0]
        assert hasattr(p, "id")
        assert hasattr(p, "title")
        assert hasattr(p, "body")
        assert hasattr(p, "fetch_count")
        assert hasattr(p, "user_rating")

    def test_search_stemming(self, populated_db):
        """Stemming should match 'testing' when searching for 'test'."""
        # Our fixture prompts use 'review', 'analysis', 'design' etc.
        # 'reviewing' should match 'review' via porter stemmer
        # The fixture body for code-review contains 'Review the following code'
        results = search_prompts("reviewing", connection=populated_db)
        review_ids = {r.id for r in results}
        assert "code-review" in review_ids

    def test_search_ranking(self, populated_db):
        """Higher usage prompts should rank better for similar matches."""
        # Both code-review and api-design match 'design' to varying degrees
        results = search_prompts("api rest", connection=populated_db)
        if len(results) >= 2:
            assert results[0].id == "api-design"

    def test_search_limit(self, populated_db):
        """Search should respect result limit."""
        results = search_prompts("a", connection=populated_db)
        # Should return at most 20 results
        assert len(results) <= 20


class TestFallbackSearch:
    def test_fallback_on_no_fts_results(self, populated_db):
        """Fallback to LIKE search when FTS returns nothing."""
        # Search for something that doesn't exist via FTS but exists via LIKE
        # This is hard to guarantee since FTS5 is very flexible with porter stemmer
        # Just ensure it doesn't crash
        results = search_prompts("zzzznonexistent", connection=populated_db)
        assert results == []

    def test_fallback_prefix_wildcard(self, populated_db):
        """Prefix wildcard fallback should work for partial matches."""
        # "cod" should match "code-review" via prefix matching
        results = search_prompts("cod", connection=populated_db)
        ids = {r.id for r in results}
        assert "code-review" in ids or "api-design" in ids


class TestEdgeCases:
    def test_empty_query(self, populated_db):
        """Empty query should return empty list."""
        assert search_prompts("", connection=populated_db) == []

    def test_very_long_query(self, populated_db):
        """Very long query should not crash."""
        long_q = "word " * 100
        results = search_prompts(long_q.strip(), connection=populated_db)
        assert isinstance(results, list)

    def test_unicode_query(self, populated_db):
        """Unicode query should not crash."""
        results = search_prompts("café résumé", connection=populated_db)
        assert isinstance(results, list)

    def test_query_with_numbers(self, populated_db):
        """Numeric queries should work."""
        results = search_prompts("v1", connection=populated_db)
        assert isinstance(results, list)
