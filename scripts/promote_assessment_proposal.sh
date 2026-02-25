#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<EOF
Usage:
  ./scripts/promote_assessment_proposal.sh \\
    --proposal-id PROPOSAL-... \\
    --assessment-ref artifacts/assessments/<role>/daily/YYYY-MM-DD.md \\
    --title "Short title" \\
    [--priority P2] [--estimate "2-4 hours"] [--files "src/..."]

This prints a backlog-entry scaffold to stdout. It does not modify files.
EOF
}

proposal_id=""
assessment_ref=""
title=""
priority="P2"
estimate="2-4 hours"
files=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --proposal-id) proposal_id="${2:-}"; shift 2 ;;
    --assessment-ref) assessment_ref="${2:-}"; shift 2 ;;
    --title) title="${2:-}"; shift 2 ;;
    --priority) priority="${2:-}"; shift 2 ;;
    --estimate) estimate="${2:-}"; shift 2 ;;
    --files) files="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown arg: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ -z "${proposal_id}" || -z "${assessment_ref}" || -z "${title}" ]]; then
  usage
  exit 1
fi

cat <<EOF
### TASK-XXX: ${title}
**Priority**: ${priority}
**Estimate**: ${estimate}

Assessment-Ref: \`${assessment_ref}\` (\`${proposal_id}\`)

<1-2 paragraph summary of the problem and desired outcome.>

**Files**: ${files:-<fill in likely files/dirs>}

**Acceptance Criteria**:
- [ ] <criterion 1>
- [ ] <criterion 2>

---
EOF
