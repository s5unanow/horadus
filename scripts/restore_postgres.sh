#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <dump.sql.gz>" >&2
  exit 1
fi

dump_path="$1"
if [[ ! -f "${dump_path}" ]]; then
  echo "Dump file not found: ${dump_path}" >&2
  exit 1
fi

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
POSTGRES_USER="${POSTGRES_USER:-geoint}"
POSTGRES_DB="${POSTGRES_DB:-geoint}"

gzip -dc "${dump_path}" | docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"

echo "Restore completed from: ${dump_path}"
