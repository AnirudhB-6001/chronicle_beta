"""
Chronicle Beta - Test Configuration
Shared fixtures for all test modules.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["CHRONICLE_NONINTERACTIVE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"


@pytest.fixture
def fixture_path():
    return str(Path(__file__).parent / "fixtures" / "sample_conversations.json")


@pytest.fixture
def sample_conversations(fixture_path):
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sample_chunks(sample_conversations):
    from scripts.parser import process_conversations
    return process_conversations(sample_conversations, chunk_size=1000)


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp(prefix="chronicle_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def indexed_db(sample_chunks, tmp_dir):
    from scripts.embed_and_index import load_chunks, build_records
    from sentence_transformers import SentenceTransformer
    import chromadb

    chunks_path = os.path.join(tmp_dir, "chunks.json")
    with open(chunks_path, "w", encoding="utf-8") as f:
        json.dump(sample_chunks, f, ensure_ascii=False)

    loaded = load_chunks(chunks_path)
    ids, docs, metas = build_records(loaded)

    db_path = os.path.join(tmp_dir, "vector_store")
    collection_name = "test_collection"

    model = SentenceTransformer("all-MiniLM-L6-v2")
    client = chromadb.PersistentClient(path=db_path)
    coll = client.create_collection(collection_name)
    embs = model.encode(docs)
    coll.add(documents=docs, embeddings=embs, metadatas=metas, ids=ids)

    return db_path, collection_name


@pytest.fixture
def configured_retriever(indexed_db):
    import retriever.core as core

    db_path, collection_name = indexed_db
    core.DB_PATH = db_path
    core.COLLECTION_NAME = collection_name
    core._client = None
    core._collection = None
    core._model = None

    yield core

    core._client = None
    core._collection = None
    core._model = None
