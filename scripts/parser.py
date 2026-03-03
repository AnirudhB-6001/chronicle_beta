"""
Chronicle Beta — ChatGPT Export Parser

Parses a ChatGPT conversations.json export into chunked records
suitable for embedding and indexing.

Usage:
    python -m scripts.parser
    python -m scripts.parser --input data/conversations.json --output data/chunks.json
    python -m scripts.parser --chunk-size 500
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_CHUNK_SIZE = 1000


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Parse ChatGPT export into Chronicle chunks.")
    p.add_argument("--input", default="data/conversations.json", help="Path to conversations.json.")
    p.add_argument("--output", default="data/chunks.json", help="Output path for chunks JSON.")
    p.add_argument(
        "--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE,
        help=f"Character limit per chunk (default: {DEFAULT_CHUNK_SIZE}).",
    )
    return p.parse_args()


def load_conversations(filepath: str) -> List[Dict[str, Any]]:
    """Load raw ChatGPT export JSON."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def chunk_text(text: str, size: int = DEFAULT_CHUNK_SIZE) -> List[str]:
    """Split text into chunks of at most `size` characters."""
    return [text[i : i + size] for i in range(0, len(text), size)]


def process_conversations(
    json_data: List[Dict[str, Any]],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> List[Dict[str, Any]]:
    """
    Process a ChatGPT export into a flat list of chunk records.

    Each chunk record contains:
        text, chat_title, timestamp, chat_index, chunk_index
    """
    chunks: List[Dict[str, Any]] = []

    for i, convo in enumerate(json_data):
        title = convo.get("title", f"Chat {i}")
        messages = convo.get("mapping", {})

        full_text = ""
        timestamps: List[datetime] = []

        for node in messages.values():
            if not node:
                continue

            msg = node.get("message")
            if msg is None:
                continue

            role = msg.get("author", {}).get("role", "unknown")
            content_parts = msg.get("content", {}).get("parts", [])

            # Normalize content parts (handle both str and dict)
            normalized_parts = []
            for part in content_parts:
                if isinstance(part, str):
                    normalized_parts.append(part)
                elif isinstance(part, dict):
                    normalized_parts.append(part.get("text", ""))
                else:
                    normalized_parts.append(str(part))

            content = " ".join(normalized_parts).strip()

            timestamp = msg.get("create_time", None)
            if timestamp:
                try:
                    dt = datetime.fromtimestamp(timestamp)
                    timestamps.append(dt)
                except Exception:
                    pass

            full_text += f"\n[{role.upper()}]: {content}"

        date_str = min(timestamps).strftime("%Y-%m-%d") if timestamps else "unknown"
        convo_chunks = chunk_text(full_text, size=chunk_size)

        for j, chunk in enumerate(convo_chunks):
            chunks.append({
                "text": chunk.strip(),
                "chat_title": title,
                "timestamp": date_str,
                "chat_index": i,
                "chunk_index": j,
            })

    return chunks


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    print(f"Loading conversations from {input_path}")
    raw_data = load_conversations(str(input_path))

    print(f"Processing and chunking (chunk_size={args.chunk_size})...")
    all_chunks = process_conversations(raw_data, chunk_size=args.chunk_size)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    print(f"Done! {len(all_chunks)} chunks saved to {output_path}")


if __name__ == "__main__":
    main()
