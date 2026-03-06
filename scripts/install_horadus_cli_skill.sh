#!/usr/bin/env bash
set -euo pipefail

CODEX_HOME_RESOLVED="${CODEX_HOME:-$HOME/.codex}"
SKILL_SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)/ops/skills/horadus-cli"
SKILL_TARGET_DIR="${CODEX_HOME_RESOLVED}/skills/horadus-cli"

if [[ ! -d "${CODEX_HOME_RESOLVED}" ]]; then
  echo "Missing Codex home: ${CODEX_HOME_RESOLVED}"
  exit 1
fi

mkdir -p "${SKILL_TARGET_DIR}"
test -w "${SKILL_TARGET_DIR}"

rm -rf "${SKILL_TARGET_DIR:?}/"*
cp -R "${SKILL_SOURCE_DIR}/". "${SKILL_TARGET_DIR}/"

echo "Installed Horadus CLI skill to ${SKILL_TARGET_DIR}"
