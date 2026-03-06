#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  cat <<EOF
Usage:
  ./scripts/start_task_branch.sh TASK-117 short-name
  ./scripts/start_task_branch.sh 117 short-name
EOF
  exit 1
fi

if [[ "${HORADUS_CLI_WRAPPER_SILENT:-0}" != "1" ]]; then
  echo "Deprecated wrapper: use 'uv run --no-sync horadus tasks start TASK-XXX --name short-name'." >&2
fi

task_input="$1"
shift
set +e
output="$(uv run --no-sync horadus tasks start "${task_input}" --name "$*" 2>&1)"
status=$?
set -e
printf '%s\n' "${output}"
if [[ ${status} -eq 0 ]]; then
  exit 0
fi
exit 1
