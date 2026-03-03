#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  cat <<USAGE
Usage:
  ./scripts/run_with_backpressure.sh <label> <command> [args...]

Example:
  ./scripts/run_with_backpressure.sh ruff-check uv run --no-sync ruff check src/ tests/
USAGE
  exit 1
fi

label="$1"
shift

artifacts_dir="${ARTIFACTS_DIR:-artifacts/agent}"
mkdir -p "${artifacts_dir}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
slug="$(printf '%s' "${label}" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//')"
log_path="${artifacts_dir}/${timestamp}-${slug}.log"

# Keep only the newest 120 logs to avoid unbounded growth.
if ls "${artifacts_dir}"/*.log >/dev/null 2>&1; then
  ls -1t "${artifacts_dir}"/*.log | tail -n +121 | xargs -I{} rm -f "{}"
fi

echo "[agent] RUN ${label}"
if "$@" >"${log_path}" 2>&1; then
  echo "[agent] PASS ${label}"
  echo "[agent] log: ${log_path}"
  exit 0
fi

status=$?
echo "[agent] FAIL ${label} (exit ${status})"
echo "[agent] log: ${log_path}"
if command -v rg >/dev/null 2>&1; then
  rg -n "error|failed|traceback|exception|assert" "${log_path}" | tail -n 20 || true
else
  tail -n 40 "${log_path}" || true
fi
exit "${status}"
