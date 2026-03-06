#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  cat <<USAGE
Usage:
  ./scripts/task_context_pack.sh TASK-XXX
USAGE
  exit 1
fi

if [[ "${HORADUS_CLI_WRAPPER_SILENT:-0}" != "1" ]]; then
  echo "Deprecated wrapper: use 'uv run --no-sync horadus tasks context-pack TASK-XXX'." >&2
fi

uv run --no-sync horadus tasks context-pack "$1"
