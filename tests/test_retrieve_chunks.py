"""Tests for mcp_server/tools/retrieve_chunks.py"""

from mcp_server.tools.retrieve_chunks import (
    retrieve_chunks,
    _map_one_result,
    _dedupe,
    _merge_results,
    _normalize_score,
    _content_hash,
    _guess_content_type,
)


class TestNormalizeScore:
    def test_none(self):
        assert _normalize_score(None) is None

    def test_normal_range(self):
        assert _normalize_score(0.5) == 0.5

    def test_clamps_high(self):
        assert _normalize_score(1.5) == 1.0

    def test_clamps_low(self):
        assert _normalize_score(-0.3) == 0.0

    def test_string_input(self):
        assert _normalize_score("not a number") is None


class TestGuessContentType:
    def test_python_source(self):
        assert _guess_content_type("module.py", "") == "code"

    def test_chat(self):
        assert _guess_content_type("slack conversation", "") == "chat"

    def test_code_in_content(self):
        assert _guess_content_type("untitled", "```python\ndef foo():\n```") == "code"

    def test_doc(self):
        assert _guess_content_type("readme.md", "") == "doc"


class TestContentHash:
    def test_deterministic(self):
        h1 = _content_hash("src", "anchor", "content")
        h2 = _content_hash("src", "anchor", "content")
        assert h1 == h2

    def test_different_inputs(self):
        h1 = _content_hash("a", "b", "c")
        h2 = _content_hash("x", "y", "z")
        assert h1 != h2


class TestMapOneResult:
    def test_basic_mapping(self):
        raw = {
            "text": "hello world",
            "source": "test_source",
            "title": "Test",
            "date": "2025-01-01",
            "score": 0.85,
            "metadata": {"type": "chat", "project": "TestProject"},
        }
        mapped = _map_one_result(raw)
        assert mapped["content_raw"] == "hello world"
        assert mapped["source_name"] == "test_source"
        assert mapped["relevance_score"] == 0.85
        assert mapped["content_type"] == "chat"
        assert mapped["project"] == "TestProject"

    def test_handles_missing_fields(self):
        mapped = _map_one_result({})
        assert mapped["content_raw"] == ""
        assert mapped["source_name"] == "unknown"
        assert mapped["relevance_score"] is None

    def test_metadata_type_overrides_guess(self):
        raw = {
            "text": "def foo(): pass",
            "source": "some_chat",
            "metadata": {"type": "doc"},
        }
        mapped = _map_one_result(raw)
        assert mapped["content_type"] == "doc"


class TestDedupe:
    def test_removes_duplicates(self):
        items = [
            {"source_name": "a", "source_anchor": None, "content_raw": "same"},
            {"source_name": "a", "source_anchor": None, "content_raw": "same"},
            {"source_name": "b", "source_anchor": None, "content_raw": "different"},
        ]
        result = _dedupe(items)
        assert len(result) == 2

    def test_preserves_order(self):
        items = [
            {"source_name": "first", "source_anchor": None, "content_raw": "a"},
            {"source_name": "second", "source_anchor": None, "content_raw": "b"},
        ]
        result = _dedupe(items)
        assert result[0]["source_name"] == "first"


class TestMergeResults:
    def test_interleaves(self):
        q1 = [{"source_name": "a1", "source_anchor": None, "content_raw": "x1"}]
        q2 = [{"source_name": "b1", "source_anchor": None, "content_raw": "y1"}]
        merged = _merge_results([q1, q2], per_query_limit=5)
        names = [m["source_name"] for m in merged]
        assert "a1" in names and "b1" in names

    def test_dedupes_across_queries(self):
        item = {"source_name": "same", "source_anchor": None, "content_raw": "same"}
        merged = _merge_results([[item], [item]], per_query_limit=5)
        assert len(merged) == 1


class TestRetrieveChunks:
    def test_empty_query(self):
        result = retrieve_chunks("", k=3)
        assert result["chunks"] == []
        assert "meta" in result

    def test_empty_list_query(self):
        result = retrieve_chunks([], k=3)
        assert result["chunks"] == []

    def test_with_configured_retriever(self, configured_retriever):
        import mcp_server.tools.retrieve_chunks as rc_mod
        rc_mod._search_fn = configured_retriever.search
        rc_mod._retriever_loaded = True

        result = retrieve_chunks("python debugging", k=3)
        assert len(result["chunks"]) > 0
        assert result["meta"]["mode"] == "callable"

    def test_multi_query(self, configured_retriever):
        import mcp_server.tools.retrieve_chunks as rc_mod
        rc_mod._search_fn = configured_retriever.search
        rc_mod._retriever_loaded = True

        result = retrieve_chunks(["battery", "architecture"], k=3)
        assert result["meta"]["queries"] == ["battery", "architecture"]
        assert len(result["chunks"]) > 0

    def test_chunks_sorted_by_score(self, configured_retriever):
        import mcp_server.tools.retrieve_chunks as rc_mod
        rc_mod._search_fn = configured_retriever.search
        rc_mod._retriever_loaded = True

        result = retrieve_chunks("test query", k=5)
        scores = [c.get("relevance_score", 0) or 0 for c in result["chunks"]]
        assert scores == sorted(scores, reverse=True)

    def test_meta_includes_filters(self, configured_retriever):
        import mcp_server.tools.retrieve_chunks as rc_mod
        rc_mod._search_fn = configured_retriever.search
        rc_mod._retriever_loaded = True

        result = retrieve_chunks("test", k=3, date_from="2024-01-01", filters={"type": "chat"})
        assert result["meta"]["date_from"] == "2024-01-01"
        assert result["meta"]["filters"] == {"type": "chat"}
