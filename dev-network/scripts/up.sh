#!/usr/bin/env bash
# Bring up the dev network for a scenario (default: healthy). Idempotent: a no-op
# if the server is already running (AGENTS.md §5).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCENARIO="${SCENARIO:-healthy}"
cd "$REPO_ROOT"
exec uv run python dev-network/scripts/devnet.py up --scenario "$SCENARIO" "$@"
