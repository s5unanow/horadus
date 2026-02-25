#!/usr/bin/env bash
set -euo pipefail

tracked="$(git ls-files artifacts 2>/dev/null || true)"
if [[ -n "${tracked}" ]]; then
  cat <<EOF
Repo hygiene check failed: files under 'artifacts/' are tracked in git.

These should be generated/ephemeral. Remove them from the index:
  git rm -r --cached artifacts/

Tracked paths:
${tracked}
EOF
  exit 1
fi

echo "Repo hygiene check passed: no tracked artifacts/ paths."
