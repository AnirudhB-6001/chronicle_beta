"""
Chronicle Beta — Retrieve Chunks Tool

Bridges the MCP "retrieve_chunks" tool with Chronicle's retriever layer.
Handles multi-query retrieval, result mapping, deduplication, and merging.

Supports metadata filters and date windows passed through to retriever/core.py.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

_retriever_loaded = False
_search_fn: Optional[Callable[..., Any]] = None


# -----------------------------
# Lazy retriever loader
# -----------------------------
def _ensure_retriever():
    """Load the callable search function from retriever.core."""
    global _retriever_loaded, _search_fn
    if _retriever_loaded:
        return

    import importlib
    import os

    os.environ.setdefault("CHRONICLE_NONINTERACTIVE", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    try:
        core = importlib.import_module("retriever.core")
        fn = getattr(core, "search", None)
        if callable(fn):
            _search_fn = fn
    except Exception:
        pass

    _retriever_loaded = True


# -----------------------------
# Mapping utilities
# -----------------------------
def _iso(ts: Any) -> Optional[str]:
    """Best-effort ISO timestamp normalizer."""
    if not ts:
        return None
    if isinstance(ts, str):
        try:
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return ts
        except Exception:
            return ts
    if isinstance(ts, (int, float)):
        try:
            return datetime.utcfromtimestamp(float(ts)).isoformat() + "Z"
        except Exception:
            return None
    if isinstance(ts, datetime):
        return ts.isoformat()
    return None


def _guess_content_type(source_name: str, content: str) -> str:
    """Heuristic content type detection."""
    s = (source_name or "").lower()
    if s.endswith(".py") or "commit" in s:
        return "code"
    if any(tok in s for tok in ("chat", "thread", "slack", "conversation")):
        return "chat"
    if content and re.search(r"```|def |class |import ", content):
        return "code"
    if s.endswith((".md", ".txt", ".rst")) or any(tok in s for tok in ("note", "readme")):
        return "doc"
    return "unknown"


def _content_hash(source_name: str, source_anchor: Optional[str], content_raw: str) -> str:
    """SHA-256 hash for deduplication."""
    h = hashlib.sha256()
    h.update((source_name or "").encode("utf-8"))
    h.update((source_anchor or "").encode("utf-8"))
    h.update((content_raw or "").encode("utf-8"))
    return h.hexdigest()


def _normalize_score(score: Any) -> Optional[float]:
    """Clamp score to [0, 1]."""
    if score is None:
        return None
    try:
        v = float(score)
        return max(0.0, min(1.0, v))
    except Exception:
        return None


def _map_one_result(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Map a raw retriever result to the standardized chunk schema."""
    text = raw.get("text") or raw.get("body") or raw.get("content") or ""
    source_name = (
        raw.get("source")
        or raw.get("path")
        or raw.get("title")
        or "unknown"
    )
    source_anchor = raw.get("anchor") or raw.get("id") or None
    timestamp = raw.get("timestamp") or raw.get("time") or raw.get("date") or None
    author = raw.get("author") or raw.get("user") or None
    score = raw.get("score") or raw.get("similarity") or raw.get("relevance") or None

    meta = raw.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}

    ct = meta.get("type") or _guess_content_type(str(source_name), str(text))

    return {
        "source_name": source_name,
        "source_anchor": source_anchor,
        "timestamp": _iso(timestamp),
        "author": author or meta.get("author"),
        "relevance_score": _normalize_score(score),
        "content_raw": text,
        "content_type": ct,
        "is_confirmed_working": raw.get("is_confirmed_working"),
        "project": meta.get("project"),
        "path": meta.get("path"),
    }


# -----------------------------
# Retriever call
# -----------------------------
def _call_retriever(
    q: str,
    k: int,
    date_from: Optional[str],
    date_to: Optional[str],
    filters: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Call the underlying retriever with graceful signature fallback."""
    _ensure_retriever()

    if _search_fn is None:
        return []

    # Try full signature first, then degrade gracefully
    try:
        return _search_fn(q, k=k, date_from=date_from, date_to=date_to, filters=filters)
    except TypeError:
        try:
            return _search_fn(q, k=k, date_from=date_from, date_to=date_to)
        except TypeError:
            try:
                return _search_fn(q, k=k)
            except TypeError:
                return _search_fn(q)


# -----------------------------
# Merge + Dedup
# -----------------------------
def _dedupe(mapped: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicates by content hash."""
    seen = set()
    out = []
    for m in mapped:
        key = _content_hash(m.get("source_name"), m.get("source_anchor"), m.get("content_raw"))
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


def _merge_results(
    per_query_results: List[List[Dict[str, Any]]],
    per_query_limit: int,
) -> List[Dict[str, Any]]:
    """Interleave results from multiple queries, then deduplicate."""
    merged: List[Dict[str, Any]] = []
    max_rounds = max((len(lst) for lst in per_query_results), default=0)
    cap = per_query_limit * max(1, len(per_query_results))

    for i in range(max_rounds):
        for lst in per_query_results:
            if i < len(lst) and len(merged) < cap:
                merged.append(lst[i])

    return _dedupe(merged)


# -----------------------------
# Public API
# -----------------------------
def retrieve_chunks(
    retrieval_query: Any,
    k: int = 8,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Main entry point called by the MCP server.

    Accepts a single query string or list of queries.
    Returns standardized chunks with metadata.
    """
    # Normalize input
    if isinstance(retrieval_query, str):
        queries = [retrieval_query]
    elif isinstance(retrieval_query, list):
        queries = [q for q in retrieval_query if isinstance(q, str) and q.strip()]
    else:
        queries = []

    if not queries:
        return {"chunks": [], "meta": {"strategy": "no_queries"}}

    # Run retrieval for each query
    per_query_results = []
    for q in queries:
        raw_list = _call_retriever(q, k=k, date_from=date_from, date_to=date_to, filters=filters)
        mapped = [_map_one_result(r) for r in (raw_list or [])]
        per_query_results.append(mapped)

    # Merge and sort
    merged = _merge_results(per_query_results, per_query_limit=k)
    merged_sorted = sorted(
        merged,
        key=lambda m: (-float(m.get("relevance_score") or 0), m.get("timestamp") or ""),
    )

    return {
        "chunks": merged_sorted,
        "meta": {
            "queries": queries,
            "k_per_query": k,
            "total_after_merge": len(merged_sorted),
            "retriever": "chronicle",
            "mode": "callable" if _search_fn else "unavailable",
            "filters": filters or {},
            "date_from": date_from,
            "date_to": date_to,
        },
    }
