#!/usr/bin/env bash
set -euo pipefail

# Canonical measured-coverage gate for repo workflow surfaces.
#
# Testability hook:
# - HORADUS_UNIT_COVERAGE_GATE_CMD="..." to replace the default pytest command

if [[ -n "${HORADUS_UNIT_COVERAGE_GATE_CMD:-}" ]]; then
  echo "unit-coverage: running overridden coverage gate command"
  bash -lc "${HORADUS_UNIT_COVERAGE_GATE_CMD}"
  exit 0
fi

UV_BIN="${UV_BIN:-uv}"

echo "unit-coverage: enforcing 100% measured coverage for src/, tools/, and scripts/"
exec "${UV_BIN}" run --no-sync pytest tests/unit/ tests/horadus_cli/ tests/workflow/ -v \
  --cov=src \
  --cov=tools \
  --cov=scripts \
  --cov-report=term-missing:skip-covered \
  --cov-fail-under=100
