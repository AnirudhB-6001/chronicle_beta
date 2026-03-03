"""
Chronicle Beta — Embed and Index

Embed parsed chunks into ChromaDB with rich metadata.

Highlights:
  - Configurable via CLI (model, db path, collection, input file, batch size, limit, reset).
  - Preserves/creates collection; --reset to drop/rebuild.
  - Rich metadata fields for filtering: title, timestamp, source, type, project, author.
  - Stable IDs via SHA1 + collision suffix.
  - Optional project hints file for auto-tagging.

Usage:
    python -m scripts.embed_and_index --reset
    python -m scripts.embed_and_index --limit 500 --batch-size 64
    python -m scripts.embed_and_index --project-hints my_projects.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import chromadb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm


# -----------------------------
# CLI args
# -----------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Embed and index Chronicle chunks into ChromaDB."
    )
    p.add_argument("--input", default="data/chunks.json", help="Path to chunks JSON.")
    p.add_argument("--db-path", default="data/vector_store", help="Chroma persistent path.")
    p.add_argument("--collection", default="chronicle_memory", help="Chroma collection name.")
    p.add_argument("--model", default="all-MiniLM-L6-v2", help="SentenceTransformer model.")
    p.add_argument("--batch-size", type=int, default=128, help="Embedding batch size.")
    p.add_argument("--limit", type=int, default=0, help="If >0, limit number of chunks.")
    p.add_argument("--reset", action="store_true", help="Drop existing collection before indexing.")
    p.add_argument(
        "--project-hints", default=None,
        help=(
            "Optional JSON file mapping lowercase keywords to project names. "
            "Example: {\"my project\": \"My Project\", \"other\": \"Other Project\"}"
        ),
    )
    return p.parse_args()


# -----------------------------
# Helpers
# -----------------------------
def _sanitize(value: Any, fallback: Any = "unknown") -> Any:
    """Ensure no None leaks into Chroma metadata."""
    if value is None:
        return fallback
    return value


def _iso(ts: Any) -> str:
    """Best-effort ISO-8601 normalizer; returns '' if empty."""
    if not ts:
        return ""
    if isinstance(ts, str):
        s = ts.strip()
        if not s:
            return ""
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).isoformat()
        except Exception:
            try:
                datetime.fromisoformat(s + "T00:00:00")
                return s
            except Exception:
                return s
    if isinstance(ts, (int, float)):
        try:
            return datetime.utcfromtimestamp(float(ts)).isoformat() + "Z"
        except Exception:
            return ""
    if isinstance(ts, datetime):
        return ts.isoformat()
    return str(ts)


def _guess_type(title: str, path: str, text: str) -> str:
    """Heuristic content type detection."""
    s_title = (title or "").lower()
    s_path = (path or "").lower()
    s_txt = text or ""

    if s_path.endswith(".py") or "commit" in s_title or "commit" in s_path:
        return "code"
    if any(tok in s_title for tok in ("chat", "thread", "conversation")):
        return "chat"
    if any(tok in s_path for tok in ("chat", "thread", "slack")):
        return "chat"
    if "```" in s_txt or "def " in s_txt or "class " in s_txt or "import " in s_txt:
        return "code"
    if s_path.endswith((".md", ".txt", ".rst")) or any(t in s_title for t in ("note", "readme")):
        return "doc"
    return "unknown"


def _load_project_hints(hints_path: Optional[str]) -> Dict[str, str]:
    """Load project hints from a JSON file, or return empty dict."""
    if not hints_path or not os.path.exists(hints_path):
        return {}
    try:
        with open(hints_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k).lower(): str(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def _guess_project(title: str, path: str, text: str, hints: Dict[str, str]) -> Optional[str]:
    """Match content against project hints."""
    if not hints:
        return None
    hay = " ".join([title or "", path or "", text[:400] or ""]).lower()
    for keyword, project_name in hints.items():
        if keyword in hay:
            return project_name
    return None


def _stable_id(
    origin_id: Any, text: str, ts: Optional[str], title: Optional[str],
    path: str, chat_index: Any, chunk_index: Any,
) -> str:
    """Stable SHA1 id using multiple fields to minimize collisions."""
    h = hashlib.sha1()
    h.update(str(origin_id or "").encode("utf-8"))
    h.update((text or "").encode("utf-8"))
    h.update((ts or "").encode("utf-8"))
    h.update((title or "").encode("utf-8"))
    h.update((path or "").encode("utf-8"))
    h.update(str(chat_index).encode("utf-8"))
    h.update(str(chunk_index).encode("utf-8"))
    return h.hexdigest()


def _clean_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure all metadata values are primitives and non-None.
    Chroma accepts only bool | int | float | str (no None).
    """
    cleaned: Dict[str, Any] = {}
    for k, v in meta.items():
        if v is None:
            cleaned[k] = ""
            continue
        if k in ("chat_index", "chunk_index"):
            try:
                cleaned[k] = int(v)
            except Exception:
                cleaned[k] = -1
            continue
        if isinstance(v, (bool, int, float, str)):
            cleaned[k] = v
            continue
        cleaned[k] = str(v)
    return cleaned


# -----------------------------
# Load chunks
# -----------------------------
def load_chunks(path: str, limit: int = 0) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path} must be a list of chunk dicts.")
    if limit and limit > 0:
        data = data[:limit]
    return data


# -----------------------------
# Build records for Chroma
# -----------------------------
def build_records(
    chunks: List[Dict[str, Any]],
    project_hints: Optional[Dict[str, str]] = None,
) -> Tuple[List[str], List[str], List[Dict[str, Any]]]:
    ids: List[str] = []
    docs: List[str] = []
    metas: List[Dict[str, Any]] = []
    seen_ids: Dict[str, int] = {}

    hints = project_hints or {}

    for c in chunks:
        text = c.get("text") or ""
        title = _sanitize(c.get("chat_title"), "untitled")
        timestamp = _iso(c.get("timestamp"))
        chat_index = _sanitize(c.get("chat_index"), -1)
        chunk_index = _sanitize(c.get("chunk_index"), -1)
        path = _sanitize(c.get("path") or c.get("source") or "", "")
        author = _sanitize(c.get("author") or c.get("user"), "")
        origin_id = _sanitize(c.get("id") or c.get("_id"), "")

        source = _sanitize(path or title, title)
        ctype = _guess_type(str(title), str(path), str(text))
        project = _sanitize(_guess_project(str(title), str(path), str(text), hints), "")

        meta = _clean_meta({
            "title": title,
            "timestamp": timestamp,
            "source": source,
            "type": ctype,
            "project": project,
            "author": author,
            "chat_index": chat_index,
            "chunk_index": chunk_index,
            "path": path,
            "origin_id": origin_id,
        })

        base_id = _stable_id(origin_id, text, timestamp, title, path, chat_index, chunk_index)
        if base_id in seen_ids:
            seen_ids[base_id] += 1
            uniq_id = f"{base_id}-{seen_ids[base_id]}"
        else:
            seen_ids[base_id] = 0
            uniq_id = base_id

        ids.append(uniq_id)
        docs.append(text)
        metas.append(meta)

    return ids, docs, metas


# -----------------------------
# Main
# -----------------------------
def main():
    args = parse_args()

    # Load project hints if provided
    project_hints = _load_project_hints(args.project_hints)
    if project_hints:
        print(f"Loaded {len(project_hints)} project hints from {args.project_hints}")

    print(f"Loading embedding model: {args.model}")
    model = SentenceTransformer(args.model)

    print(f"Opening Chroma at {args.db_path!r}")
    client = chromadb.PersistentClient(path=args.db_path)

    # Drop or create collection
    existing = {c.name for c in client.list_collections()}
    if args.reset and args.collection in existing:
        client.delete_collection(args.collection)
        print(f"Deleted existing collection: {args.collection}")

    if args.collection in {c.name for c in client.list_collections()}:
        coll = client.get_collection(args.collection)
        print(f"Using existing collection: {args.collection}")
    else:
        coll = client.create_collection(args.collection)
        print(f"Created collection: {args.collection}")

    # Load + prepare
    print(f"Loading chunks from {args.input!r}")
    raw = load_chunks(args.input, limit=args.limit)
    print(f"Preparing {len(raw)} chunk(s)")
    ids, docs, metas = build_records(raw, project_hints=project_hints)

    # Embed + add in batches
    B = max(1, int(args.batch_size))
    print(f"Embedding + indexing in batches of {B}")
    for i in tqdm(range(0, len(docs), B)):
        batch_docs = docs[i : i + B]
        batch_ids = ids[i : i + B]
        batch_metas = metas[i : i + B]
        embs = model.encode(batch_docs)
        coll.add(documents=batch_docs, embeddings=embs, metadatas=batch_metas, ids=batch_ids)

    print("Indexing complete.")

    # Summary
    type_counts: Dict[str, int] = {}
    proj_counts: Dict[str, int] = {}
    for m in metas:
        t = m.get("type", "unknown") if isinstance(m.get("type"), str) else "unknown"
        p = m.get("project", "none") if isinstance(m.get("project"), str) else "none"
        type_counts[t] = type_counts.get(t, 0) + 1
        proj_counts[p] = proj_counts.get(p, 0) + 1

    print(f"  Types: {type_counts}")
    print(f"  Projects: {proj_counts}")
    print(f"  Total indexed: {len(docs)}")


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    main()
