#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  cat <<EOF
Usage:
  ./scripts/start_task_branch.sh TASK-117 short-name
  ./scripts/start_task_branch.sh 117 short-name
EOF
  exit 1
fi

task_input="$1"
shift
raw_slug="$*"

if [[ "${task_input}" =~ ^TASK-([0-9]{3})$ ]]; then
  task_num="${BASH_REMATCH[1]}"
elif [[ "${task_input}" =~ ^([0-9]{3})$ ]]; then
  task_num="${BASH_REMATCH[1]}"
else
  echo "Invalid task id '${task_input}'. Expected TASK-XXX or XXX."
  exit 1
fi

slug="$(printf '%s' "${raw_slug}" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//')"
if [[ -z "${slug}" ]]; then
  echo "Invalid branch suffix '${raw_slug}'."
  exit 1
fi

branch_name="codex/task-${task_num}-${slug}"

./scripts/check_task_start_preflight.sh

if git show-ref --verify --quiet "refs/heads/${branch_name}"; then
  echo "Branch already exists locally: ${branch_name}"
  exit 1
fi

if git ls-remote --exit-code --heads origin "${branch_name}" >/dev/null 2>&1; then
  echo "Branch already exists on origin: ${branch_name}"
  exit 1
fi

git switch -c "${branch_name}"
echo "Created task branch: ${branch_name}"
