#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage:
  ./scripts/promote_assessment_proposal.sh \
    --proposal-id PROPOSAL-... \
    --assessment-ref artifacts/assessments/<role>/daily/YYYY-MM-DD.md \
    --title "Short title" \
    [--priority P2] [--estimate "2-4 hours"] [--files "src/..."] \
    [--lookback-days 14] [--strict-dedupe]

This prints a backlog-entry scaffold to stdout. It does not modify files.
USAGE
}

proposal_id=""
assessment_ref=""
title=""
priority="P2"
estimate="2-4 hours"
files=""
lookback_days="14"
strict_dedupe="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --proposal-id) proposal_id="${2:-}"; shift 2 ;;
    --assessment-ref) assessment_ref="${2:-}"; shift 2 ;;
    --title) title="${2:-}"; shift 2 ;;
    --priority) priority="${2:-}"; shift 2 ;;
    --estimate) estimate="${2:-}"; shift 2 ;;
    --files) files="${2:-}"; shift 2 ;;
    --lookback-days) lookback_days="${2:-}"; shift 2 ;;
    --strict-dedupe) strict_dedupe="1"; shift ;;
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

if ! [[ "${lookback_days}" =~ ^[0-9]+$ ]]; then
  echo "--lookback-days must be a non-negative integer"
  exit 1
fi

dedupe_matches="$({
python3 - "${proposal_id}" "${assessment_ref}" "${lookback_days}" <<'PY'
import re
import sys
from datetime import date, timedelta
from pathlib import Path

proposal_id = sys.argv[1].strip()
assessment_ref = sys.argv[2].strip()
lookback_days = int(sys.argv[3])

id_pattern = re.compile(r"^(?:PROPOSAL|FINDING)-(\d{4}-\d{2}-\d{2})-(.+)$")
heading_pattern = re.compile(r"^###\s+((?:PROPOSAL|FINDING)-[A-Za-z0-9._:-]+)\s*$")
role_prefixes = {"po", "ba", "sa", "security", "agents"}

def normalize_slug(slug: str) -> str:
    parts = [chunk for chunk in slug.split("-") if chunk]
    if parts and parts[0] in role_prefixes:
        parts = parts[1:]
    return "-".join(parts)

current_match = id_pattern.match(proposal_id)
current_date = date.fromisoformat(current_match.group(1)) if current_match else None
current_slug = current_match.group(2) if current_match else proposal_id
current_slug_normalized = normalize_slug(current_slug)

cutoff = (current_date - timedelta(days=lookback_days)) if current_date else None
root = Path("artifacts/assessments")
if not root.exists():
    sys.exit(0)

for path in sorted(root.glob("*/daily/*.md")):
    if str(path) == assessment_ref:
        continue

    filename_date_match = re.search(r"(\d{4}-\d{2}-\d{2})\.md$", path.name)
    if cutoff and filename_date_match:
        file_date = date.fromisoformat(filename_date_match.group(1))
        if file_date < cutoff:
            continue

    for line in path.read_text(encoding="utf-8").splitlines():
        match = heading_pattern.match(line.strip())
        if not match:
            continue
        candidate_id = match.group(1)
        if candidate_id == proposal_id:
            print(f"{candidate_id}|{path.as_posix()}")
            continue

        candidate_match = id_pattern.match(candidate_id)
        candidate_slug = candidate_match.group(2) if candidate_match else candidate_id
        if normalize_slug(candidate_slug) == current_slug_normalized:
            print(f"{candidate_id}|{path.as_posix()}")
PY
} | sort -u)"

if [[ -n "${dedupe_matches}" ]]; then
  echo "Potential duplicate proposals detected in recent assessments:"
  while IFS='|' read -r prior_id prior_path; do
    [[ -n "${prior_id}" ]] || continue
    echo "- matched prior (proposal_id, Assessment-Ref): (${prior_id}, ${prior_path})"
  done <<< "${dedupe_matches}"

  if [[ "${strict_dedupe}" == "1" ]]; then
    echo "Strict mode enabled: refusing scaffold generation due to duplicate matches."
    exit 2
  fi
fi

cat <<SCAFFOLD
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
SCAFFOLD
