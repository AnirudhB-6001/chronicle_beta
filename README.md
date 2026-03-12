# Chronicle Beta

A local-first personal RAG memory system that turns your AI conversation history into a searchable, retrievable knowledge base. Designed to work with any LLM via MCP (Model Context Protocol).

## What It Does

Chronicle Beta ingests your exported AI conversations, chunks and embeds them into a local vector store, and exposes a retrieval interface via MCP. When connected to an LLM like Claude, the LLM can semantically search your entire conversation history. It finds relevant context, past decisions, code snippets, and ideas on demand.

The LLM handles query decomposition and answer synthesis. Chronicle handles storage and retrieval. 

## Architecture

```
Your LLM (via MCP) → Chronicle MCP Server → Retriever → ChromaDB
                                                ↑
                              Ingestion: parser → embedder → vector store
```

**Two MCP tools:**
- `retrieve_chunks` - semantic search with optional metadata filters and date ranges
- `health_check` - connectivity and status probe

**Stack:**
- ChromaDB (persistent local vector store)
- all-MiniLM-L6-v2 (sentence-transformers, ~22MB, runs locally)
- MCP over stdio (JSON-RPC)

## Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/AnirudhB-6001/chronicle_beta.git
cd chronicle_beta
```

### 2. Export your ChatGPT data

Go to ChatGPT → **Settings → Data Controls → Export Data**. You'll receive an email with a download link. Unzip the archive and place `conversations.json` in the `data/` folder inside the cloned repository.
```
chronicle_beta/
└── data/
    └── conversations.json   ← place it here
```

### 3. Run the install script (WSL / Linux / macOS)
```bash
bash scripts/install.sh
```

The script runs the full pipeline in one pass: verifies Python 3.10+, creates a virtual environment, installs dependencies (~2GB first run), parses your conversations, embeds them into a local vector store, and prints the MCP config for Claude Desktop. Indexing ~30k chunks takes approximately 45 minutes — the embedding model runs entirely on your machine.

The script is idempotent. It detects completed steps and skips them on re-run.

### 4. Connect to Claude Desktop

The install script prints the exact MCP config block with your paths filled in. Copy it into your `claude_desktop_config.json`:

| Platform | Config file location |
| --- | --- |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Windows Store | `AppData\Local\Packages\Claude_*\LocalCache\Roaming\Claude\` |

Restart Claude Desktop, then ask Claude:

> "Use chronicle health_check"

If it responds with status `ok` and sample titles from your conversations, you're done.

### What the install script does

The script is safe to re-run at any point. It detects what's already done and skips it:

| State | What happens |
| --- | --- |
| No venv | Creates virtual environment and installs dependencies |
| venv exists, deps installed | Skips install (seconds) |
| No `conversations.json` | Pauses, tells you where to put the file |
| `conversations.json` present, no `chunks.json` | Runs parser automatically |
| `chunks.json` exists, no vector store | Runs embedding and indexing |
| Vector store exists | Skips ingestion, prints MCP config |

To rebuild from scratch: `rm -rf venv data/chunks.json data/vector_store` and re-run.

## Troubleshooting

**Install script fails on "Dependency installation failed"**
If you're on WSL and see `[Errno 5] Input/output error`, this is a known WSL + NTFS issue. Try running the script again — pip may succeed on retry. If deps are already installed from a previous attempt, the script will detect them and skip the install.

**PyTorch download is very slow or fails**
sentence-transformers pulls PyTorch (~2GB). On slow connections, this can take 10-20 minutes. If it times out, re-run the script — pip caches partial downloads.

**Indexing takes a long time**
First-run indexing of 30k+ chunks takes ~45 minutes. This is normal — the embedding model runs locally on CPU. Subsequent runs skip indexing if the vector store already exists.

**Claude Desktop doesn't show Chronicle tools**
Check that `claude_desktop_config.json` has the correct paths. The `command` field must point to the Python binary inside your venv (not the system Python). The `cwd` must be the chronicle_beta project root. After editing the config, fully quit Claude Desktop (not just close the window) and reopen it.

**health_check returns "degraded" or no results**
The vector store may not be built yet. Run `bash scripts/install.sh` to verify — it will tell you if any step was skipped.

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
- `retrieval_query` - string or list of strings for multi-query retrieval
- `k` - number of results (default: 8)
- `date_from` / `date_to` - ISO date strings for time-window filtering
- `filters` - metadata filters: `type`, `project`, `source`, `title`, `author`, `path`

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
│   ├── install.sh             # One-command setup (install + ingest)
│   ├── parser.py              # ChatGPT export → chunks.json
│   └── embed_and_index.py     # Chunks → ChromaDB (stable IDs, rich metadata)
├── tests/                     # Unit + integration tests
├── eval/                      # Evaluation pipeline + golden datasets
├── data/                      # User data directory (gitignored)
├── docs/                      # Documentation
├── pyproject.toml
├── LICENSE                    # Apache 2.0
├── SECURITY.md                # Vulnerability reporting
└── README.md
```

## Privacy

Chronicle Beta is local-first by design. Your conversation data never leaves your machine.

- **No cloud dependencies.** Embeddings are computed locally using sentence-transformers. No OpenAI API, no external embedding services.
- **No telemetry.** Chronicle Beta does not phone home, collect analytics, or transmit any data.
- **No API keys required.** Everything runs on your hardware.
- **All user data is gitignored.** The `data/` directory (conversations, chunks, vector store) is excluded from version control by default.
- **MCP data flow.** When connected to an LLM client like Claude Desktop, retrieved chunks are sent to the LLM via stdio for answer synthesis. At that point, the LLM provider's data handling policies apply. Chronicle Beta itself does not control what happens after chunks leave the MCP interface.

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting instructions.

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Demo Video
https://youtu.be/CXG5Yvd43Qc?si=NJl_QnhceA_vMigx