# Chronicle Beta

A local-first personal RAG memory system that turns your AI conversation history into a searchable, retrievable knowledge base. Designed to work with any LLM via MCP (Model Context Protocol).

## What It Does

Chronicle Beta ingests your exported AI conversations, chunks and embeds them into a local vector store, and exposes a retrieval interface via MCP. When connected to an LLM like Claude, the LLM can semantically search your entire conversation history. It finds relevant context, past decisions, code snippets, and ideas on demand.

The LLM handles query decomposition and answer synthesis. Chronicle handles storage and retrieval. 

## Architecture

```
Your LLM (via MCP) -> Chronicle MCP Server -> Retriever -> ChromaDB
                                                ↑
                              Ingestion: parser -> embedder -> vector store
```

**Two MCP tools:**
- `retrieve_chunks` - semantic search with optional metadata filters and date ranges
- `health_check` - connectivity and status probe

**Stack:**
- ChromaDB (persistent local vector store)
- all-MiniLM-L6-v2 (sentence-transformers, ~22MB, runs locally)
- MCP over stdio (JSON-RPC)

## Quick Start

**[Full setup guide ->](docs/QUICKSTART.md)** - step-by-step instructions for macOS, Windows (WSL), and Linux, including how to install prerequisites.

The short version:

```bash
mkdir -p ~/Projects && cd ~/Projects
git clone https://github.com/AnirudhB-6001/chronicle_beta.git
cd chronicle_beta
```

Export your ChatGPT data (Settings -> Data Controls -> Export Data), unzip the archive, and place `conversations.json` in the `data/` folder:

```
chronicle_beta/
└── data/
    └── conversations.json   <- place it here
```

Then run the install script:

```bash
bash scripts/install.sh
```

The script handles everything: verifies Python 3.10+, creates a virtual environment, installs dependencies (~2 GB first run), parses your conversations, embeds them into a local vector store, and prints the MCP config for Claude Desktop. It is idempotent - safe to re-run at any point, skipping completed steps.

Follow the printed instructions to connect to Claude Desktop, then ask Claude:

> "Use chronicle health_check"

If it responds with `status: ok` and sample titles from your conversations, you're done.

**Requirements:** Python 3.10+, ~3 GB disk space, 30–90 minutes for first setup. See the [full guide](docs/QUICKSTART.md) for how to install Python and other prerequisites on your OS.

## Troubleshooting

See the [Troubleshooting Guide](docs/TROUBLESHOOTING.md) for solutions to common installation, ingestion, and MCP connection issues across all platforms.

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
│   ├── parser.py              # ChatGPT export -> chunks.json
│   └── embed_and_index.py     # Chunks -> ChromaDB (stable IDs, rich metadata)
├── tests/                     # Unit + integration tests
├── eval/                      # Evaluation pipeline + golden datasets
├── data/                      # User data directory (gitignored)
├── docs/                      # Documentation
│   ├── QUICKSTART.md          # Full setup guide (macOS, Windows, Linux)
│   ├── TROUBLESHOOTING.md     # Solutions to common issues
│   └── eval.md                # Evaluation metrics and methodology
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

Apache 2.0 - see [LICENSE](LICENSE).

## Demo Video
https://youtu.be/CXG5Yvd43Qc?si=NJl_QnhceA_vMigx