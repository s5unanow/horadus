#!/usr/bin/env bash
set -euo pipefail

pr_branch="${PR_BRANCH:-}"
pr_title="${PR_TITLE:-}"
pr_body="${PR_BODY:-}"

if [[ -z "${pr_branch}" ]]; then
  echo "PR scope guard failed: PR_BRANCH is required."
  exit 1
fi

branch_pattern='^codex/task-([0-9]{3})-[a-z0-9][a-z0-9._-]*$'

if [[ ! "${pr_branch}" =~ ${branch_pattern} ]]; then
  cat <<EOF
PR scope guard failed.
Branch '${pr_branch}' does not match required task branch pattern:
  codex/task-XXX-short-name
EOF
  exit 1
fi

branch_task_id="TASK-${BASH_REMATCH[1]}"

metadata_task_ids="$(
  printf '%s\n%s\n' "${pr_title}" "${pr_body}" \
    | grep -Eo 'TASK-[0-9]{3}' \
    | sort -u || true
)"

metadata_count="$(printf '%s\n' "${metadata_task_ids}" | sed '/^$/d' | wc -l | tr -d ' ')"

if [[ "${metadata_count}" -eq 0 ]]; then
  echo "PR scope guard failed: PR title/body must include TASK-XXX (missing task ID)."
  exit 1
fi

if [[ "${metadata_count}" -gt 1 ]]; then
  cat <<EOF
PR scope guard failed: multiple task IDs found in PR title/body.
Found:
${metadata_task_ids}
EOF
  exit 1
fi

metadata_task_id="$(printf '%s\n' "${metadata_task_ids}" | sed '/^$/d' | head -n 1)"

if [[ "${metadata_task_id}" != "${branch_task_id}" ]]; then
  cat <<EOF
PR scope guard failed: branch task ID and PR task ID mismatch.
Branch task: ${branch_task_id}
PR task:     ${metadata_task_id}
EOF
  exit 1
fi

echo "PR scope guard passed: ${branch_task_id}"
