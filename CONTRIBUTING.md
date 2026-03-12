# Contributing to Chronicle Beta

Thank you for your interest in contributing. This document explains how to set up a development environment, run tests, and submit changes.

## Getting Started

### Dev environment setup

**Option A Using the install script (recommended):**
```bash
git clone https://github.com/AnirudhB-6001/chronicle_beta.git
cd chronicle_beta
bash scripts/install.sh
```

The install script creates a virtual environment, installs all dependencies including dev tools (pytest, ruff), and verifies the installation. You don't need data files to work on the codebase, the script will pause at the ingestion step if no `conversations.json` is present.

**Option B Manual setup:**
```bash
git clone https://github.com/AnirudhB-6001/chronicle_beta.git
cd chronicle_beta
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

### Running tests

```bash
source venv/bin/activate
pytest
```

This runs the full test suite (unit tests + smoke tests). All tests should pass without any data files, they use fixtures and mocks.

To run with coverage:
```bash
pytest --cov=mcp_server --cov=retriever --cov=scripts
```

### Running the eval suite

The eval suite measures retrieval quality against a golden question dataset. This requires a built vector store (i.e., you need to have run the full install with data).

```bash
source venv/bin/activate
python -m eval.run_eval --dataset eval/golden_questions.json
```

See [docs/eval.md](docs/eval.md) for details on metrics.

### Code style

Chronicle Beta uses [ruff](https://docs.astral.sh/ruff/) for linting, configured in `pyproject.toml`:

```bash
ruff check .          # lint
ruff check --fix .    # auto-fix what's possible
ruff format .         # format
```

Key settings: line length 100, target Python 3.10, rules E/F/W/I/N/UP.

## Making Changes

### When to open an issue vs a PR

- **Open an issue** if you've found a bug, have a setup problem, want to report a retrieval quality issue, or want to propose a feature. Use the appropriate [issue template](https://github.com/AnirudhB-6001/chronicle_beta/issues/new/choose).
- **Open a PR** if you've already written the fix or feature and want to contribute it. Link the related issue if one exists.

For anything non-trivial, open an issue first to discuss the approach before writing code. This avoids wasted effort on changes that don't align with the project direction.

### Commit messages

Use [conventional commits](https://www.conventionalcommits.org/):

| Prefix | Use for |
|--------|---------|
| `feat:` | New feature or capability |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `test:` | Adding or updating tests |
| `chore:` | Build, config, dependency changes |
| `refactor:` | Code change that doesn't add features or fix bugs |

Examples:
```
feat: add date range filter to retrieve_chunks
fix: parser crash on empty conversation mapping
docs: add WSL troubleshooting for NTFS I/O errors
test: add edge case tests for empty query handling
chore: pin numpy to 2.4.3
```

### PR guidelines

- Keep PRs focused | one logical change per PR
- Include tests for new functionality
- Run `pytest` and `ruff check` before submitting
- If the change affects retrieval quality, include eval results (before/after)
- Update documentation if your change affects user-facing behavior

## Project Architecture

```
chronicle_beta/
├── mcp_server/           # MCP JSON-RPC server (entry point for Claude Desktop)
│   ├── server.py         # Protocol handling, tool routing
│   └── tools/
│       └── retrieve_chunks.py  # Retrieval tool: multi-query, dedup, merge
├── retriever/
│   └── core.py           # Vector search via ChromaDB, filters, date windows, caching
├── scripts/
│   ├── install.sh        # One-command setup
│   ├── parser.py         # ChatGPT export → chunks.json
│   └── embed_and_index.py  # Chunks → ChromaDB with stable IDs
├── tests/                # pytest suite
├── eval/                 # Retrieval quality evaluation
└── docs/                 # Guides and references
```

The separation of concerns is intentional: the MCP server handles protocol, the retriever handles search, the parser handles ingestion. Changes to one layer should not require changes to another.

## Scope What We're Not Doing (Yet)

The following items are intentionally deferred. Please do not open PRs for these without discussing in an issue first. These have been considered and deprioritized for specific reasons documented in the product roadmap.

| Item | Why not now |
|------|------------|
| Local LLM integration | Chronicle's value is MCP integration with frontier LLMs, not running local models |
| Desktop GUI | No demand signal yet; focus is on core retrieval and MCP reliability |
| Encryption at rest | Theoretical risk for a local-first tool; enterprise feature, not personal tool priority |
| Semantic chunking rewrite | Current fixed-character chunking achieves 100% content recall. No eval evidence of failure |
| Recursive summarization | Adds drift; Chronicle's value is raw evidence retrieval |
| Background sync / tray app | Users export data manually; not worth the engineering yet |
| Fuzzy deduplication | Decided against after analysis; exact-hash dedup preserves evidence |

If you believe one of these should be reconsidered, open an issue with concrete evidence (eval results, user feedback, or a specific failure case). Philosophical arguments alone won't change the priority.

## Getting Help

- **Setup problems:** Check the [Troubleshooting Guide](docs/TROUBLESHOOTING.md) first, then open a setup issue
- **Questions about architecture or approach:** Open a discussion or issue
- **Security vulnerabilities:** See [SECURITY.md](SECURITY.md) | do not open a public issue

## License

By contributing, you agree that your contributions will be licensed under the [Apache 2.0 License](LICENSE).
