# Quick Start Guide

Get Chronicle Beta running from scratch. Pick your operating system and follow the steps.

---

## Prerequisites

Before you begin, you need:

1. **A ChatGPT data export.** Go to ChatGPT -> Settings -> Data Controls -> Export Data. You'll receive an email with a download link. Unzip the archive. You need the `conversations.json` file inside it.

2. **Claude Desktop** installed on your machine. Download it from [claude.ai/download](https://claude.ai/download) if you don't have it.

3. **About 30–90 minutes.** Most of this is waiting for downloads and indexing.

---

## macOS

### Step 1  Open Terminal

Press **⌘ + Space** (Command + Space) to open Spotlight Search. Type `Terminal` and press Enter.

A window opens with a blinking cursor. This is where you'll run all the commands below. 

### Step 2 Install Xcode Command Line Tools

macOS needs developer tools before you can install anything. Run:

```bash
xcode-select --install
```

A popup appears. Click **Install**, then **Agree**. This downloads about 1.5 GB and takes 5–15 minutes.

When it finishes, verify:

```bash
xcode-select -p
```

Should print `/Library/Developer/CommandLineTools`.

### Step 3 Install Homebrew

Homebrew is the macOS package manager. Paste this into Terminal:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

It will ask for your Mac password (characters won't appear as you type, this is normal). Then press Enter to confirm.

**After installation, Homebrew will print "Next steps" with commands to run.** You must run them. They look like this:

```bash
echo >> /Users/YOURNAME/.zprofile
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> /Users/YOURNAME/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

Copy and run each line Homebrew prints. The paths will have your actual Mac username.

Verify Homebrew works:

```bash
brew --version
```

If it says "command not found", close Terminal (⌘ + Q) and reopen it.

### Step 4 Install Python

The system Python on macOS is too old. Install a current version:

```bash
brew install python@3.12
```

Verify it installed and is available:

```bash
python3 --version
```

If this still shows an old version (3.9.x), run:

```bash
echo 'export PATH="/opt/homebrew/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
python3 --version
```

You need Python 3.10 or higher to continue.

### Step 5 Clone and set up

```bash
mkdir -p ~/Projects
cd ~/Projects
git clone https://github.com/AnirudhB-6001/chronicle_beta.git
cd chronicle_beta
```

### Step 6 Place your data file

Copy `conversations.json` into the project's `data/` folder. If the file is in your Downloads folder:

```bash
cp ~/Downloads/conversations.json data/conversations.json
```

If the ChatGPT export was a zip file, unzip it first:

```bash
unzip ~/Downloads/*.zip -d ~/Downloads/chatgpt_export
cp ~/Downloads/chatgpt_export/conversations.json data/conversations.json
```

Verify the file is there:

```bash
ls -lh data/conversations.json
```

### Step 7 Run the install script

```bash
bash scripts/install.sh
```

The script handles everything: creates a virtual environment, installs dependencies (~2 GB download on first run), parses your conversations, embeds them into a local vector store, and prints the MCP config for Claude Desktop.

**This takes a while.** Dependency installation is 10–20 minutes. Embedding 30k+ chunks takes another 5–45 minutes depending on your machine. Don't close the Terminal window.

When it finishes, you'll see a green "Chronicle Beta is ready!" banner with a JSON config block.

### Step 8 Connect to Claude Desktop

The install script prints the config to add. On macOS, the config file is at:

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

Open the config file in Terminal:

```bash
nano ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

The file may already have content (like a `preferences` block). You need to add the `mcpServers` section printed by the install script **inside** the existing JSON object, not as a separate block after it. The result should be a single JSON object with both keys.

For example, if the file currently contains:

```json
{
  "preferences": {
    "coworkWebSearchEnabled": true
  }
}
```

It should become:

```json
{
  "preferences": {
    "coworkWebSearchEnabled": true
  },
  "mcpServers": {
    "chronicle": {
      ...config from install script...
    }
  }
}
```

Save the file (Ctrl + O, then Enter, then Ctrl + X to exit nano).

**Fully quit** Claude Desktop: press **⌘ + Q** (clicking the red close button only hides the window, it doesn't restart the app). Reopen Claude Desktop.

### Step 9 Verify

In Claude Desktop, ask:

> Use chronicle health_check

If it responds with `status: ok` and sample titles from your conversations, you're done.

---

## Windows (WSL)

Chronicle Beta runs inside WSL (Windows Subsystem for Linux) on Windows. The install script and all Python commands run in WSL, while Claude Desktop runs as a normal Windows app and talks to the WSL-based server.

### Step 1 Install WSL

Open PowerShell as Administrator (right-click the Start button -> Terminal (Admin)) and run:

```powershell
wsl --install
```

This installs Ubuntu by default. Restart your computer when prompted.

After restart, Ubuntu will open and ask you to create a username and password. These are for WSL only, not your Windows account.

If WSL is already installed, skip this step.

### Step 2 Install Python in WSL

Open your WSL terminal (search for "Ubuntu" in the Start menu). Run:

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
```

Verify:

```bash
python3 --version
```

You need Python 3.10 or higher.

### Step 3 Create a project directory and clone

```bash
mkdir -p ~/Projects
cd ~/Projects
git clone https://github.com/AnirudhB-6001/chronicle_beta.git
cd chronicle_beta
```

### Step 4 Place your data file

Your Windows filesystem is accessible from WSL at `/mnt/c/`. If `conversations.json` is in your Windows Downloads folder:

```bash
cp /mnt/c/Users/YOURNAME/Downloads/conversations.json data/conversations.json
```

Replace `YOURNAME` with your actual Windows username.

### Step 5 Run the install script

```bash
bash scripts/install.sh
```

This handles everything. Wait for the green "Chronicle Beta is ready!" banner.

### Step 6 Connect to Claude Desktop

Find your Claude Desktop config file. Open PowerShell (not WSL) and run:

```powershell
Get-ChildItem $env:APPDATA, $env:LOCALAPPDATA -Recurse -Filter "claude_desktop_config.json" -ErrorAction SilentlyContinue | Select-Object FullName
```

This prints the full path to your config file. Common locations:

| Install type | Path |
| --- | --- |
| Standard | `%APPDATA%\Claude\claude_desktop_config.json` |
| Windows Store | `AppData\Local\Packages\Claude_*\LocalCache\Roaming\Claude\claude_desktop_config.json` |

Open the config file and add the `mcpServers` block printed by the install script, merged into the existing JSON (same merge approach as described in the macOS section above).

Save, fully quit Claude Desktop (right-click the tray icon -> Quit), and reopen.

### Step 7 Verify

In Claude Desktop, ask:

> Use chronicle health_check

If it responds with `status: ok` and sample titles from your conversations, you're done.

---

## Linux

### Step 1 Install Python

On Debian/Ubuntu:

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
```

On Fedora:

```bash
sudo dnf install -y python3 python3-pip git
```

Verify Python 3.10+:

```bash
python3 --version
```

### Step 2 Clone and set up

```bash
mkdir -p ~/Projects
cd ~/Projects
git clone https://github.com/AnirudhB-6001/chronicle_beta.git
cd chronicle_beta
```

### Step 3 Place your data file

Copy `conversations.json` into `data/`:

```bash
cp /path/to/conversations.json data/conversations.json
```

### Step 4 Run the install script

```bash
bash scripts/install.sh
```

### Step 5 Connect to Claude Desktop

The config file on Linux is at:

```
~/.config/Claude/claude_desktop_config.json
```

Add the `mcpServers` block printed by the install script, merged into the existing JSON. Restart Claude Desktop.

### Step 6 Verify

> Use chronicle health_check

---

## Troubleshooting

If you hit any issues during setup, see the full [Troubleshooting Guide](TROUBLESHOOTING.md) - it covers installation failures, ingestion problems, MCP connection issues, and platform-specific notes for macOS, WSL, and Linux.

---

## Useful Terminal Commands

| Action | macOS / Linux | Windows (PowerShell) |
| --- | --- | --- |
| Open terminal | ⌘+Space -> "Terminal" | Start -> "Terminal" |
| List files | `ls` | `dir` |
| Change directory | `cd folder` | `cd folder` |
| Go home | `cd ~` | `cd $HOME` |
| Show current path | `pwd` | `pwd` |
| Copy file | `cp source dest` | `Copy-Item source dest` |
| Open folder in file manager | `open .` (macOS) | `explorer .` |
| Cancel running command | Ctrl + C | Ctrl + C |
| Paste in terminal | ⌘ + V (macOS) | Ctrl + V |
