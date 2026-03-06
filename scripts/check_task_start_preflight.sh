#!/usr/bin/env bash
set -euo pipefail

if [[ "${HORADUS_CLI_WRAPPER_SILENT:-0}" != "1" ]]; then
  echo "Deprecated wrapper: use 'uv run --no-sync horadus tasks preflight'." >&2
fi

uv run --no-sync horadus tasks preflight "$@"
