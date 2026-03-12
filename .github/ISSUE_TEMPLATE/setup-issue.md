---
name: Setup Issue
about: Report a problem with installation, configuration, or environment setup
title: "[Setup] "
labels: setup
assignees: ''
---

**Describe the problem**
What went wrong during setup? Include the exact error message if you have one.

**Operating system**
- [ ] macOS (version: )
- [ ] Windows + WSL (Windows version: , WSL distro: )
- [ ] Linux (distro and version: )

**Python version**
Output of `python3 --version`:

**How was Python installed?**
- [ ] Homebrew
- [ ] System default
- [ ] python.org installer
- [ ] pyenv
- [ ] apt / dnf / package manager
- [ ] Other: 

**Which step failed?**
- [ ] Running `bash scripts/install.sh`
- [ ] Installing dependencies (pip install)
- [ ] Parsing conversations.json
- [ ] Embedding and indexing
- [ ] Connecting to Claude Desktop
- [ ] Running health_check
- [ ] Other: 

**Full error output**
Paste the terminal output starting from the last successful step. Include as much as possible.

```
(paste here)
```

**Steps already tried**
What have you done to try to fix it? (re-running the script, checking the troubleshooting guide, etc.)

**Additional context**
Anything else that might be relevant- unusual system configuration, corporate network, etc.
