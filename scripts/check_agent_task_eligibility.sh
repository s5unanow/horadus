#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  cat <<USAGE
Usage:
  ./scripts/check_agent_task_eligibility.sh TASK-XXX
USAGE
  exit 1
fi

task_input="$1"
if [[ "${task_input}" =~ ^TASK-([0-9]{3})$ ]]; then
  task_id="${task_input}"
elif [[ "${task_input}" =~ ^([0-9]{3})$ ]]; then
  task_id="TASK-${BASH_REMATCH[1]}"
else
  echo "Invalid task id '${task_input}'. Expected TASK-XXX or XXX."
  exit 1
fi

sprint_file="${TASK_ELIGIBILITY_SPRINT_FILE:-tasks/CURRENT_SPRINT.md}"
preflight_cmd="${TASK_ELIGIBILITY_PREFLIGHT_CMD:-./scripts/check_task_start_preflight.sh}"

if [[ ! -f "${sprint_file}" ]]; then
  echo "Missing sprint file: ${sprint_file}"
  exit 1
fi

active_section="$({
  awk '
    /^## Active Tasks/ {in_active=1; next}
    /^## / {if (in_active) exit}
    in_active {print}
  ' "${sprint_file}"
} || true)"

if [[ -z "${active_section}" ]]; then
  echo "Unable to locate Active Tasks section in ${sprint_file}"
  exit 1
fi

if command -v rg >/dev/null 2>&1; then
  task_line="$(printf '%s\n' "${active_section}" | rg "${task_id}" || true)"
else
  task_line="$(printf '%s\n' "${active_section}" | grep "${task_id}" || true)"
fi
if [[ -z "${task_line}" ]]; then
  echo "${task_id} is not listed in Active Tasks (${sprint_file})"
  exit 1
fi

if [[ "${task_line}" == *"[REQUIRES_HUMAN]"* ]]; then
  echo "${task_id} is marked [REQUIRES_HUMAN] and is not eligible for autonomous start"
  exit 1
fi

if ! eval "${preflight_cmd}"; then
  echo "Task sequencing preflight failed for ${task_id}."
  exit 1
fi

echo "Agent task eligibility passed: ${task_id}"
