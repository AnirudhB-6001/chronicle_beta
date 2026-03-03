#!/usr/bin/env python3
"""
Chronicle Beta — MCP Server (stdio JSON-RPC)

Exposes two tools to any MCP-compatible LLM client:
  1. retrieve_chunks  — semantic search with filters and date windows
  2. health_check     — lightweight connectivity and status probe

The LLM handles query decomposition and answer synthesis.
Chronicle handles storage and retrieval.
"""

import sys
import json
import traceback
import io
import contextlib
import os

# Flush lines; avoid stray prints mixing with protocol
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

SERVER_NAME = "chronicle-beta"
SERVER_VERSION = "0.1.0"

TOOLS = {
    "retrieve_chunks": {
        "name": "retrieve_chunks",
        "description": (
            "Run Chronicle retrieval for one string query or a list of sub-queries; "
            "return standardized chunks with metadata. Supports optional date window "
            "and metadata filters.\n\n"
            "Best practices for the calling LLM:\n"
            "- Decompose complex questions into 3-5 focused keyword queries.\n"
            "- Use array syntax: [\"topic keywords\", \"related concept\"] "
            "not full sentences.\n"
            "- Use filters when you know the content type or project.\n"
            "- Use date_from/date_to for temporal queries.\n\n"
            "The returned chunks contain source_name, timestamp, relevance_score, "
            "content_raw, content_type, and project fields. The calling LLM should "
            "synthesize an evidence-based answer from these chunks, citing sources "
            "and presenting an evidence timeline."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "retrieval_query": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                    "description": (
                        "One or more retrieval queries. Use keyword-dense phrases, "
                        "not full sentences. Array of 3-5 variations recommended "
                        "for complex questions."
                    ),
                },
                "k": {
                    "type": "integer",
                    "description": "Number of results per query (default: 8).",
                },
                "date_from": {
                    "type": ["string", "null"],
                    "description": "Inclusive start date filter (YYYY-MM-DD).",
                },
                "date_to": {
                    "type": ["string", "null"],
                    "description": "Inclusive end date filter (YYYY-MM-DD).",
                },
                "filters": {
                    "type": "object",
                    "description": (
                        "Optional metadata filters. Supported keys: "
                        "type (chat|code|doc|unknown), project, source, title, author, path. "
                        "All filters are case-insensitive substring matches."
                    ),
                },
            },
            "required": ["retrieval_query"],
        },
    },
    "health_check": {
        "name": "health_check",
        "description": (
            "Light connectivity and status probe. Returns server info, "
            "environment flags, and runs a tiny test retrieval to verify "
            "the vector store is accessible."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "probe_query": {
                    "type": "string",
                    "description": "Optional test query to verify retrieval works (default: 'test').",
                },
            },
        },
    },
}


def _ok(req_id, result):
    """Build a JSON-RPC success response."""
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id, msg, data=None, code=-32000):
    """Build a JSON-RPC error response."""
    e = {"jsonrpc": "2.0", "id": req_id or "", "error": {"code": code, "message": msg}}
    if data is not None:
        e["error"]["data"] = data
    return e


def _wrap_content(payload, summary=None):
    """
    Wrap tool result for MCP transport.
    Returns text-only JSON (compatible with all MCP clients).
    """
    text_blob = json.dumps(payload, indent=2, ensure_ascii=False)
    if summary:
        text_blob += f"\n\nSummary: {summary}"
    return {"content": [{"type": "text", "text": text_blob}]}


def _handle_call(method: str, params: dict):
    """Route a JSON-RPC method call to the appropriate handler."""

    # ---- Initialization ----
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion") or "2025-06-18",
            "capabilities": {
                "tools": {"list": True, "call": True},
                "prompts": {"list": True},
                "resources": {"list": True},
            },
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }

    # ---- Optional probes (required by some MCP clients) ----
    if method == "prompts/list":
        return {"prompts": []}
    if method == "resources/list":
        return {"resources": []}
    if method == "resources/subscribe":
        return {"subscriptions": []}

    # ---- Tools ----
    if method == "tools/list":
        return {"tools": list(TOOLS.values())}

    if method == "tools/call":
        tool = params.get("name")
        args = params.get("arguments", {}) or {}

        os.environ.setdefault("CHRONICLE_NONINTERACTIVE", "1")

        # Capture any stray stdout/stderr from libraries
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):

            if tool == "retrieve_chunks":
                from mcp_server.tools.retrieve_chunks import retrieve_chunks

                payload = retrieve_chunks(
                    args.get("retrieval_query", ""),
                    k=args.get("k", 8),
                    date_from=args.get("date_from"),
                    date_to=args.get("date_to"),
                    filters=args.get("filters") or {},
                )
                summary = (
                    f"mode={payload.get('meta', {}).get('mode')}; "
                    f"chunks={len(payload.get('chunks', []))}"
                )
                return _wrap_content(payload, summary=summary)

            if tool == "health_check":
                probe_q = (args.get("probe_query") or "test").strip()
                probe_titles, probe_n, probe_error = [], 0, None
                try:
                    from retriever.core import search
                    results = search(probe_q, k=3) or []
                    probe_n = len(results)
                    probe_titles = [
                        (x.get("title") or x.get("source") or "untitled")
                        for x in results
                    ][:3]
                except Exception as e:
                    probe_error = f"{type(e).__name__}: {e}"

                payload = {
                    "server": SERVER_NAME,
                    "version": SERVER_VERSION,
                    "status": "ok" if not probe_error else "degraded",
                    "cwd": os.getcwd(),
                    "python": sys.executable,
                    "env_flags": {
                        "CHRONICLE_NONINTERACTIVE": os.environ.get("CHRONICLE_NONINTERACTIVE"),
                        "TOKENIZERS_PARALLELISM": os.environ.get("TOKENIZERS_PARALLELISM"),
                    },
                    "probe": {
                        "query": probe_q,
                        "results_count": probe_n,
                        "sample_titles": probe_titles,
                    },
                }
                if probe_error:
                    payload["probe"]["error"] = probe_error
                summary = f"status={payload['status']}; probe_n={probe_n}"
                return _wrap_content(payload, summary=summary)

        raise ValueError(f"Unknown tool: {tool}")

    # ---- Unknown method ----
    raise ValueError(f"Unknown method: {method}")


def main():
    """Main stdio JSON-RPC loop."""
    sys.path.insert(0, os.getcwd())

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except Exception as e:
            sys.stdout.write(json.dumps(_err(None, f"Parse error: {e}", code=-32700)) + "\n")
            sys.stdout.flush()
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {}) or {}

        cap_out, cap_err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(cap_out), contextlib.redirect_stderr(cap_err):
                result = _handle_call(method, params)
            sys.stdout.write(json.dumps(_ok(req_id, result)) + "\n")
            sys.stdout.flush()
        except Exception as e:
            debug = {
                "traceback": traceback.format_exc(),
                "captured_stdout": cap_out.getvalue(),
                "captured_stderr": cap_err.getvalue(),
            }
            sys.stdout.write(json.dumps(_err(req_id, str(e), data=debug)) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
