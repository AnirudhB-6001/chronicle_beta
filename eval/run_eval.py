"""
Chronicle Beta — Evaluation Runner

Measures retrieval quality against a golden question dataset.
Computes industry-standard IR metrics: Precision@k, Recall@k, MRR, NDCG.

The eval ingests test data into a temp vector store, runs each golden question,
and compares retrieved results against expected matches.

Usage:
    python -m eval.run_eval
    python -m eval.run_eval --dataset eval/golden_questions.json --k 5
    python -m eval.run_eval --verbose
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["CHRONICLE_NONINTERACTIVE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"


# ============================================================
# Metrics
# ============================================================

def precision_at_k(retrieved_titles: List[str], relevant_titles: set, k: int) -> float:
    """Of the top-k retrieved, what fraction is relevant?"""
    top_k = retrieved_titles[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for t in top_k if t in relevant_titles)
    return hits / len(top_k)


def recall_at_k(retrieved_titles: List[str], relevant_titles: set, k: int) -> float:
    """Of all relevant docs, what fraction appears in top-k?"""
    if not relevant_titles:
        return 1.0  # vacuously true
    top_k = set(retrieved_titles[:k])
    hits = len(top_k & relevant_titles)
    return hits / len(relevant_titles)


def reciprocal_rank(retrieved_titles: List[str], relevant_titles: set) -> float:
    """1 / rank of the first relevant result. 0 if none found."""
    for i, t in enumerate(retrieved_titles):
        if t in relevant_titles:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(retrieved_titles: List[str], relevant_titles: set, k: int) -> float:
    """Normalized Discounted Cumulative Gain at k."""
    top_k = retrieved_titles[:k]

    # DCG: count each relevant title only once (handles duplicate chunks)
    dcg = 0.0
    seen_relevant: set = set()
    for i, t in enumerate(top_k):
        if t in relevant_titles and t not in seen_relevant:
            dcg += 1.0 / math.log2(i + 2)  # i+2 because log2(1) = 0
            seen_relevant.add(t)

    # Ideal DCG: all relevant docs at the top positions
    n_relevant = min(len(relevant_titles), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(n_relevant))

    if idcg == 0.0:
        return 1.0 if not relevant_titles else 0.0
    return min(1.0, dcg / idcg)


# ============================================================
# Test data setup
# ============================================================

def setup_test_index(fixture_path: str, tmp_dir: str) -> str:
    """Parse, embed, and index test data. Returns db_path."""
    from scripts.parser import load_conversations, process_conversations
    from scripts.embed_and_index import load_chunks, build_records
    from sentence_transformers import SentenceTransformer
    import chromadb

    # Parse
    raw = load_conversations(fixture_path)
    chunks = process_conversations(raw, chunk_size=1000)

    chunks_path = os.path.join(tmp_dir, "chunks.json")
    with open(chunks_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    # Build records
    loaded = load_chunks(chunks_path)
    ids, docs, metas = build_records(loaded)

    # Embed and index
    db_path = os.path.join(tmp_dir, "vector_store")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    client = chromadb.PersistentClient(path=db_path)
    coll = client.create_collection("eval_test")

    embs = model.encode(docs)
    coll.add(documents=docs, embeddings=embs, metadatas=metas, ids=ids)

    return db_path


def configure_retriever(db_path: str, collection: str = "eval_test"):
    """Point the retriever at the test index."""
    import retriever.core as core
    core.DB_PATH = db_path
    core.COLLECTION_NAME = collection
    core._client = None
    core._collection = None
    core._model = None


# ============================================================
# Eval runner
# ============================================================

def run_single_question(
    question: Dict[str, Any],
    k: int,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Run one golden question and compute metrics."""
    from mcp_server.tools.retrieve_chunks import retrieve_chunks
    import retriever.core as core
    import mcp_server.tools.retrieve_chunks as rc_mod

    # Ensure tool uses our retriever
    rc_mod._search_fn = core.search
    rc_mod._retriever_loaded = True

    query = question["query"]
    expected_titles = set(question.get("expected_titles", []))
    expected_content = question.get("expected_content_contains", [])
    category = question.get("category", "unknown")
    difficulty = question.get("difficulty", "unknown")

    # Build query (support both single string and array)
    query_input = question.get("query_variants", query)

    # Run retrieval
    result = retrieve_chunks(
        query_input,
        k=k,
        date_from=question.get("date_from"),
        date_to=question.get("date_to"),
        filters=question.get("filters"),
    )
    chunks = result.get("chunks", [])
    retrieved_titles = [c.get("source_name", "") for c in chunks]

    # Title-based metrics
    p_at_k = precision_at_k(retrieved_titles, expected_titles, k)
    r_at_k = recall_at_k(retrieved_titles, expected_titles, k)
    rr = reciprocal_rank(retrieved_titles, expected_titles)
    ndcg = ndcg_at_k(retrieved_titles, expected_titles, k)

    # Content-based check: do retrieved chunks contain expected strings?
    all_content = " ".join(c.get("content_raw", "") for c in chunks).lower()
    content_hits = sum(1 for term in expected_content if term.lower() in all_content)
    content_recall = content_hits / len(expected_content) if expected_content else 1.0

    result_dict = {
        "id": question.get("id", "?"),
        "query": query,
        "category": category,
        "difficulty": difficulty,
        "n_retrieved": len(chunks),
        "precision_at_k": round(p_at_k, 4),
        "recall_at_k": round(r_at_k, 4),
        "mrr": round(rr, 4),
        "ndcg_at_k": round(ndcg, 4),
        "content_recall": round(content_recall, 4),
    }

    if verbose:
        result_dict["retrieved_titles"] = retrieved_titles[:5]
        result_dict["expected_titles"] = list(expected_titles)

    return result_dict


def run_eval(
    dataset_path: str,
    fixture_path: str,
    k: int = 5,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Run the full eval suite."""

    # Load golden questions
    with open(dataset_path, "r", encoding="utf-8") as f:
        questions = json.load(f)

    if not questions:
        print("ERROR: No questions in dataset")
        return {}

    # Setup test index
    tmp_dir = tempfile.mkdtemp(prefix="chronicle_eval_")
    try:
        print(f"Setting up test index from {fixture_path}...")
        db_path = setup_test_index(fixture_path, tmp_dir)
        configure_retriever(db_path)

        print(f"Running {len(questions)} eval questions (k={k})...\n")

        results = []
        for q in questions:
            r = run_single_question(q, k=k, verbose=verbose)
            results.append(r)

            status = "PASS" if r["content_recall"] >= 0.5 else "WEAK"
            print(f"  [{status}] {r['id']}: P@{k}={r['precision_at_k']:.2f}  "
                  f"R@{k}={r['recall_at_k']:.2f}  MRR={r['mrr']:.2f}  "
                  f"NDCG={r['ndcg_at_k']:.2f}  ContentRecall={r['content_recall']:.2f}  "
                  f"({r['category']}/{r['difficulty']})")

            if verbose and r.get("retrieved_titles"):
                print(f"         Retrieved: {r['retrieved_titles'][:3]}")

        # Aggregate
        n = len(results)
        avg = lambda key: round(sum(r[key] for r in results) / n, 4) if n else 0.0

        summary = {
            "n_questions": n,
            "k": k,
            "avg_precision_at_k": avg("precision_at_k"),
            "avg_recall_at_k": avg("recall_at_k"),
            "avg_mrr": avg("mrr"),
            "avg_ndcg_at_k": avg("ndcg_at_k"),
            "avg_content_recall": avg("content_recall"),
        }

        # Per-category breakdown
        categories = set(r["category"] for r in results)
        by_category = {}
        for cat in sorted(categories):
            cat_results = [r for r in results if r["category"] == cat]
            cn = len(cat_results)
            by_category[cat] = {
                "n": cn,
                "avg_precision": round(sum(r["precision_at_k"] for r in cat_results) / cn, 4),
                "avg_mrr": round(sum(r["mrr"] for r in cat_results) / cn, 4),
                "avg_content_recall": round(sum(r["content_recall"] for r in cat_results) / cn, 4),
            }
        summary["by_category"] = by_category

        # Print summary
        print(f"\n{'='*60}")
        print(f"  EVAL SUMMARY (k={k}, n={n})")
        print(f"{'='*60}")
        print(f"  Avg Precision@{k}:    {summary['avg_precision_at_k']:.4f}")
        print(f"  Avg Recall@{k}:       {summary['avg_recall_at_k']:.4f}")
        print(f"  Avg MRR:              {summary['avg_mrr']:.4f}")
        print(f"  Avg NDCG@{k}:         {summary['avg_ndcg_at_k']:.4f}")
        print(f"  Avg Content Recall:   {summary['avg_content_recall']:.4f}")

        if by_category:
            print(f"\n  By Category:")
            for cat, stats in by_category.items():
                print(f"    {cat} (n={stats['n']}): "
                      f"P={stats['avg_precision']:.2f}  "
                      f"MRR={stats['avg_mrr']:.2f}  "
                      f"Content={stats['avg_content_recall']:.2f}")

        return {"summary": summary, "results": results}

    finally:
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass


# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Chronicle Beta — Eval Runner")
    p.add_argument(
        "--dataset", default="eval/golden_questions.json",
        help="Path to golden questions JSON.",
    )
    p.add_argument(
        "--fixture", default="tests/fixtures/sample_conversations.json",
        help="Path to test conversations for indexing.",
    )
    p.add_argument("--k", type=int, default=5, help="Top-k for metrics (default: 5).")
    p.add_argument("--verbose", action="store_true", help="Show retrieved titles per question.")
    p.add_argument(
        "--output", default=None,
        help="Save full results JSON to this path.",
    )
    return p.parse_args()


def main():
    args = parse_args()

    if not Path(args.dataset).exists():
        print(f"ERROR: dataset not found: {args.dataset}")
        sys.exit(1)
    if not Path(args.fixture).exists():
        print(f"ERROR: fixture not found: {args.fixture}")
        sys.exit(1)

    output = run_eval(
        dataset_path=args.dataset,
        fixture_path=args.fixture,
        k=args.k,
        verbose=args.verbose,
    )

    if args.output and output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"\n  Results saved to {args.output}")


if __name__ == "__main__":
    main()
