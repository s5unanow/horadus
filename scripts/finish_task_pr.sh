#!/usr/bin/env bash
set -euo pipefail

# Compatibility wrapper. The canonical task completion engine is:
#   uv run --no-sync horadus tasks finish [TASK-XXX]

UV_BIN="${UV_BIN:-uv}"

exec "${UV_BIN}" run --no-sync horadus tasks finish "$@"
