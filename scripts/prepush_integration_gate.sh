#!/usr/bin/env bash
set -euo pipefail

# Pre-push integration test gate.
#
# This is intentionally conservative: integration tests truncate all public
# tables, so we force a Docker-based ephemeral environment by default.
#
# Escape hatches:
# - HORADUS_SKIP_INTEGRATION_TESTS=1 (or SKIP_INTEGRATION_TESTS=1)
#
# Testability hooks:
# - HORADUS_INTEGRATION_PREPUSH_REQUIRE_DOCKER=false (skip docker daemon checks)
# - HORADUS_INTEGRATION_PREPUSH_CMD="..." (default: make test-integration-docker)

SKIP="${HORADUS_SKIP_INTEGRATION_TESTS:-${SKIP_INTEGRATION_TESTS:-}}"
if [[ "${SKIP}" == "1" ]] || [[ "${SKIP}" == "true" ]]; then
  echo "pre-push: skipping integration test gate (explicit skip env var set)"
  exit 0
fi

REQUIRE_DOCKER="${HORADUS_INTEGRATION_PREPUSH_REQUIRE_DOCKER:-true}"
RUNNER_CMD="${HORADUS_INTEGRATION_PREPUSH_CMD:-make test-integration-docker}"

if [[ "${REQUIRE_DOCKER}" == "true" ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "pre-push failed: docker is required for integration test gate." >&2
    echo "Start Docker Desktop or set HORADUS_SKIP_INTEGRATION_TESTS=1 to bypass." >&2
    exit 1
  fi

  if ! docker info >/dev/null 2>&1; then
    echo "pre-push failed: docker daemon not reachable." >&2
    echo "Start Docker Desktop or set HORADUS_SKIP_INTEGRATION_TESTS=1 to bypass." >&2
    exit 1
  fi
fi

echo "pre-push: running integration test gate..."
bash -lc "${RUNNER_CMD}"
