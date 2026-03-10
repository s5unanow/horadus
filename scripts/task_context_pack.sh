#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  cat <<USAGE
Usage:
  ./scripts/task_context_pack.sh TASK-XXX [--include-archive]
USAGE
  exit 1
fi

extra_args=()
if [[ $# -eq 2 ]]; then
  if [[ "$2" != "--include-archive" ]]; then
    echo "Invalid second argument: $2" >&2
    exit 1
  fi
  extra_args+=("$2")
fi

if [[ "${HORADUS_CLI_WRAPPER_SILENT:-0}" != "1" ]]; then
  echo "Deprecated wrapper: use 'uv run --no-sync horadus tasks context-pack TASK-XXX'." >&2
fi

command=(uv run --no-sync horadus tasks context-pack "$1")
if [[ ${#extra_args[@]} -gt 0 ]]; then
  command+=("${extra_args[@]}")
fi

set +e
output="$("${command[@]}" 2>&1)"
status=$?
set -e
printf '%s\n' "${output}"
if [[ ${status} -eq 0 ]]; then
  exit 0
fi
exit 1
