#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Make sure deps are installed and resolve an absolute python path.
uv sync --quiet
PYTHON="$(uv run python -c 'import sys; print(sys.executable)')"

# Initialize the seed DB if it does not exist yet.
[ -f "$ROOT/lab.db" ] || uv run python implementation/init_db.py

NPM_CONFIG_CACHE="$ROOT/.npm-cache" npx -y @modelcontextprotocol/inspector \
    "$PYTHON" "$ROOT/implementation/mcp_server.py"
