#!/usr/bin/env bash
# Tag and push a locally built image to the dev network's local registry.
# Usage: push_image.sh IMAGE_NAME [TAG]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
IMAGE="${1:?Usage: push_image.sh IMAGE_NAME [TAG]}"
TAG="${2:-dev}"
cd "$REPO_ROOT"
exec uv run python dev-network/scripts/devnet.py push-image --image "$IMAGE" --tag "$TAG"
