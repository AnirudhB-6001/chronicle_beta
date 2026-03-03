# Chronicle Beta

A local-first personal RAG memory system that turns your AI conversation history into a searchable, retrievable knowledge base — designed to work with any LLM via MCP (Model Context Protocol).

## What It Does

Chronicle Beta ingests your exported AI conversations, chunks and embeds them into a local vector store, and exposes a retrieval interface via MCP. When connected to an LLM like Claude, the LLM can semantically search your entire conversation history — finding relevant context, past decisions, code snippets, and ideas on demand.

The LLM handles query decomposition and answer synthesis. Chronicle handles storage and retrieval. Clean separation of concerns.

## Architecture

```
Your LLM (via MCP) → Chronicle MCP Server → Retriever → ChromaDB
                                                ↑
                              Ingestion: parser → embedder → vector store
```

**Two MCP tools:**
- `retrieve_chunks` — semantic search with optional metadata filters and date ranges
- `health_check` — connectivity and status probe

**Stack:**
- ChromaDB (persistent local vector store)
- all-MiniLM-L6-v2 (sentence-transformers, ~22MB, runs locally)
- MCP over stdio (JSON-RPC)

## Quick Start

### 1. Install
```bash
git clone https://github.com/AnirudhB-6001/chronicle_beta.git
cd chronicle_beta
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -e .
```

### 2. Ingest your data
Export your ChatGPT conversations (Settings → Data Controls → Export Data).
Place the `conversations.json` in `data/`.

```bash
# Parse conversations into chunks
python -m scripts.parser --input data/conversations.json --output data/chunks.json

# Embed and index into ChromaDB
python -m scripts.embed_and_index --input data/chunks.json --db-path data/vector_store
```

### 3. Connect via MCP
Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "chronicle": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/chronicle_beta",
      "env": {
        "CHRONICLE_NONINTERACTIVE": "1",
        "TOKENIZERS_PARALLELISM": "false"
      }
    }
  }
}
```

## Configuration

### Ingestion options
```bash
python -m scripts.embed_and_index \
  --input data/chunks.json \
  --db-path data/vector_store \
  --collection chronicle_memory \
  --model all-MiniLM-L6-v2 \
  --batch-size 100 \
  --reset  # drop and rebuild collection
```

### Retrieval filters
The `retrieve_chunks` tool supports:
- `retrieval_query` — string or list of strings for multi-query retrieval
- `k` — number of results (default: 8)
- `date_from` / `date_to` — ISO date strings for time-window filtering
- `filters` — metadata filters: `type`, `project`, `source`, `title`, `author`, `path`

## Eval

Chronicle Beta includes an evaluation pipeline for measuring retrieval quality.

```bash
# Run the eval suite
python -m eval.run_eval --dataset eval/golden_questions.json
```

See [docs/eval.md](docs/eval.md) for details on metrics (Precision@k, Recall@k, MRR, NDCG).

## Project Structure

```
chronicle_beta/
├── mcp_server/
│   ├── server.py              # MCP JSON-RPC server (2 tools)
│   └── tools/
│       └── retrieve_chunks.py # Retrieval tool wrapper
├── retriever/
│   └── core.py                # Callable retriever: search(q, k, filters, dates)
├── scripts/
│   ├── parser.py              # ChatGPT export → chunks.json
│   └── embed_and_index.py     # Chunks → ChromaDB (stable IDs, rich metadata)
├── tests/                     # Unit + integration tests
├── eval/                      # Evaluation pipeline + golden datasets
├── data/                      # User data directory (gitignored)
├── docs/                      # Documentation
├── pyproject.toml
├── LICENSE                    # MIT
└── README.md
```

## Privacy

Chronicle Beta is local-first by design. Your data never leaves your machine.
- No cloud dependencies
- No telemetry
- No API keys required (embeddings run locally)
- All data stored in `data/` which is gitignored

## License

MIT — see [LICENSE](LICENSE).
