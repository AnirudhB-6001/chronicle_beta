# Troubleshooting

Organized by what you see. Find your error, follow the fix.

---

## Installation

### "Python 3.10+ is required but not found"

**Cause:** 

The install script can't find a Python version ≥ 3.10 in your PATH. This usually happens on macOS after installing Python via Homebrew.

Homebrew puts Python in `/opt/homebrew/bin/` but your shell may still find the older system Python first.

**Fix (macOS):**
```bash
echo 'export PATH="/opt/homebrew/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
python3 --version   # should now show 3.10+
```

**Fix (Linux):** Check which Python is active with `which python3`. If it points to an old version, install a newer one with your package manager:
```bash
# Debian/Ubuntu
sudo apt install python3.12 python3.12-venv

# Fedora
sudo dnf install python3.12
```

Then re-run `bash scripts/install.sh`.

---

### "command not found: brew" (macOS)

**Cause:** Homebrew was installed but not added to your PATH. The Homebrew installer prints "Next steps" commands after installation.**These must be run.**

**Fix:**
```bash
eval "$(/opt/homebrew/bin/brew shellenv)"
```

To make it permanent:
```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
```

If unsure, close Terminal completely (⌘ + Q) and reopen it.

---

### python3 shows an old version after installing a new one

**Cause:** The system Python (typically 3.9.6 from Xcode Command Line Tools) is earlier in your PATH than the Homebrew or manually installed version.

**Fix (macOS):**
```bash
echo 'export PATH="/opt/homebrew/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
python3 --version
```

**Fix (Linux):**
```bash
which -a python3
```
This shows all Python 3 binaries in PATH order. The first one wins. Either adjust your PATH or use the full path to the correct version.

---

### First run downloads ~2 GB

**Not an error.** sentence-transformers requires PyTorch, which is a large download. This is normal and only happens once. If the download times out, re-run `bash scripts/install.sh` — pip caches partial downloads and will resume.

---

### pip install fails with "[Errno 5] Input/output error" on WSL

**Cause:** WSL has a known issue writing to NTFS-mounted filesystems (`/mnt/c/`). Large pip operations can trigger I/O errors during file installation or cleanup.

**Fix:** Re-run the install script. If dependencies were partially installed, the script detects them via import checks and skips the pip step entirely. If you consistently hit this error, consider cloning the repo inside the WSL filesystem (`~/Projects/`) instead of on the Windows mount (`/mnt/c/`).

---

### "error: externally-managed-environment"

**Cause:** Your system Python is configured to block global pip installs (common on recent Ubuntu, Fedora, and macOS). This should not happen with Chronicle's install script because it creates a virtual environment first.

**Fix:** If you see this, you're likely running pip outside the venv. Let the install script handle everything:
```bash
bash scripts/install.sh
```

Do not run `pip install` manually unless you've activated the venv first (`source venv/bin/activate`).

---

### "No module named 'scripts.parser'"

**Cause:** You're not in the chronicle_beta project directory. Python needs to find the `scripts` package relative to the project root.

**Fix:**
```bash
cd ~/Projects/chronicle_beta   # or wherever you cloned it
bash scripts/install.sh
```

---

### "BackendUnavailable" during pip install

**Cause:** The `pyproject.toml` build backend is misconfigured. This was fixed in commit `bb2125b`

If you're on an older version or a fork, the build backend may still point to `setuptools.backends._legacy:_Backend` instead of the standard `setuptools.build_meta`.

**Fix:** Pull the latest version:
```bash
git pull origin main
bash scripts/install.sh
```

---

## Ingestion

### Indexing takes a long time

**Not an error.** Embedding 30k+ chunks runs the all-MiniLM-L6-v2 model locally on your CPU. Expected times:

| Hardware | ~30k chunks |
|----------|-------------|
| Apple Silicon (M1/M2/M3) | 5–10 minutes |
| Modern x86 laptop | 15–30 minutes |
| Older hardware or WSL on HDD | 30–60 minutes |

The install script shows a progress bar. 

---

### Parser fails on conversations.json

**Cause:** The file may not be a valid ChatGPT export, or it may be corrupted or truncated.

**Checks:**
1. Verify the file is valid JSON: `python3 -c "import json; json.load(open('data/conversations.json'))"`
2. Verify it's a ChatGPT export (should be a JSON array of conversation objects)
3. Make sure you unzipped the export. ChatGPT sends a zip file, and `conversations.json` is inside it

---

### KeyError during parsing

**Cause:** ChatGPT may have changed their export schema. The parser expects specific keys (`title`, `mapping`, `message`, `author`, `content`, `parts`). If ChatGPT restructures their export format, the parser may hit missing keys.

**Fix (temporary):** Open an issue on GitHub with the error message and the structure of one conversation object from your export (redact personal content). This helps us update the parser.

**Fix (structural):** This is tracked in the Phase 2 roadmap as "Input Validation Hardening". Replacing KeyErrors with clear messages about what changed.

---

## MCP Connection

### Claude Desktop doesn't show Chronicle tools

**Cause:** Claude Desktop was not fully restarted after editing the config file. Closing the window does not quit the app. It stays running in the background.

**Fix:**
- **macOS:** Press ⌘ + Q to fully quit, then reopen
- **Windows:** Right-click the Claude icon in the system tray -> Quit, then reopen
- **Linux:** Fully close the application process

Also verify the config file is in the right location. Claude Desktop may change the config path after updates.

---

### "Could not load app settings" after editing config

**Cause:** The JSON in `claude_desktop_config.json` is malformed.

**Common mistakes:**

1. **Two root-level objects.** You pasted the MCP config as a second JSON block after the existing one. JSON allows only one root object. The `mcpServers` block must be merged inside the existing `{ }`.

   Wrong:
   ```json
   { "preferences": { ... } }
   { "mcpServers": { ... } }
   ```

   Correct:
   ```json
   {
     "preferences": { ... },
     "mcpServers": { ... }
   }
   ```

2. **Trailing comma.** JSON does not allow a comma after the last item in an object.

3. **Rich Text formatting.** On macOS, TextEdit may save the file as Rich Text (.rtf), inserting invisible formatting characters. Use `nano` in Terminal instead:
   ```bash
   nano ~/Library/Application\ Support/Claude/claude_desktop_config.json
   ```

**Validation:** Paste your config into [jsonlint.com](https://jsonlint.com/) to check for syntax errors.

---

### health_check returns "degraded" with a path error

**Cause:** The MCP server started in the wrong directory and can't find `data/vector_store`.

**Background:** Claude Desktop may strip the `cwd` field from the config file when it loads. Without `cwd`, the server starts at `/` (root) and ChromaDB can't find the data directory.

**Fix:** The install script (after the March 12 update) generates a bash wrapper that embeds the `cd` into the command itself, avoiding the `cwd` issue. If you're using an older config format with a `cwd` field, replace it with the wrapper format.

macOS / Linux:
```json
{
  "command": "/bin/bash",
  "args": ["-c", "cd /path/to/chronicle_beta && /path/to/venv/bin/python -m mcp_server.server"],
  "env": {
    "CHRONICLE_NONINTERACTIVE": "1",
    "TOKENIZERS_PARALLELISM": "false"
  }
}
```

WSL:
```json
{
  "command": "wsl.exe",
  "args": ["bash", "-lc", "cd /path/to/chronicle_beta && /path/to/venv/bin/python -m mcp_server.server"],
  "env": {
    "CHRONICLE_NONINTERACTIVE": "1",
    "TOKENIZERS_PARALLELISM": "false"
  }
}
```

Re-run `bash scripts/install.sh` to get the correct config block with your actual paths.

---

### health_check returns "degraded" with "Read-only file system"

**Cause:** ChromaDB needs write access to the vector store directory (for lock files and index updates). On WSL, the `/mnt/c/` mount can sometimes become read-only.

**Fix:**
```bash
mount | grep mnt/c
```

If the output shows `ro` (read-only), you need to remount:
```bash
sudo mount -o remount,rw /mnt/c
```

Or check your `/etc/wsl.conf` for mount options. If this recurs, consider moving the project to the WSL filesystem (`~/Projects/`) instead of the Windows mount.

Also check permissions on the data directory:
```bash
ls -la data/vector_store/
```

---

### health_check returns "degraded" with "RustBindingsAPI" error

**Cause:** ChromaDB version mismatch. The Rust bindings inside ChromaDB are broken, typically because of a partial upgrade or version conflict between the Python wrapper and the compiled Rust extension.

**Fix:**
```bash
cd ~/Projects/chronicle_beta   # or your project directory
source venv/bin/activate
pip uninstall chromadb -y
pip install chromadb==1.5.5
```

Then re-test:
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"health_check","arguments":{"probe_query":"test"}}}' | venv/bin/python -m mcp_server.server
```

---

### Can't find the Claude Desktop config file

The config file location depends on your platform and how Claude Desktop was installed.

**macOS:**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```
Open it with:
```bash
nano ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

**Linux:**
```
~/.config/Claude/claude_desktop_config.json
```

**Windows (standard install):**
```
%APPDATA%\Claude\claude_desktop_config.json
```

**Windows (Store install):**
The path includes a package identifier. Find it with PowerShell:
```powershell
Get-ChildItem $env:APPDATA, $env:LOCALAPPDATA -Recurse -Filter "claude_desktop_config.json" -ErrorAction SilentlyContinue | Select-Object FullName
```

**After Claude Desktop updates:** The config file location may change, or the contents may be overwritten. After any Claude Desktop update, verify the config file still contains your MCP server entries.Ypu can always open an issue and we will resolve it asap. 

---

### Claude Desktop update overwrites config

**Cause:** Claude Desktop may overwrite `claude_desktop_config.json` during updates, removing MCP server entries and resetting to defaults.

**Fix:** Keep a backup of your working config. After any Claude Desktop update, check the file and restore your `mcpServers` block if needed.

On macOS:
```bash
cp ~/Library/Application\ Support/Claude/claude_desktop_config.json ~/claude_config_backup.json
```

---

## Platform Notes

### macOS

- **Homebrew PATH:** After installing Homebrew, you must run the "Next steps" commands it prints. If you miss them, Homebrew commands won't be found.
- **TextEdit and JSON:** TextEdit defaults to Rich Text mode, which corrupts JSON files. Use `nano` in Terminal or switch TextEdit to plain text (Format → Make Plain Text) before editing.
- **Xcode Command Line Tools:** Required before Homebrew or git will work. Install with `xcode-select --install`.
- **Python version:** The system Python (from Xcode CLT) is 3.9.6,  its too old for Chronicle. Install Python 3.10+ via Homebrew.

### WSL (Windows Subsystem for Linux)

- **Path format:** Use Linux paths (`/mnt/c/Users/...`), not Windows paths (`C:\Users\...`).
- **NTFS I/O errors:** pip install can fail on `/mnt/c/` due to NTFS filesystem limitations. Consider using the native WSL filesystem (`~/`) for the project.
- **Claude Desktop config:** The config file is on the Windows side. Edit it with PowerShell or a Windows text editor, not from within WSL.

### Windows Store Claude Desktop

- The config file lives in a different location than the standard install. Use the PowerShell search command above to find it.
- The package path includes a hash like `Claude_pzs8sxrjxfjjc`, this is normal.

---

## Debugging with the CLI

You can test the MCP server directly from the command line without Claude Desktop. This isolates whether the problem is Chronicle itself or the Claude Desktop connection.

**From the project directory, with the venv active:**

```bash
cd ~/Projects/chronicle_beta

echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"health_check","arguments":{"probe_query":"test"}}}' | venv/bin/python -m mcp_server.server
```

**Expected output:** Two JSON lines.

The first is the initialization response:
```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18","capabilities":{"tools":{"list":true,"call":true},...},"serverInfo":{"name":"chronicle-beta","version":"0.1.0"}}}
```

The second is the health check result. A working system shows:
```json
{
  "status": "ok",
  "probe": {
    "query": "test",
    "results_count": 3,
    "sample_titles": ["Some conversation title", ...]
  }
}
```

If `status` is `"degraded"`, the `probe.error` field tells you what went wrong.

**If the CLI test works but Claude Desktop doesn't:** The problem is in the Claude Desktop config, not Chronicle. Double-check the config file paths, JSON syntax, and make sure you've fully restarted Claude Desktop.

**If the CLI test also fails:** The problem is in Chronicle itself. Check the error message and look for matching symptoms above.
