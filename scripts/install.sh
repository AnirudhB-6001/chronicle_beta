#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# Chronicle Beta — Install & Setup (Linux / WSL / macOS)
#
# One script, full pipeline:
#   1. Check Python ≥ 3.10
#   2. Create venv and install dependencies
#   3. Parse conversations.json (if present)
#   4. Embed and index into ChromaDB (if parsed)
#   5. Print MCP config for Claude Desktop
#
# Run from the project root:
#   cd chronicle_beta && bash scripts/install.sh
#
# Safe to re-run — skips steps that are already done.
# ──────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colours (disabled when not a terminal) ────────────────────
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    RED='\033[0;31m'
    BOLD='\033[1m'
    DIM='\033[2m'
    RESET='\033[0m'
else
    GREEN='' YELLOW='' RED='' BOLD='' DIM='' RESET=''
fi

info()  { printf "${GREEN}✓${RESET} %s\n" "$1"; }
warn()  { printf "${YELLOW}!${RESET} %s\n" "$1"; }
fail()  { printf "${RED}✗ %s${RESET}\n" "$1"; exit 1; }
step()  { printf "\n${BOLD}▸ %s${RESET}\n" "$1"; }

# ── Ensure we're in the project root ──────────────────────────
if [ ! -f "pyproject.toml" ] || [ ! -d "mcp_server" ]; then
    fail "Run this script from the chronicle_beta project root.
    Expected: cd chronicle_beta && bash scripts/install.sh"
fi

PROJ_ROOT="$(pwd)"

# ══════════════════════════════════════════════════════════════
# PHASE 1: Environment Setup
# ══════════════════════════════════════════════════════════════

# ── Step 1: Find Python ≥ 3.10 ───────────────────────────────
step "Checking Python version"

PYTHON=""
for candidate in python3 python python3.12 python3.11 python3.10; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "${major:-0}" -ge 3 ] && [ "${minor:-0}" -ge 10 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    fail "Python 3.10+ is required but not found.
    Install it from https://www.python.org/downloads/ and re-run this script."
fi

info "Found $PYTHON ($ver)"

# ── Step 2: Check venv module ─────────────────────────────────
step "Checking venv module"

if ! "$PYTHON" -c "import venv" &>/dev/null; then
    fail "Python venv module not available.
    On Debian/Ubuntu: sudo apt install python${ver}-venv
    On Fedora:        sudo dnf install python3-virtualenv
    On macOS:         venv is included with python.org installs."
fi

info "venv module available"

# ── Step 3: Create virtual environment ────────────────────────
step "Creating virtual environment"

VENV_DIR="$PROJ_ROOT/venv"

if [ -d "$VENV_DIR" ]; then
    warn "venv/ already exists — reusing it"
else
    "$PYTHON" -m venv "$VENV_DIR"
    info "Created venv at $VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
info "Activated virtual environment"

# ── Step 4: Install dependencies ──────────────────────────────
step "Installing Chronicle Beta and dependencies"

# Check if deps already work — skip the slow pip install if so
DEPS_OK=false
python -c "
import chromadb
from sentence_transformers import SentenceTransformer
import diskcache
" 2>/dev/null && DEPS_OK=true

if [ "$DEPS_OK" = true ]; then
    info "Dependencies already installed — skipping pip install"
else
    printf "${DIM}  (sentence-transformers pulls PyTorch — first install is ~2GB, be patient)${RESET}\n"

    pip install --upgrade pip --quiet 2>&1 | tail -1 || true

    pip install -e ".[dev]" 2>&1 | grep -E "(Installing|Successfully|ERROR|already satisfied)" | tail -8 || true

    # Verify core imports after install
    python -c "
import chromadb
from sentence_transformers import SentenceTransformer
" 2>/dev/null || fail "Dependency installation failed. Check the output above for errors."
fi

info "All dependencies installed"

# ── Step 5: Prepare data directory ────────────────────────────
mkdir -p "$PROJ_ROOT/data"

# ── Step 6: Verify installation ───────────────────────────────
step "Verifying installation"

VERIFY=$(python -c "
import sys
checks = []

v = sys.version_info
checks.append(('Python', f'{v.major}.{v.minor}.{v.micro}', v.major >= 3 and v.minor >= 10))

try:
    import chromadb
    checks.append(('chromadb', chromadb.__version__, True))
except Exception:
    checks.append(('chromadb', 'MISSING', False))

try:
    import sentence_transformers
    checks.append(('sentence-transformers', sentence_transformers.__version__, True))
except Exception:
    checks.append(('sentence-transformers', 'MISSING', False))

try:
    import diskcache
    checks.append(('diskcache', diskcache.__version__, True))
except Exception:
    checks.append(('diskcache', 'MISSING', False))

try:
    from scripts.parser import process_conversations
    checks.append(('scripts.parser', 'ok', True))
except Exception:
    checks.append(('scripts.parser', 'IMPORT FAIL', False))

try:
    from retriever.core import search
    checks.append(('retriever.core', 'ok', True))
except Exception:
    checks.append(('retriever.core', 'IMPORT FAIL', False))

all_ok = all(ok for _, _, ok in checks)
for name, ver, ok in checks:
    status = 'ok' if ok else 'FAIL'
    print(f'  {status}: {name} {ver}')

sys.exit(0 if all_ok else 1)
" 2>&1) || {
    echo "$VERIFY"
    fail "Verification failed. See details above."
}

echo "$VERIFY"
info "All checks passed"

# ══════════════════════════════════════════════════════════════
# PHASE 2: Data Ingestion
# ══════════════════════════════════════════════════════════════

CONVERSATIONS="$PROJ_ROOT/data/conversations.json"
CHUNKS="$PROJ_ROOT/data/chunks.json"
VECTOR_STORE="$PROJ_ROOT/data/vector_store"

if [ ! -f "$CONVERSATIONS" ]; then
    # ── No data file yet — pause and tell user what to do ─────
    printf "\n"
    printf "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
    printf "${YELLOW}${BOLD}  Environment ready! Data file not found yet.${RESET}\n"
    printf "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
    printf "\n"
    printf "  ${BOLD}1.${RESET} Export your ChatGPT data:\n"
    printf "     ChatGPT → Settings → Data Controls → Export Data\n"
    printf "     ${DIM}(you'll receive an email with a download link)${RESET}\n"
    printf "\n"
    printf "  ${BOLD}2.${RESET} Place ${BOLD}conversations.json${RESET} in:\n"
    printf "     ${BOLD}%s/data/${RESET}\n" "$PROJ_ROOT"
    printf "\n"
    printf "  ${BOLD}3.${RESET} Re-run this script:\n"
    printf "     ${BOLD}bash scripts/install.sh${RESET}\n"
    printf "     ${DIM}(it will skip the install and jump straight to ingestion)${RESET}\n"
    printf "\n"
    exit 0
fi

# ── Step 7: Parse conversations ───────────────────────────────
if [ -f "$CHUNKS" ]; then
    CHUNK_COUNT=$(python -c "import json; print(len(json.load(open('$CHUNKS'))))" 2>/dev/null || echo "0")
    step "Parsing conversations"
    warn "chunks.json already exists ($CHUNK_COUNT chunks) — skipping parse"
    warn "To re-parse: rm data/chunks.json && re-run this script"
else
    step "Parsing conversations"
    info "Found conversations.json — parsing into chunks"

    python -m scripts.parser \
        --input "$CONVERSATIONS" \
        --output "$CHUNKS" \
    || fail "Parser failed. Check that data/conversations.json is a valid ChatGPT export."

    CHUNK_COUNT=$(python -c "import json; print(len(json.load(open('$CHUNKS'))))" 2>/dev/null || echo "?")
    info "Parsed $CHUNK_COUNT chunks into data/chunks.json"
fi

# ── Step 8: Embed and index ───────────────────────────────────
if [ -d "$VECTOR_STORE" ]; then
    step "Embedding and indexing"
    warn "Vector store already exists at data/vector_store/ — skipping indexing"
    warn "To rebuild: rm -rf data/vector_store && re-run this script"
else
    step "Embedding and indexing"
    info "Building vector store — this takes a while on first run"
    printf "${DIM}  (~45 minutes for 30k+ chunks — the embedding model runs locally)${RESET}\n"
    printf "\n"

    python -m scripts.embed_and_index \
        --input "$CHUNKS" \
        --db-path "$VECTOR_STORE" \
        --reset \
    || fail "Embedding/indexing failed. Check the output above for errors."

    info "Vector store built at data/vector_store/"
fi

# ══════════════════════════════════════════════════════════════
# PHASE 3: Connect to Claude Desktop
# ══════════════════════════════════════════════════════════════

# Detect OS and generate the correct MCP config.
#
# Why a bash wrapper instead of "cwd"?
# Claude Desktop may strip the "cwd" field from the config on some
# platforms. The bash wrapper embeds the cd into the command itself,
# so the working directory is always correct regardless of how Claude
# Desktop handles the config.

IS_WSL=false
IS_MACOS=false
IS_LINUX=false

if [ -f /proc/version ] && grep -qi microsoft /proc/version 2>/dev/null; then
    IS_WSL=true
elif [ "$(uname -s)" = "Darwin" ]; then
    IS_MACOS=true
else
    IS_LINUX=true
fi

printf "\n"
printf "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
printf "${GREEN}${BOLD}  Chronicle Beta is ready!${RESET}\n"
printf "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
printf "\n"
printf "  ${BOLD}Last step — connect to Claude Desktop:${RESET}\n"
printf "  Add the ${BOLD}mcpServers${RESET} block below to your ${BOLD}claude_desktop_config.json${RESET}.\n"
printf "  ${DIM}(Merge it into the existing file — don't create a second JSON object.)${RESET}\n"
printf "\n"

if [ "$IS_WSL" = true ]; then
    printf '     "mcpServers": {\n'
    printf '       "chronicle": {\n'
    printf '         "command": "wsl.exe",\n'
    printf '         "args": [\n'
    printf '           "bash", "-lc",\n'
    printf '           "cd %s && %s -m mcp_server.server"\n' "$PROJ_ROOT" "$VENV_DIR/bin/python"
    printf '         ],\n'
    printf '         "env": {\n'
    printf '           "CHRONICLE_NONINTERACTIVE": "1",\n'
    printf '           "TOKENIZERS_PARALLELISM": "false"\n'
    printf '         }\n'
    printf '       }\n'
    printf '     }\n'
elif [ "$IS_MACOS" = true ] || [ "$IS_LINUX" = true ]; then
    printf '     "mcpServers": {\n'
    printf '       "chronicle": {\n'
    printf '         "command": "/bin/bash",\n'
    printf '         "args": ["-c", "cd %s && %s -m mcp_server.server"],\n' "$PROJ_ROOT" "$VENV_DIR/bin/python"
    printf '         "env": {\n'
    printf '           "CHRONICLE_NONINTERACTIVE": "1",\n'
    printf '           "TOKENIZERS_PARALLELISM": "false"\n'
    printf '         }\n'
    printf '       }\n'
    printf '     }\n'
fi

printf "\n"
printf "  ${BOLD}Then:${RESET}\n"
printf "     1. Fully quit Claude Desktop (not just close the window)\n"
printf "     2. Reopen Claude Desktop\n"
printf "     3. Ask Claude: ${DIM}\"Use chronicle health_check\"${RESET}\n"
printf "\n"

if [ "$IS_WSL" = true ]; then
    printf "${DIM}  Finding your config file (run in PowerShell, not WSL):${RESET}\n"
    printf "${DIM}    Get-ChildItem \$env:APPDATA, \$env:LOCALAPPDATA -Recurse -Filter \"claude_desktop_config.json\" -ErrorAction SilentlyContinue${RESET}\n"
elif [ "$IS_MACOS" = true ]; then
    printf "${DIM}  Config file:${RESET}\n"
    printf "${DIM}    ~/Library/Application Support/Claude/claude_desktop_config.json${RESET}\n"
    printf "${DIM}  Open it with: nano ~/Library/Application\\ Support/Claude/claude_desktop_config.json${RESET}\n"
elif [ "$IS_LINUX" = true ]; then
    printf "${DIM}  Config file:${RESET}\n"
    printf "${DIM}    ~/.config/Claude/claude_desktop_config.json${RESET}\n"
fi

printf "\n"
printf "${DIM}  Full setup guide: https://github.com/AnirudhB-6001/chronicle_beta/blob/main/docs/QUICKSTART.md${RESET}\n"
printf "\n"