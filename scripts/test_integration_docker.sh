#!/usr/bin/env bash
set -euo pipefail

# Run integration tests against an ephemeral Dockerized Postgres+Redis stack.
#
# This avoids foot-guns with local dev DBs (e.g. DATABASE_URL pointing at "geoint")
# because integration tests truncate all public tables.
#
# Environment overrides:
# - INTEGRATION_DOCKER_POSTGRES_PORT (default: 55432)
# - INTEGRATION_DOCKER_REDIS_PORT (default: 56379)
# - INTEGRATION_DOCKER_DB_NAME (default: geoint_test)
# - INTEGRATION_DOCKER_POSTGRES_IMAGE (default: geoint-postgres:it)
# - INTEGRATION_DOCKER_FORCE_BUILD (default: false)
# - MIGRATION_GATE_VALIDATE_AUTOGEN (default: true)
# - OPENAI_API_KEY (optional; some integration paths read it)

POSTGRES_PORT="${INTEGRATION_DOCKER_POSTGRES_PORT:-55432}"
REDIS_PORT="${INTEGRATION_DOCKER_REDIS_PORT:-56379}"
DB_NAME="${INTEGRATION_DOCKER_DB_NAME:-geoint_test}"
POSTGRES_IMAGE="${INTEGRATION_DOCKER_POSTGRES_IMAGE:-geoint-postgres:it}"
FORCE_BUILD="${INTEGRATION_DOCKER_FORCE_BUILD:-false}"

POSTGRES_CONTAINER="${INTEGRATION_DOCKER_POSTGRES_CONTAINER:-geoint-postgres-it}"
REDIS_CONTAINER="${INTEGRATION_DOCKER_REDIS_CONTAINER:-geoint-redis-it}"

require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "integration-docker failed: missing required command '${cmd}'." >&2
    exit 1
  fi
}

require_cmd docker
require_cmd uv

cleanup() {
  docker rm -f "${POSTGRES_CONTAINER}" "${REDIS_CONTAINER}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Ensure a clean slate for idempotent re-runs.
cleanup

if [[ "${FORCE_BUILD}" == "true" ]] || ! docker image inspect "${POSTGRES_IMAGE}" >/dev/null 2>&1; then
  echo "Building Postgres image (${POSTGRES_IMAGE})..."
  docker build -t "${POSTGRES_IMAGE}" -f docker/postgres/Dockerfile docker/postgres
fi

echo "Starting Redis (${REDIS_CONTAINER}) on :${REDIS_PORT}..."
docker run -d \
  --name "${REDIS_CONTAINER}" \
  -p "${REDIS_PORT}:6379" \
  redis:7-alpine >/dev/null

echo "Starting Postgres (${POSTGRES_CONTAINER}) on :${POSTGRES_PORT} (db=${DB_NAME})..."
docker run -d \
  --name "${POSTGRES_CONTAINER}" \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB="${DB_NAME}" \
  -p "${POSTGRES_PORT}:5432" \
  -v "$(pwd)/docker/postgres/init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro" \
  "${POSTGRES_IMAGE}" >/dev/null

echo "Waiting for Postgres to be ready..."
for attempt in $(seq 1 30); do
  if docker exec "${POSTGRES_CONTAINER}" pg_isready -U postgres -d "${DB_NAME}" >/dev/null 2>&1; then
    break
  fi
  if [[ "${attempt}" -eq 30 ]]; then
    docker logs "${POSTGRES_CONTAINER}"
    echo "integration-docker failed: Postgres did not become ready in time." >&2
    exit 1
  fi
  sleep 2
done
sleep 2

echo "Verifying required Postgres extensions..."
installed_count="$(
  docker exec "${POSTGRES_CONTAINER}" \
    psql -U postgres -d "${DB_NAME}" \
    -tAc "SELECT count(*) FROM pg_extension WHERE extname IN ('timescaledb', 'vector');"
)"
if [[ "${installed_count}" -ne 2 ]]; then
  docker exec "${POSTGRES_CONTAINER}" \
    psql -U postgres -d "${DB_NAME}" \
    -c "SELECT extname, extversion FROM pg_extension ORDER BY extname;"
  echo "integration-docker failed: missing required extensions (expected timescaledb + vector)." >&2
  exit 1
fi

export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:${POSTGRES_PORT}/${DB_NAME}" # pragma: allowlist secret
export REDIS_URL="redis://localhost:${REDIS_PORT}/0"
export MIGRATION_GATE_VALIDATE_AUTOGEN="${MIGRATION_GATE_VALIDATE_AUTOGEN:-true}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-test-key}"

echo "Applying migrations..."
uv run --no-sync alembic upgrade head

echo "Running migration drift gate..."
./scripts/check_migration_drift.sh

echo "Running integration tests..."
uv run --no-sync pytest tests/integration/ -v -m integration
