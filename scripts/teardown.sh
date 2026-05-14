#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../docker"
docker compose -p mcp-sqlite-lab down -v --remove-orphans
echo "✓ Removed mcp-sqlite-lab containers, network, and volumes."
