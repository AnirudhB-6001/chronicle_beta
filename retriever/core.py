"""
Chronicle Beta — Core Retriever

Pure, callable retriever with no CLI dependencies.
Provides vector search via ChromaDB with:
  - Date window filtering (inclusive)
  - Post-retrieval metadata filters (type, project, source, title, author, path)
  - TTL disk cache for repeated queries
  - Robust distance-to-score normalization across cosine/l2/ip spaces
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Quiet tokenizer fork warnings in WSL/subprocess
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import chromadb
from sentence_transformers import SentenceTransformer

# --- Configuration (overridable via environment) ---
DB_PATH = os.environ.get("CHRONICLE_DB_PATH", "data/vector_store")
COLLECTION_NAME = os.environ.get("CHRONICLE_COLLECTION", "chronicle_memory")
EMBEDDING_MODEL = os.environ.get("CHRONICLE_MODEL", "all-MiniLM-L6-v2")

# --- Singletons (loaded once per process) ---
_client: Optional[chromadb.ClientAPI] = None
_collection = None
_model: Optional[SentenceTransformer] = None

# --- Tiny TTL cache ---
try:
    from diskcache import Cache  # type: ignore
    _CACHE: Optional[Cache] = Cache(".cache")
except Exception:
    _CACHE = None


def _ensure_init() -> None:
    """Lazy-load Chroma client, collection, and embedding model once."""
    global _client, _collection, _model
    if _client is None:
        _client = chromadb.PersistentClient(path=DB_PATH)
    if _collection is None:
        _collection = _client.get_collection(name=COLLECTION_NAME)
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)


def _get_distance_space() -> str:
    """Detect Chroma HNSW space (cosine / l2 / ip). Defaults to 'l2'."""
    try:
        meta = getattr(_collection, "metadata", None)
        if isinstance(meta, dict):
            return str(meta.get("hnsw:space", "l2")).lower()
    except Exception:
        pass
    return "l2"


def _distance_to_score(dist: Any) -> Optional[float]:
    """
    Convert a Chroma distance to a normalized score in [0, 1].
    Higher is better. Works across cosine/l2/ip without assuming a specific range.
    """
    if not isinstance(dist, (int, float)):
        return None

    d = float(dist)
    space = _get_distance_space()

    if space == "cosine":
        # Cosine distance is in [0, 2] (0 best, 2 worst)
        s = 1.0 - (d / 2.0)
        return max(0.0, min(1.0, s))

    if space in ("ip", "inner_product", "dot"):
        s = 1.0 / (1.0 + max(0.0, d))
        return max(0.0, min(1.0, s))

    # L2 (or unknown): unbounded; use inverse transform
    s = 1.0 / (1.0 + max(0.0, d))
    return max(0.0, min(1.0, s))


def _iso_parse(ts: Any) -> Optional[datetime]:
    """Best-effort ISO timestamp parser. Returns None on failure."""
    if not ts:
        return None
    if isinstance(ts, str):
        s = ts.strip()
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            try:
                return datetime.fromisoformat(s + "T00:00:00")
            except Exception:
                return None
    if isinstance(ts, (int, float)):
        try:
            return datetime.utcfromtimestamp(float(ts))
        except Exception:
            return None
    if isinstance(ts, datetime):
        return ts
    return None


def _cache_get(key: Tuple) -> Optional[Any]:
    if _CACHE is None:
        return None
    try:
        return _CACHE.get(key)
    except Exception:
        return None


def _cache_set(key: Tuple, value: Any, expire: int = 60) -> None:
    if _CACHE is None:
        return
    try:
        _CACHE.set(key, value, expire=expire)
    except Exception:
        pass


def _vector_query(q: str, k: int) -> List[Dict[str, Any]]:
    """Run vector search and map to standard row shape."""
    _ensure_init()
    qvec = _model.encode([q])[0]  # type: ignore[index]
    res = _collection.query(
        query_embeddings=[qvec],
        n_results=int(max(1, k)),
        include=["documents", "metadatas", "distances"],
    )

    docs = res.get("documents") or [[]]
    metas = res.get("metadatas") or [[]]
    dists = res.get("distances") or [[]]

    out: List[Dict[str, Any]] = []
    D0 = dists[0] if (dists and dists[0]) else [None] * len(docs[0])

    for doc, meta, dist in zip(docs[0], metas[0], D0):
        meta = meta or {}
        title = (
            meta.get("title")
            or meta.get("source")
            or meta.get("path")
            or "untitled"
        )
        ts = meta.get("timestamp") or meta.get("date") or None
        anchor = meta.get("id") or meta.get("origin_id") or meta.get("line_range") or None
        score = _distance_to_score(dist)

        out.append({
            "text": doc or "",
            "title": title,
            "date": ts,
            "source": meta.get("source") or title,
            "anchor": anchor,
            "score": score,
            "distance": dist,
            "metadata": meta,
        })
    return out


def _match_filter_value(val: Any, needle: Any) -> bool:
    """Case-insensitive contains for strings, equality otherwise."""
    if needle is None:
        return True
    if isinstance(val, str) and isinstance(needle, str):
        return needle.lower() in val.lower()
    return str(val).lower() == str(needle).lower()


def _apply_filters(rows: List[Dict[str, Any]], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Apply post-retrieval metadata filters."""
    if not filters:
        return rows

    want_type = filters.get("type")
    want_proj = filters.get("project")
    want_source = filters.get("source")
    want_title = filters.get("title")
    want_author = filters.get("author")
    want_path = filters.get("path")

    out: List[Dict[str, Any]] = []
    for r in rows:
        m = r.get("metadata") or {}
        title = m.get("title") or r.get("title") or ""
        source = m.get("source") or r.get("source") or ""
        author = m.get("author") or ""
        ctype = m.get("type") or ""
        proj = m.get("project") or ""
        path = m.get("path") or ""

        if want_type and not _match_filter_value(ctype, want_type):
            continue
        if want_proj and not _match_filter_value(proj, want_proj):
            continue
        if want_source and not _match_filter_value(source, want_source):
            continue
        if want_title and not _match_filter_value(title, want_title):
            continue
        if want_author and not _match_filter_value(author, want_author):
            continue
        if want_path and not _match_filter_value(path, want_path):
            continue

        out.append(r)
    return out


def search(
    q: str,
    k: int = 8,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Pure, callable retriever. No prints, no input(), no CLI dependencies.

    Returns a list of dicts with keys: text, title, date, source, anchor,
    score, distance, metadata.

    Args:
        q: Search query string.
        k: Number of results to return.
        date_from: Inclusive start date (ISO or YYYY-MM-DD).
        date_to: Inclusive end date (ISO or YYYY-MM-DD).
        filters: Post-retrieval metadata filters (type, project, source, etc.).
    """
    if not isinstance(q, str) or not q.strip():
        return []

    # Cache key
    key = (
        "search", q, int(k),
        date_from or "", date_to or "",
        tuple(sorted((filters or {}).items())),
    )
    hit = _cache_get(key)
    if hit is not None:
        return hit

    # Vector search — fetch wider to afford post-filtering
    wide_k = max(k, 32)
    rows = _vector_query(q, k=wide_k)

    # Date window filter (inclusive)
    if date_from or date_to:
        df = _iso_parse(date_from) if date_from else None
        dt = _iso_parse(date_to) if date_to else None

        def in_range(r: Dict[str, Any]) -> bool:
            ts = _iso_parse(r.get("date"))
            if not ts:
                return False  # No timestamp = excluded from date-filtered results
            if df and ts < df:
                return False
            if dt and ts > dt:
                return False
            return True

        rows = [r for r in rows if in_range(r)]

    # Metadata filters
    rows = _apply_filters(rows, filters or {})

    # Final top-k
    final = rows[:k]
    _cache_set(key, final, expire=60)
    return final
