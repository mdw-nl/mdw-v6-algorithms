#!/usr/bin/env bash
# Wipe all dev-network state and recreate it from config (AGENTS.md §5).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCENARIO="${SCENARIO:-healthy}"
cd "$REPO_ROOT"
exec uv run python dev-network/scripts/devnet.py reset --scenario "$SCENARIO" "$@"
