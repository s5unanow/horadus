#!/usr/bin/env bash
set -euo pipefail

DATABASE_URL_INPUT="${DATABASE_URL:-${1:-}}"
MIGRATION_GATE_VALIDATE_AUTOGEN="${MIGRATION_GATE_VALIDATE_AUTOGEN:-true}"

if [[ -z "${DATABASE_URL_INPUT}" ]]; then
  echo "DATABASE_URL is required (env var or first argument)." >&2
  exit 2
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required to run migration drift checks." >&2
  exit 2
fi

heads_output="$(uv run --no-sync alembic heads)"
head_revisions="$(printf "%s\n" "${heads_output}" | awk '/\(head\)/ {print $1}')"
head_count="$(printf "%s\n" "${head_revisions}" | sed '/^$/d' | wc -l | tr -d ' ')"

if [[ "${head_count}" -eq 0 ]]; then
  echo "Could not determine Alembic head revision." >&2
  exit 1
fi

if [[ "${head_count}" -gt 1 ]]; then
  echo "Multiple Alembic heads detected:" >&2
  printf "  %s\n" "${head_revisions}" >&2
  echo "Resolve migration branches before running this gate." >&2
  exit 1
fi

head_revision="$(printf "%s\n" "${head_revisions}" | head -n 1)"

current_output="$(
  DATABASE_URL="${DATABASE_URL_INPUT}" \
    uv run --no-sync alembic current
)"
current_revision="$(
  printf "%s\n" "${current_output}" | awk '/^[0-9A-Za-z_]+/ {print $1; exit}'
)"

if [[ -z "${current_revision}" ]]; then
  echo "Could not determine current Alembic revision for target database." >&2
  echo "Raw output:" >&2
  printf "%s\n" "${current_output}" >&2
  exit 1
fi

if [[ "${current_revision}" != "${head_revision}" ]]; then
  echo "Migration drift detected: current=${current_revision}, head=${head_revision}" >&2
  echo "Run: DATABASE_URL='<target-db-url>' uv run --no-sync alembic upgrade head" >&2
  exit 1
fi

echo "Migration revision parity OK: ${current_revision}"

if [[ "${MIGRATION_GATE_VALIDATE_AUTOGEN}" == "true" ]]; then
  DATABASE_URL="${DATABASE_URL_INPUT}" uv run --no-sync alembic check
  echo "Alembic autogenerate parity OK: no pending migration ops detected."
else
  echo "Skipped alembic autogenerate parity check (explicit bypass: MIGRATION_GATE_VALIDATE_AUTOGEN=false)."
fi
