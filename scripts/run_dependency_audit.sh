#!/usr/bin/env bash
set -euo pipefail

UV_BIN="${UV_BIN:-uv}"

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

requirements_file="$(mktemp)"
trap 'rm -f "${requirements_file}"' EXIT

"${UV_BIN}" export \
  --frozen \
  --extra dev \
  --format requirements-txt \
  --no-hashes \
  --no-emit-project \
  -o "${requirements_file}" >/dev/null

echo "dependency-audit: auditing the exported frozen dependency set for known vulnerabilities"
"${UV_BIN}" run --no-sync python -m pip_audit -r "${requirements_file}" --strict --progress-spinner off
