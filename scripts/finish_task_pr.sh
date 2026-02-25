#!/usr/bin/env bash
set -euo pipefail

# Finish the "full lifecycle" for the current task branch:
# - validate branch + clean tree
# - validate PR scope metadata (Primary-Task matches branch task)
# - wait for checks
# - squash-merge + delete remote branch
# - sync local main and verify merge commit exists locally

GH_BIN="${GH_BIN:-gh}"
GIT_BIN="${GIT_BIN:-git}"

CHECKS_TIMEOUT_SECONDS="${CHECKS_TIMEOUT_SECONDS:-1800}" # 30 minutes
CHECKS_POLL_SECONDS="${CHECKS_POLL_SECONDS:-10}"

require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "task-finish failed: missing required command '${cmd}'."
    exit 1
  fi
}

require_cmd "${GH_BIN}"
require_cmd "${GIT_BIN}"

current_branch="$("${GIT_BIN}" rev-parse --abbrev-ref HEAD)"
if [[ "${current_branch}" == "HEAD" ]]; then
  echo "task-finish failed: detached HEAD is not allowed."
  exit 1
fi
if [[ "${current_branch}" == "main" ]]; then
  echo "task-finish failed: refusing to run on 'main'."
  exit 1
fi

branch_pattern='^codex/task-([0-9]{3})-[a-z0-9][a-z0-9._-]*$'
if [[ ! "${current_branch}" =~ ${branch_pattern} ]]; then
  cat <<EOF
task-finish failed: branch does not match required task branch pattern:
  codex/task-XXX-short-name
Current branch: ${current_branch}
EOF
  exit 1
fi

if [[ -n "$("${GIT_BIN}" status --porcelain)" ]]; then
  echo "task-finish failed: working tree must be clean."
  exit 1
fi

# Validate PR exists for current branch and its scope metadata matches.
if ! pr_body="$("${GH_BIN}" pr view --json body --jq .body 2>/dev/null)"; then
  echo "task-finish failed: unable to locate PR for current branch (${current_branch})."
  echo "Ensure you have pushed the branch and opened a PR."
  exit 1
fi

PR_BRANCH="${current_branch}" PR_BODY="${pr_body}" ./scripts/check_pr_task_scope.sh

pr_url="$("${GH_BIN}" pr view --json url --jq .url)"
echo "PR: ${pr_url}"

if [[ "$("${GH_BIN}" pr view --json isDraft --jq .isDraft)" == "true" ]]; then
  echo "task-finish failed: PR is draft; refusing to merge."
  exit 1
fi

echo "Waiting for PR checks to pass (timeout=${CHECKS_TIMEOUT_SECONDS}s)..."
deadline="$(( $(date +%s) + CHECKS_TIMEOUT_SECONDS ))"
while true; do
  if "${GH_BIN}" pr checks --required >/dev/null 2>&1; then
    break
  fi
  now="$(date +%s)"
  if (( now >= deadline )); then
    echo "task-finish failed: checks did not pass before timeout."
    "${GH_BIN}" pr checks --required || true
    exit 1
  fi
  sleep "${CHECKS_POLL_SECONDS}"
done

echo "Merging PR (squash, delete branch)..."
if ! "${GH_BIN}" pr merge --squash --delete-branch; then
  echo "task-finish failed: merge failed."
  exit 1
fi

merge_commit="$("${GH_BIN}" pr view --json mergeCommit --jq .mergeCommit.oid)"
if [[ -z "${merge_commit}" || "${merge_commit}" == "null" ]]; then
  echo "task-finish failed: could not determine merge commit."
  exit 1
fi

echo "Syncing main..."
"${GIT_BIN}" switch main
"${GIT_BIN}" pull --ff-only

if ! "${GIT_BIN}" cat-file -e "${merge_commit}" 2>/dev/null; then
  echo "task-finish failed: merge commit not found locally after pull: ${merge_commit}"
  exit 1
fi

echo "task-finish passed: merged ${merge_commit} and synced main."
