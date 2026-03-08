# Automation Agent Instructions

This directory contains the canonical, versioned instructions for scheduled
"role agent" automations (PO/BA/SA/security/agentic) and repo operational
automations (triage, sprint health).

Repo operational automations also include the Horadus friction summary flow,
which writes daily reports under
`artifacts/agent/horadus-cli-feedback/daily/YYYY-MM-DD.md`.

Automations should keep their configured prompt minimal: open the relevant file
here and follow it exactly.

Related policy:
- `docs/ASSESSMENTS.md`

Related tooling:
- `scripts/assessment_publish_gate.py`
- `scripts/validate_assessment_artifacts.py`
- `scripts/promote_assessment_proposal.sh`

Implementation-start guard (when an automation proposes execution-ready work):
- Run `uv run --no-sync horadus tasks eligibility TASK-XXX --format json` before any code changes.
- Do not proceed when the task is not active or is marked `[REQUIRES_HUMAN]`.
