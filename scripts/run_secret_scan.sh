#!/usr/bin/env bash
set -euo pipefail

UV_BIN="${UV_BIN:-uv}"

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

exec "${UV_BIN}" run --no-sync python scripts/check_secret_baseline.py
