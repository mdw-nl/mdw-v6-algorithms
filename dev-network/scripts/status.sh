#!/usr/bin/env bash
# Report what's running in the dev network.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"
exec uv run python dev-network/scripts/devnet.py status "$@"
