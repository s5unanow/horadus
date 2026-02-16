#!/usr/bin/env bash
set -euo pipefail

if [[ "${SKIP_BRANCH_GUARD:-0}" == "1" ]]; then
  echo "Branch guard skipped (SKIP_BRANCH_GUARD=1)."
  exit 0
fi

branch_name="$(git rev-parse --abbrev-ref HEAD)"
branch_pattern='^codex/task-[0-9]{3}-[a-z0-9][a-z0-9._-]*$'

if [[ "${branch_name}" == "HEAD" ]]; then
  echo "Branch guard failed: detached HEAD is not allowed for task commits/pushes."
  exit 1
fi

if [[ ! "${branch_name}" =~ ${branch_pattern} ]]; then
  cat <<EOF
Branch guard failed.
Current branch: ${branch_name}
Expected pattern: codex/task-XXX-short-name
Example: codex/task-110-workflow-guards

Create/checkout a dedicated task branch before commit/push.
EOF
  exit 1
fi

echo "Branch guard passed: ${branch_name}"
