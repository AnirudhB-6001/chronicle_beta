"""Tests for scripts/embed_and_index.py"""

import json
import os

from scripts.embed_and_index import (
    build_records,
    load_chunks,
    _stable_id,
    _guess_type,
    _iso,
    _clean_meta,
    _sanitize,
)


class TestSanitize:
    def test_none_gets_fallback(self):
        assert _sanitize(None) == "unknown"
        assert _sanitize(None, "default") == "default"

    def test_value_passes_through(self):
        assert _sanitize("hello") == "hello"
        assert _sanitize(42) == 42


class TestIso:
    def test_iso_string(self):
        result = _iso("2025-07-08")
        assert result.startswith("2025-07-08")

    def test_iso_with_z(self):
        result = _iso("2025-07-08T12:00:00Z")
        assert "2025-07-08" in result

    def test_epoch_timestamp(self):
        result = _iso(1720454400)
        assert "2024" in result or "2025" in result

    def test_empty(self):
        assert _iso("") == ""
        assert _iso(None) == ""


class TestGuessType:
    def test_python_file(self):
        assert _guess_type("", "script.py", "") == "code"

    def test_chat_title(self):
        assert _guess_type("My chat session", "", "") == "chat"

    def test_code_in_content(self):
        assert _guess_type("untitled", "", "def my_function():") == "code"

    def test_markdown_doc(self):
        assert _guess_type("readme.md", "", "") == "doc"

    def test_unknown(self):
        assert _guess_type("random", "", "just some text") == "unknown"


class TestCleanMeta:
    def test_removes_none(self):
        result = _clean_meta({"a": None, "b": "hello"})
        assert result["a"] == ""
        assert result["b"] == "hello"

    def test_converts_int_fields(self):
        result = _clean_meta({"chat_index": "5", "chunk_index": 3})
        assert result["chat_index"] == 5
        assert result["chunk_index"] == 3

    def test_stringifies_complex(self):
        result = _clean_meta({"data": [1, 2, 3]})
        assert isinstance(result["data"], str)


class TestStableId:
    def test_deterministic(self):
        id1 = _stable_id("orig", "text", "2025-01-01", "title", "path", 0, 0)
        id2 = _stable_id("orig", "text", "2025-01-01", "title", "path", 0, 0)
        assert id1 == id2

    def test_different_inputs_different_ids(self):
        id1 = _stable_id("a", "text1", "2025-01-01", "t1", "p1", 0, 0)
        id2 = _stable_id("b", "text2", "2025-01-02", "t2", "p2", 1, 1)
        assert id1 != id2


class TestBuildRecords:
    def test_output_lengths_match(self, sample_chunks):
        ids, docs, metas = build_records(sample_chunks)
        assert len(ids) == len(docs) == len(metas) == len(sample_chunks)

    def test_ids_unique(self, sample_chunks):
        ids, _, _ = build_records(sample_chunks)
        assert len(set(ids)) == len(ids)

    def test_no_none_in_metadata(self, sample_chunks):
        _, _, metas = build_records(sample_chunks)
        for m in metas:
            for k, v in m.items():
                assert v is not None, f"None found for key {k}"

    def test_metadata_has_required_fields(self, sample_chunks):
        _, _, metas = build_records(sample_chunks)
        required = {"title", "timestamp", "source", "type", "chat_index", "chunk_index"}
        for m in metas:
            assert required.issubset(m.keys()), f"Missing: {required - set(m.keys())}"

    def test_collision_suffix(self):
        chunk = {
            "text": "same text",
            "chat_title": "same",
            "timestamp": "2025-01-01",
            "chat_index": 0,
            "chunk_index": 0,
        }
        ids, _, _ = build_records([chunk, chunk])
        assert len(set(ids)) == 2


class TestLoadChunks:
    def test_loads_from_file(self, sample_chunks, tmp_dir):
        path = os.path.join(tmp_dir, "test.json")
        with open(path, "w") as f:
            json.dump(sample_chunks, f)
        loaded = load_chunks(path)
        assert len(loaded) == len(sample_chunks)

    def test_limit(self, sample_chunks, tmp_dir):
        path = os.path.join(tmp_dir, "test.json")
        with open(path, "w") as f:
            json.dump(sample_chunks, f)
        loaded = load_chunks(path, limit=2)
        assert len(loaded) == 2
