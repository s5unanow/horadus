#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  cat <<USAGE
Usage:
  ./scripts/task_context_pack.sh TASK-XXX
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

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
backlog_path="${repo_root}/tasks/BACKLOG.md"
sprint_path="${repo_root}/tasks/CURRENT_SPRINT.md"
spec_path="${repo_root}/tasks/specs/${task_id#TASK-}-"*

line_exists() {
  local pattern="$1"
  local file="$2"
  if command -v rg >/dev/null 2>&1; then
    rg -q -- "${pattern}" "${file}"
  else
    grep -Eq -- "${pattern}" "${file}"
  fi
}

print_matching_lines() {
  local pattern="$1"
  local file="$2"
  if command -v rg >/dev/null 2>&1; then
    rg -n -- "${pattern}" "${file}" || true
  else
    grep -En -- "${pattern}" "${file}" || true
  fi
}

if ! line_exists "^### ${task_id}:" "${backlog_path}"; then
  echo "${task_id} not found in tasks/BACKLOG.md"
  exit 1
fi

echo "# Context Pack: ${task_id}"
echo

echo "## Backlog Entry"
awk -v task="${task_id}" '
  $0 ~ "^### " task ":" {in_block=1}
  in_block {print}
  in_block && /^---$/ {exit}
' "${backlog_path}"
echo

echo "## Sprint Status"
print_matching_lines "${task_id}" "${sprint_path}"
echo

echo "## Matching Spec"
if ls ${spec_path} >/dev/null 2>&1; then
  ls ${spec_path}
else
  echo "(none)"
fi

echo

echo "## Likely Code Areas"
files_line="$(awk -v task="${task_id}" '
  $0 ~ "^### " task ":" {in_block=1; next}
  in_block && /^\*\*Files\*\*:/ {print; exit}
  in_block && /^---$/ {exit}
' "${backlog_path}")"
if [[ -n "${files_line}" ]]; then
  printf '%s\n' "${files_line}" | sed -E 's/^\*\*Files\*\*:\s*//'
else
  echo "(not specified in backlog entry)"
fi

echo

echo "## Suggested Validation Commands"
echo "make agent-check"
echo "make docs-freshness"
echo "uv run --no-sync pytest tests/unit/ -v -m unit"
