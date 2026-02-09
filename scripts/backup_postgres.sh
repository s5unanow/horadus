#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
OUTPUT_DIR="${OUTPUT_DIR:-./backups}"
POSTGRES_USER="${POSTGRES_USER:-geoint}"
POSTGRES_DB="${POSTGRES_DB:-geoint}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
BACKUP_RETENTION_COUNT="${BACKUP_RETENTION_COUNT:-30}"
VERIFY_BACKUP="${VERIFY_BACKUP:-true}"
MIN_BACKUP_BYTES="${MIN_BACKUP_BYTES:-1024}"

timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
mkdir -p "${OUTPUT_DIR}"
backup_path="${OUTPUT_DIR}/horadus_${timestamp}.sql.gz"
checksum_path="${backup_path}.sha256"

docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  | gzip -9 > "${backup_path}"

if [[ "${VERIFY_BACKUP}" == "true" ]]; then
  gzip -t "${backup_path}"
  backup_size="$(wc -c < "${backup_path}")"
  if [[ "${backup_size}" -lt "${MIN_BACKUP_BYTES}" ]]; then
    echo "Backup is suspiciously small (${backup_size} bytes < ${MIN_BACKUP_BYTES})." >&2
    exit 1
  fi
fi

shasum -a 256 "${backup_path}" > "${checksum_path}"

if [[ "${BACKUP_RETENTION_DAYS}" -gt 0 ]]; then
  while IFS= read -r expired_file; do
    [[ -z "${expired_file}" ]] && continue
    rm -f "${expired_file}" "${expired_file}.sha256"
  done < <(find "${OUTPUT_DIR}" -type f -name "horadus_*.sql.gz" -mtime +"${BACKUP_RETENTION_DAYS}")
fi

if [[ "${BACKUP_RETENTION_COUNT}" -gt 0 ]]; then
  mapfile -t all_backups < <(
    find "${OUTPUT_DIR}" -type f -name "horadus_*.sql.gz" -print | sort -r
  )
  if [[ "${#all_backups[@]}" -gt "${BACKUP_RETENTION_COUNT}" ]]; then
    for old_backup in "${all_backups[@]:${BACKUP_RETENTION_COUNT}}"; do
      rm -f "${old_backup}" "${old_backup}.sha256"
    done
  fi
fi

echo "Backup created: ${backup_path}"
echo "Checksum written: ${checksum_path}"
