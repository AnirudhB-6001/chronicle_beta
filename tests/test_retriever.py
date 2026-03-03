"""Tests for retriever/core.py"""


class TestSearch:
    def test_basic_search(self, configured_retriever):
        results = configured_retriever.search("python debugging", k=3)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_result_schema(self, configured_retriever):
        results = configured_retriever.search("battery monitoring", k=3)
        required = {"text", "title", "date", "source", "anchor", "score", "distance", "metadata"}
        for r in results:
            assert required.issubset(r.keys()), f"Missing: {required - set(r.keys())}"

    def test_score_normalized(self, configured_retriever):
        results = configured_retriever.search("architecture", k=3)
        for r in results:
            if r["score"] is not None:
                assert 0.0 <= r["score"] <= 1.0, f"Score out of range: {r['score']}"

    def test_respects_k(self, configured_retriever):
        r1 = configured_retriever.search("test", k=1)
        r3 = configured_retriever.search("test", k=3)
        assert len(r1) <= 1
        assert len(r3) <= 3

    def test_empty_query_returns_empty(self, configured_retriever):
        assert configured_retriever.search("", k=5) == []
        assert configured_retriever.search("   ", k=5) == []

    def test_date_filter_narrows_results(self, configured_retriever):
        all_results = configured_retriever.search("architecture", k=10)
        dated = configured_retriever.search(
            "architecture", k=10,
            date_from="2024-07-08", date_to="2024-07-09",
        )
        assert len(dated) <= len(all_results)

    def test_metadata_filter(self, configured_retriever):
        results = configured_retriever.search(
            "test", k=10,
            filters={"type": "chat"},
        )
        # Should only return chat-typed results
        for r in results:
            meta = r.get("metadata", {})
            assert "chat" in (meta.get("type", "") or "").lower()

    def test_semantic_relevance(self, configured_retriever):
        results = configured_retriever.search("battery voltage temperature", k=3)
        titles = [r.get("title", "").lower() for r in results]
        assert any("battery" in t for t in titles), f"Expected battery content, got: {titles}"

    def test_nonexistent_content(self, configured_retriever):
        results = configured_retriever.search("quantum computing blockchain", k=3)
        # Should return something (no empty), but content won't match
        assert isinstance(results, list)


class TestDistanceToScore:
    def test_import(self):
        from retriever.core import _distance_to_score
        assert callable(_distance_to_score)

    def test_none_input(self):
        from retriever.core import _distance_to_score
        assert _distance_to_score(None) is None

    def test_string_input(self):
        from retriever.core import _distance_to_score
        assert _distance_to_score("not a number") is None

    def test_zero_distance_high_score(self):
        from retriever.core import _distance_to_score
        score = _distance_to_score(0.0)
        assert score is not None
        assert score >= 0.9  # 0 distance = very high score

    def test_large_distance_low_score(self):
        from retriever.core import _distance_to_score
        score = _distance_to_score(100.0)
        assert score is not None
        assert score < 0.1


class TestApplyFilters:
    def test_no_filters_passthrough(self):
        from retriever.core import _apply_filters
        rows = [{"metadata": {"type": "chat"}}, {"metadata": {"type": "code"}}]
        assert len(_apply_filters(rows, {})) == 2

    def test_type_filter(self):
        from retriever.core import _apply_filters
        rows = [
            {"metadata": {"type": "chat"}},
            {"metadata": {"type": "code"}},
            {"metadata": {"type": "chat"}},
        ]
        result = _apply_filters(rows, {"type": "chat"})
        assert len(result) == 2

    def test_case_insensitive(self):
        from retriever.core import _apply_filters
        rows = [{"metadata": {"project": "Chronicle Beta"}}]
        result = _apply_filters(rows, {"project": "chronicle"})
        assert len(result) == 1
