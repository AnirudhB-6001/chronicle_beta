# Evaluation Pipeline

## Overview

Chronicle Beta's eval pipeline measures retrieval quality against a golden dataset
of question-answer pairs with known ground-truth chunks.

## Metrics

- **Precision@k**: Of the k results returned, how many are relevant?
- **Recall@k**: Of all relevant chunks, how many appear in the top k?
- **MRR (Mean Reciprocal Rank)**: How high does the first relevant result rank?
- **NDCG (Normalized Discounted Cumulative Gain)**: Quality-weighted ranking score.

## Dataset Format

`eval/golden_questions.json`:
```json
[
  {
    "id": "q001",
    "query": "What embedding model does Chronicle use?",
    "expected_chunks": ["chunk_id_1", "chunk_id_2"],
    "expected_answer_contains": ["all-MiniLM-L6-v2", "sentence-transformers"],
    "category": "factual",
    "difficulty": "easy"
  }
]
```

## Running Evals

```bash
# Full eval suite
python -m eval.run_eval --dataset eval/golden_questions.json

# Specific category
python -m eval.run_eval --dataset eval/golden_questions.json --category temporal

# Output report
python -m eval.run_eval --dataset eval/golden_questions.json --report eval/reports/
```

## Adding Test Cases

See `eval/golden_questions.json` for the format. Categories:
- `factual` — direct fact retrieval
- `temporal` — time-based queries ("what was I doing in October?")
- `semantic` — conceptual similarity ("projects related to privacy")
- `multi-hop` — requires combining multiple chunks
- `negative` — queries that should return no relevant results
