"""
Chronicle Beta - Quick eval against existing vector store.
Runs golden_questions_real.json without rebuilding the index.

Usage:
    python -m eval.run_real_eval
"""

import os
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["CHRONICLE_NONINTERACTIVE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from eval.run_eval import precision_at_k, recall_at_k, reciprocal_rank, ndcg_at_k
from retriever.core import search


def main():
    dataset = "eval/golden_questions_real.json"
    if not Path(dataset).exists():
        print("ERROR: %s not found" % dataset)
        sys.exit(1)

    with open(dataset) as f:
        questions = json.load(f)

    print("Running %d questions against live vector store...\n" % len(questions))

    passed = 0
    total_mrr = 0.0
    total_cr = 0.0

    for q in questions:
        query = q.get("query_variants", q["query"])
        date_from = q.get("date_from")
        date_to = q.get("date_to")
        expected = set(q.get("expected_titles", []))
        content_terms = q.get("expected_content_contains", [])

        # Run retrieval
        if isinstance(query, list):
            all_titles = []
            all_text = ""
            for qv in query:
                results = search(qv, k=5, date_from=date_from, date_to=date_to)
                all_titles.extend([r.get("title", "") for r in results])
                all_text += " ".join(r.get("text", "") for r in results) + " "
        else:
            results = search(query, k=5, date_from=date_from, date_to=date_to)
            all_titles = [r.get("title", "") for r in results]
            all_text = " ".join(r.get("text", "") for r in results)

        # Content recall
        all_text_lower = all_text.lower()
        content_hits = sum(1 for t in content_terms if t.lower() in all_text_lower)
        cr = content_hits / len(content_terms) if content_terms else 1.0

        # MRR
        mrr = reciprocal_rank(all_titles, expected) if expected else 0.0

        # Pass/fail
        status = "PASS" if cr >= 0.5 else "WEAK"
        if not expected and not content_terms:
            status = "PASS"
        if status == "PASS":
            passed += 1

        total_mrr += mrr
        total_cr += cr

        top3 = [t[:50] for t in all_titles[:3]]
        print("  [%s] %s: MRR=%.2f  ContentRecall=%.2f  (%s/%s)" % (
            status, q["id"], mrr, cr, q["category"], q["difficulty"]))
        print("         Top 3: %s" % top3)

    n = len(questions)
    print("\n" + "=" * 60)
    print("  REAL DATA EVAL SUMMARY")
    print("=" * 60)
    print("  Passed: %d/%d" % (passed, n))
    print("  Avg MRR: %.4f" % (total_mrr / n))
    print("  Avg Content Recall: %.4f" % (total_cr / n))


if __name__ == "__main__":
    main()
