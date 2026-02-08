#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
OUTPUT_DIR="${OUTPUT_DIR:-./backups}"
POSTGRES_USER="${POSTGRES_USER:-geoint}"
POSTGRES_DB="${POSTGRES_DB:-geoint}"

timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
mkdir -p "${OUTPUT_DIR}"
backup_path="${OUTPUT_DIR}/horadus_${timestamp}.sql.gz"

docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  | gzip -9 > "${backup_path}"

echo "Backup created: ${backup_path}"
