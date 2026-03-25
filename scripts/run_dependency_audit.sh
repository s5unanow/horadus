#!/usr/bin/env bash
set -euo pipefail

UV_BIN="${UV_BIN:-uv}"

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

"${UV_BIN}" run --no-sync python scripts/check_dependency_audit.py "${UV_BIN}"
