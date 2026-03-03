"""Tests for scripts/parser.py"""

import json
from pathlib import Path
from scripts.parser import load_conversations, process_conversations, chunk_text


class TestChunkText:
    def test_short_text_single_chunk(self):
        result = chunk_text("hello world", size=100)
        assert result == ["hello world"]

    def test_exact_boundary(self):
        result = chunk_text("abcde", size=5)
        assert result == ["abcde"]

    def test_splits_correctly(self):
        result = chunk_text("abcdefghij", size=3)
        assert result == ["abc", "def", "ghi", "j"]

    def test_empty_string(self):
        result = chunk_text("", size=100)
        assert result == []

    def test_custom_size(self):
        text = "a" * 2500
        result = chunk_text(text, size=500)
        assert len(result) == 5
        assert all(len(c) == 500 for c in result)


class TestLoadConversations:
    def test_loads_fixture(self, fixture_path):
        data = load_conversations(fixture_path)
        assert isinstance(data, list)
        assert len(data) == 5

    def test_first_conversation_has_title(self, fixture_path):
        data = load_conversations(fixture_path)
        assert data[0]["title"] == "Python debugging session"


class TestProcessConversations:
    def test_produces_chunks(self, sample_conversations):
        chunks = process_conversations(sample_conversations)
        assert isinstance(chunks, list)
        assert len(chunks) > 0

    def test_chunk_schema(self, sample_conversations):
        chunks = process_conversations(sample_conversations)
        required = {"text", "chat_title", "timestamp", "chat_index", "chunk_index"}
        for chunk in chunks:
            assert required.issubset(chunk.keys()), f"Missing keys: {required - set(chunk.keys())}"

    def test_timestamps_parsed(self, sample_conversations):
        chunks = process_conversations(sample_conversations)
        for chunk in chunks:
            assert chunk["timestamp"] != "unknown", f"Unparsed timestamp in {chunk['chat_title']}"

    def test_chat_index_sequential(self, sample_conversations):
        chunks = process_conversations(sample_conversations)
        indices = sorted(set(c["chat_index"] for c in chunks))
        assert indices == list(range(len(sample_conversations)))

    def test_custom_chunk_size(self, sample_conversations):
        small = process_conversations(sample_conversations, chunk_size=200)
        large = process_conversations(sample_conversations, chunk_size=5000)
        assert len(small) >= len(large)

    def test_no_empty_chunks(self, sample_conversations):
        chunks = process_conversations(sample_conversations)
        for chunk in chunks:
            assert chunk["text"].strip(), f"Empty chunk in {chunk['chat_title']}"

    def test_handles_dict_content_parts(self):
        data = [{
            "title": "Test",
            "mapping": {
                "n1": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": [{"text": "hello from dict"}]},
                        "create_time": 1700000000,
                    }
                }
            }
        }]
        chunks = process_conversations(data)
        assert any("hello from dict" in c["text"] for c in chunks)

    def test_handles_none_nodes(self):
        data = [{
            "title": "Test",
            "mapping": {
                "n1": None,
                "n2": {"message": None},
                "n3": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": ["valid"]},
                        "create_time": 1700000000,
                    }
                }
            }
        }]
        chunks = process_conversations(data)
        assert len(chunks) > 0
