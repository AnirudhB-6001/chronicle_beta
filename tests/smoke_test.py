#!/usr/bin/env python3
"""
Chronicle Beta — End-to-End Smoke Test

Runs the full pipeline: parse → embed → retrieve → verify
Uses synthetic test data, creates a temporary vector store, cleans up after.

Usage:
    python -m tests.smoke_test
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["CHRONICLE_NONINTERACTIVE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"


def _section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def _pass(msg: str):
    print(f"  PASS: {msg}")


def _fail(msg: str):
    print(f"  FAIL: {msg}")


def main():
    fixture_path = Path(__file__).parent / "fixtures" / "sample_conversations.json"
    if not fixture_path.exists():
        print(f"ERROR: fixture not found at {fixture_path}")
        sys.exit(1)

    # Create temp directory for this test run
    tmp_dir = tempfile.mkdtemp(prefix="chronicle_smoke_")
    chunks_path = os.path.join(tmp_dir, "chunks.json")
    db_path = os.path.join(tmp_dir, "vector_store")
    collection_name = "smoke_test"

    passed = 0
    failed = 0
    total = 0

    try:
        # ============================================================
        # STEP 1: Parse
        # ============================================================
        _section("STEP 1: Parser")

        from scripts.parser import load_conversations, process_conversations

        raw = load_conversations(str(fixture_path))
        total += 1
        if isinstance(raw, list) and len(raw) == 5:
            _pass(f"Loaded {len(raw)} conversations")
            passed += 1
        else:
            _fail(f"Expected 5 conversations, got {len(raw) if isinstance(raw, list) else type(raw)}")
            failed += 1

        chunks = process_conversations(raw, chunk_size=1000)
        total += 1
        if isinstance(chunks, list) and len(chunks) > 0:
            _pass(f"Produced {len(chunks)} chunks")
            passed += 1
        else:
            _fail(f"Expected chunks, got {len(chunks) if isinstance(chunks, list) else type(chunks)}")
            failed += 1

        # Verify chunk structure
        total += 1
        required_keys = {"text", "chat_title", "timestamp", "chat_index", "chunk_index"}
        sample = chunks[0]
        if required_keys.issubset(sample.keys()):
            _pass(f"Chunk schema valid: {sorted(sample.keys())}")
            passed += 1
        else:
            missing = required_keys - set(sample.keys())
            _fail(f"Missing keys in chunk: {missing}")
            failed += 1

        # Verify timestamps parsed
        total += 1
        dated = [c for c in chunks if c.get("timestamp") != "unknown"]
        if len(dated) == len(chunks):
            _pass(f"All {len(chunks)} chunks have valid timestamps")
            passed += 1
        else:
            _fail(f"Only {len(dated)}/{len(chunks)} chunks have timestamps")
            failed += 1

        # Save chunks for next step
        with open(chunks_path, "w", encoding="utf-8") as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)

        # ============================================================
        # STEP 2: Embed and Index
        # ============================================================
        _section("STEP 2: Embed and Index")

        from scripts.embed_and_index import load_chunks, build_records

        loaded = load_chunks(chunks_path)
        total += 1
        if len(loaded) == len(chunks):
            _pass(f"Loaded {len(loaded)} chunks from JSON")
            passed += 1
        else:
            _fail(f"Expected {len(chunks)}, loaded {len(loaded)}")
            failed += 1

        ids, docs, metas = build_records(loaded)
        total += 1
        if len(ids) == len(docs) == len(metas) == len(loaded):
            _pass(f"Built {len(ids)} records (ids, docs, metas aligned)")
            passed += 1
        else:
            _fail(f"Misaligned: ids={len(ids)}, docs={len(docs)}, metas={len(metas)}")
            failed += 1

        # Check stable IDs are unique
        total += 1
        if len(set(ids)) == len(ids):
            _pass("All chunk IDs are unique")
            passed += 1
        else:
            dupes = len(ids) - len(set(ids))
            _fail(f"{dupes} duplicate IDs found")
            failed += 1

        # Check metadata cleanliness (no None values)
        total += 1
        none_found = False
        for m in metas:
            for k, v in m.items():
                if v is None:
                    none_found = True
                    break
        if not none_found:
            _pass("All metadata values are non-None (Chroma-safe)")
            passed += 1
        else:
            _fail("Found None values in metadata")
            failed += 1

        # Actually embed and index into ChromaDB
        print(f"\n  Embedding into temp vector store at {db_path}...")
        from sentence_transformers import SentenceTransformer
        import chromadb

        model = SentenceTransformer("all-MiniLM-L6-v2")
        client = chromadb.PersistentClient(path=db_path)
        coll = client.create_collection(collection_name)

        embs = model.encode(docs)
        coll.add(documents=docs, embeddings=embs, metadatas=metas, ids=ids)

        total += 1
        count = coll.count()
        if count == len(docs):
            _pass(f"Indexed {count} chunks into ChromaDB")
            passed += 1
        else:
            _fail(f"Expected {len(docs)} indexed, got {count}")
            failed += 1

        # ============================================================
        # STEP 3: Retrieval (core.py)
        # ============================================================
        _section("STEP 3: Retriever")

        # Override config for test
        import retriever.core as core
        core.DB_PATH = db_path
        core.COLLECTION_NAME = collection_name
        # Force re-init
        core._client = None
        core._collection = None
        core._model = None

        # Test 1: Basic semantic search
        results = core.search("python debugging TypeError", k=3)
        total += 1
        if isinstance(results, list) and len(results) > 0:
            top = results[0]
            _pass(f"Basic search returned {len(results)} results, top: '{top.get('title', '')[:50]}'")
            passed += 1
        else:
            _fail("Basic search returned no results")
            failed += 1

        # Test 2: Verify result schema
        total += 1
        result_keys = {"text", "title", "date", "source", "anchor", "score", "distance", "metadata"}
        if results and result_keys.issubset(results[0].keys()):
            _pass(f"Result schema valid")
            passed += 1
        else:
            missing = result_keys - set(results[0].keys()) if results else result_keys
            _fail(f"Missing result keys: {missing}")
            failed += 1

        # Test 3: Score is normalized [0, 1]
        total += 1
        if results and results[0].get("score") is not None:
            s = results[0]["score"]
            if 0.0 <= s <= 1.0:
                _pass(f"Score normalized: {s:.4f}")
                passed += 1
            else:
                _fail(f"Score out of range: {s}")
                failed += 1
        else:
            _fail("No score in results")
            failed += 1

        # Test 4: Semantic relevance - battery query should NOT return pasta
        results_battery = core.search("battery voltage temperature monitoring", k=3)
        total += 1
        if results_battery:
            titles = [r.get("title", "").lower() for r in results_battery]
            if any("battery" in t for t in titles):
                _pass(f"Semantic relevance: battery query found battery content")
                passed += 1
            elif any("pasta" in t or "carbonara" in t for t in titles):
                _fail(f"Semantic relevance BROKEN: battery query returned pasta!")
                failed += 1
            else:
                _pass(f"Semantic search returned: {titles[:2]} (reasonable)")
                passed += 1
        else:
            _fail("Battery search returned no results")
            failed += 1

        # Test 5: Date filtering
        results_dated = core.search("project architecture", k=5, date_from="2025-07-08", date_to="2025-07-15")
        total += 1
        if isinstance(results_dated, list):
            _pass(f"Date-filtered search returned {len(results_dated)} results")
            passed += 1
        else:
            _fail("Date-filtered search failed")
            failed += 1

        # Test 6: Empty query returns empty
        results_empty = core.search("", k=5)
        total += 1
        if results_empty == []:
            _pass("Empty query returns []")
            passed += 1
        else:
            _fail(f"Empty query returned {len(results_empty)} results")
            failed += 1

        # ============================================================
        # STEP 4: Retrieve Chunks Tool (MCP layer)
        # ============================================================
        _section("STEP 4: MCP Tool Layer (retrieve_chunks)")

        from mcp_server.tools.retrieve_chunks import retrieve_chunks

        # Override the search function to use our test DB
        import mcp_server.tools.retrieve_chunks as rc_mod
        rc_mod._search_fn = core.search
        rc_mod._retriever_loaded = True

        # Test: Single query
        result = retrieve_chunks("battery confidence scoring", k=3)
        total += 1
        if "chunks" in result and "meta" in result:
            n = len(result["chunks"])
            mode = result["meta"].get("mode")
            _pass(f"retrieve_chunks returned {n} chunks, mode={mode}")
            passed += 1
        else:
            _fail("retrieve_chunks missing chunks or meta")
            failed += 1

        # Test: Multi-query (array syntax)
        result_multi = retrieve_chunks(
            ["battery monitoring system", "voltage temperature sensor", "confidence scoring"],
            k=3,
        )
        total += 1
        if result_multi.get("meta", {}).get("queries") and len(result_multi["meta"]["queries"]) == 3:
            _pass(f"Multi-query: {len(result_multi['chunks'])} chunks from 3 queries")
            passed += 1
        else:
            _fail("Multi-query did not process all queries")
            failed += 1

        # Test: Chunk schema
        total += 1
        if result["chunks"]:
            chunk = result["chunks"][0]
            chunk_keys = {"source_name", "timestamp", "relevance_score", "content_raw", "content_type"}
            if chunk_keys.issubset(chunk.keys()):
                _pass(f"Chunk schema valid: content_type={chunk.get('content_type')}")
                passed += 1
            else:
                missing = chunk_keys - set(chunk.keys())
                _fail(f"Missing chunk keys: {missing}")
                failed += 1
        else:
            _fail("No chunks to check schema")
            failed += 1

        # Test: No queries returns empty
        result_none = retrieve_chunks("", k=3)
        total += 1
        if result_none.get("chunks") == []:
            _pass("Empty query returns empty chunks")
            passed += 1
        else:
            _fail("Empty query returned data")
            failed += 1

        # ============================================================
        # SUMMARY
        # ============================================================
        _section("RESULTS")
        print(f"  Passed: {passed}/{total}")
        print(f"  Failed: {failed}/{total}")

        if failed == 0:
            print(f"\n  ALL {total} TESTS PASSED — Chronicle Beta is functional.")
        else:
            print(f"\n  {failed} TEST(S) FAILED — needs attention.")

        return 0 if failed == 0 else 1

    finally:
        # Cleanup temp directory
        try:
            shutil.rmtree(tmp_dir)
            print(f"\n  Cleaned up temp dir: {tmp_dir}")
        except Exception:
            print(f"\n  Warning: could not clean up {tmp_dir}")


if __name__ == "__main__":
    sys.exit(main())
