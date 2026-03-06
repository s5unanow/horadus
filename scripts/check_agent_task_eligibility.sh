#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  cat <<USAGE
Usage:
  ./scripts/check_agent_task_eligibility.sh TASK-XXX
USAGE
  exit 1
fi

if [[ "${HORADUS_CLI_WRAPPER_SILENT:-0}" != "1" ]]; then
  echo "Deprecated wrapper: use 'uv run --no-sync horadus tasks eligibility TASK-XXX'." >&2
fi

set +e
output="$(uv run --no-sync horadus tasks eligibility "$1" 2>&1)"
status=$?
set -e
printf '%s\n' "${output}"
if [[ ${status} -eq 0 ]]; then
  exit 0
fi
exit 1
