#!/usr/bin/env bash
set -euo pipefail

pr_branch="${PR_BRANCH:-}"
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

normalize_pr_body() {
  local body="$1"
  local escaped_crlf='\\r\\n'
  local escaped_lf='\\n'

  # GitHub contexts can provide PR body with escaped newlines (`\n`) as a
  # single-line string. Normalize both escaped and literal newlines so the
  # canonical metadata line matcher behaves consistently.
  body="${body//${escaped_crlf}/$'\n'}"
  body="${body//${escaped_lf}/$'\n'}"
  body="${body//$'\r'/$'\n'}"

  printf '%s' "${body}"
}

pr_body_normalized="$(normalize_pr_body "${pr_body}")"

primary_task_ids="$(
  printf '%s\n' "${pr_body_normalized}" \
    | grep -Eoi '^[[:space:]]*Primary-Task:[[:space:]]*TASK-[0-9]{3}[[:space:]]*$' \
    | sed -E 's/^[[:space:]]*Primary-Task:[[:space:]]*(TASK-[0-9]{3})[[:space:]]*$/\1/i' \
    | sort -u || true
)"

primary_count="$(printf '%s\n' "${primary_task_ids}" | sed '/^$/d' | wc -l | tr -d ' ')"

if [[ "${primary_count}" -eq 0 ]]; then
  cat <<EOF
PR scope guard failed.
Missing canonical task metadata field in PR body:
  Primary-Task: TASK-XXX

Example:
  Primary-Task: ${branch_task_id}
EOF
  exit 1
fi

if [[ "${primary_count}" -gt 1 ]]; then
  cat <<EOF
PR scope guard failed: multiple Primary-Task fields found in PR body.
Found:
${primary_task_ids}
EOF
  exit 1
fi

primary_task_id="$(printf '%s\n' "${primary_task_ids}" | sed '/^$/d' | head -n 1)"

if [[ "${primary_task_id}" != "${branch_task_id}" ]]; then
  cat <<EOF
PR scope guard failed: branch task ID and Primary-Task mismatch.
Branch task: ${branch_task_id}
Primary-Task: ${primary_task_id}
EOF
  exit 1
fi

echo "PR scope guard passed: ${branch_task_id} (Primary-Task)"
