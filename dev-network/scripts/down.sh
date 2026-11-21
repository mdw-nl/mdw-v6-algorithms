#!/usr/bin/env bash
# Stop and clean up the dev network (server, store, nodes, UI, registry).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"
exec uv run python dev-network/scripts/devnet.py down "$@"
