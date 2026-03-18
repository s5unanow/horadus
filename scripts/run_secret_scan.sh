#!/usr/bin/env bash
set -euo pipefail

UV_BIN="${UV_BIN:-uv}"

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

tracked_files=()
while IFS= read -r -d '' file; do
  tracked_files+=("${file}")
done < <(git ls-files -z -- . ':(exclude).secrets.baseline')

if [[ "${#tracked_files[@]}" -eq 0 ]]; then
  echo "secret-scan: no tracked files to scan."
  exit 0
fi

echo "secret-scan: scanning tracked files against .secrets.baseline"
exec "${UV_BIN}" run --no-sync python -m detect_secrets.pre_commit_hook \
  --baseline .secrets.baseline \
  --no-verify \
  --exclude-files '(^docs/|^tasks/|^ai/eval/baselines/|\.env\.example$)' \
  "${tracked_files[@]}"
