# Automation: Daily Sprint Health

## Inputs

- `tasks/CURRENT_SPRINT.md`
- Optional (if needed for recommendations):
  - most recent `artifacts/backlog_triage/triage-YYYY-MM-DD.md` (within 14 days)

## Output

- Write final output to: `artifacts/sprint_health/health-YYYY-MM-DD.md`
- Use real current date for `YYYY-MM-DD`.

## Required Content

- Active task count and list
- Count of `[REQUIRES_HUMAN]` active tasks
- Any blockers called out explicitly
- If there are 0 active non-human tasks: recommend 1-3 next actions
