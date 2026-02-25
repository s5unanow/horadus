# Automation: Weekly Backlog Triage

Read and follow:
- `docs/ASSESSMENTS.md` (assessment intake rules)

## Inputs

- `tasks/CURRENT_SPRINT.md`
- `tasks/BACKLOG.md`
- `tasks/COMPLETED.md`
- `PROJECT_STATUS.md`
- Recent assessment artifacts:
  - `artifacts/assessments/**/daily/*.md` (last 14 days if present)

## Output

- Write final output to: `artifacts/backlog_triage/triage-YYYY-MM-DD.md`
- Use real current date for `YYYY-MM-DD`.

## Required Sections

- Current sprint summary (what is active, blockers, human-gated items)
- Top candidates (5-10) for next sprint, each with:
  - objective
  - why now
  - effort (S/M/L)
  - dependencies
  - risks
  - validation commands
  - gating (`AUTO_OK|HUMAN_REVIEW|REQUIRES_HUMAN`)
  - whether an exec plan is required (see `tasks/exec_plans/README.md`)
  - if assessment-driven: include `proposal_id` and `Assessment-Ref: <path>`

## Intake Rules

- Assessments are advisory; do not copy their `TASK-###` labels even if present.
- Do not allocate new `TASK-###` IDs in this report.
- De-duplicate overlapping proposals across roles.
