#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-./backups}"
MAX_BACKUP_AGE_HOURS="${MAX_BACKUP_AGE_HOURS:-30}"
MIN_BACKUP_BYTES="${MIN_BACKUP_BYTES:-1024}"

latest_backup="$(find "${OUTPUT_DIR}" -type f -name "horadus_*.sql.gz" -print | sort -r | head -n 1)"
if [[ -z "${latest_backup}" ]]; then
  echo "No backups found in ${OUTPUT_DIR}" >&2
  exit 1
fi

if stat -f %m "${latest_backup}" >/dev/null 2>&1; then
  modified_epoch="$(stat -f %m "${latest_backup}")"
else
  modified_epoch="$(stat -c %Y "${latest_backup}")"
fi

now_epoch="$(date +%s)"
age_hours="$(( (now_epoch - modified_epoch) / 3600 ))"
if [[ "${age_hours}" -gt "${MAX_BACKUP_AGE_HOURS}" ]]; then
  echo "Latest backup is stale (${age_hours}h > ${MAX_BACKUP_AGE_HOURS}h)." >&2
  exit 1
fi

gzip -t "${latest_backup}"
backup_size="$(wc -c < "${latest_backup}")"
if [[ "${backup_size}" -lt "${MIN_BACKUP_BYTES}" ]]; then
  echo "Latest backup is suspiciously small (${backup_size} bytes < ${MIN_BACKUP_BYTES})." >&2
  exit 1
fi

checksum_path="${latest_backup}.sha256"
if [[ -f "${checksum_path}" ]]; then
  expected_hash="$(awk '{print $1}' "${checksum_path}")"
  actual_hash="$(shasum -a 256 "${latest_backup}" | awk '{print $1}')"
  if [[ "${expected_hash}" != "${actual_hash}" ]]; then
    echo "Checksum mismatch for ${latest_backup}" >&2
    exit 1
  fi
fi

echo "Backup verification passed: ${latest_backup}"
