#!/usr/bin/env bash
set -euo pipefail

if [[ "${SKIP_TASK_SEQUENCE_GUARD:-0}" == "1" ]]; then
  echo "Task sequencing guard skipped (SKIP_TASK_SEQUENCE_GUARD=1)."
  exit 0
fi

if ! command -v gh >/dev/null 2>&1; then
  cat <<EOF
Task sequencing guard failed.
GitHub CLI (gh) is required for open-PR checks.
Install/auth gh or set SKIP_TASK_SEQUENCE_GUARD=1 for an explicit temporary bypass.
EOF
  exit 1
fi

current_branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "${current_branch}" != "main" ]]; then
  cat <<EOF
Task sequencing guard failed.
You must start tasks from 'main'.
Current branch: ${current_branch}
Run:
  git switch main
  git pull --ff-only
EOF
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  cat <<EOF
Task sequencing guard failed.
Working tree must be clean before starting a new task branch.
Commit/stash/discard local changes first.
EOF
  exit 1
fi

git fetch origin main --quiet
local_main_sha="$(git rev-parse HEAD)"
remote_main_sha="$(git rev-parse origin/main)"

if [[ "${local_main_sha}" != "${remote_main_sha}" ]]; then
  cat <<EOF
Task sequencing guard failed.
Local main is not synced to origin/main.
local : ${local_main_sha}
remote: ${remote_main_sha}
Run:
  git pull --ff-only
EOF
  exit 1
fi

if [[ "${ALLOW_OPEN_TASK_PRS:-0}" != "1" ]]; then
  if ! open_task_prs="$(
    gh pr list \
      --state open \
      --base main \
      --author "@me" \
      --search "head:codex/task-" \
      --limit 100 \
      --json number,headRefName,url \
      --jq '.[] | select(.headRefName | test("^codex/task-[0-9]{3}-")) | "#\(.number) \(.headRefName) \(.url)"'
  )"; then
    cat <<EOF
Task sequencing guard failed.
Unable to query open PRs via GitHub CLI.
Verify gh auth/connectivity or set ALLOW_OPEN_TASK_PRS=1 for an explicit temporary bypass.
EOF
    exit 1
  fi

  if [[ -n "${open_task_prs}" ]]; then
    cat <<EOF
Task sequencing guard failed.
Open non-merged task PR(s) already exist for current user:
${open_task_prs}

Merge/close existing task PRs before starting a new task.
To bypass explicitly once, set ALLOW_OPEN_TASK_PRS=1.
EOF
    exit 1
  fi
fi

echo "Task sequencing guard passed: main is clean/synced and no open task PRs."
