#!/usr/bin/env bash
set -euo pipefail

if [[ "${HORADUS_CLI_WRAPPER_SILENT:-0}" != "1" ]]; then
  echo "Deprecated wrapper: use 'uv run --no-sync horadus tasks preflight'." >&2
fi

set +e
output="$(uv run --no-sync horadus tasks preflight "$@" 2>&1)"
status=$?
set -e
printf '%s\n' "${output}"
if [[ ${status} -eq 0 ]]; then
  exit 0
fi
exit 1
