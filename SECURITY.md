# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Chronicle Beta, please report it responsibly.

**Email:** anirudh.batra6001@gmail.com

**Please include:**
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

**Do not** open a public GitHub issue for security vulnerabilities.

I will acknowledge receipt within 48 hours and provide a timeline for a fix.

## Scope

Chronicle Beta runs entirely on your local machine. There are no network services, cloud endpoints, or remote APIs. The primary attack surface is:

- **Malicious input files** (crafted conversations.json designed to exploit the parser)
- **Dependency vulnerabilities** (in ChromaDB, sentence-transformers, or their transitive dependencies)
- **MCP protocol** (the stdio JSON-RPC interface between Chronicle and your LLM client)

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | Yes       |

## Security Design

- All data processing happens locally. No telemetry, no cloud calls, no API keys.
- The MCP server communicates via stdio only. It does not open network ports.
- User data directories (`data/`) are gitignored to prevent accidental commits.
- Input validation is applied to conversation imports to guard against malformed data.
