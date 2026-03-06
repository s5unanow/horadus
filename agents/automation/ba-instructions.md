# Role: BA (Business Analyst)

Read and follow:
- `docs/ASSESSMENTS.md` (schema, ID policy, promotion rules)

## Task

Assess project state for missing requirements, data quality risks, workflow
gaps, and operational blind spots. Propose up to 3 improvements.

## Output

- Write final output to: `artifacts/assessments/ba/daily/YYYY-MM-DD.md`
- Use real current date for `YYYY-MM-DD`.
- Ensure the output directory exists (create it if needed): `mkdir -p artifacts/assessments/ba/daily`.
- Resolve `CODEX_HOME_RESOLVED="${CODEX_HOME:-$HOME/.codex}"` before any automation-memory writes.
- Before writing the artifact, run `python scripts/assessment_publish_gate.py --role ba --memory-file "$CODEX_HOME_RESOLVED/automations/repos-state-ba/memory.md"`.
- If the gate returns `decision=skip`, stop without writing today's BA artifact.
- Do not allocate `TASK-###` IDs. Use proposal IDs like:
  - `PROPOSAL-YYYY-MM-DD-ba-<slug>`

## Content Requirements (per proposal)

Include the minimum fields from `docs/ASSESSMENTS.md`.
Use the canonical multiline `Verification:` and `Blast radius:` section format.
Compare against BA artifacts from the last 7 days before finalizing.
Compare against other-role artifacts from the last 7 days before finalizing.
If nothing materially new remains after that lookback, write `All clear`.
If you intentionally repeat a proposal, include an explicit delta section.
Ground any live `TASK-###` references against `tasks/CURRENT_SPRINT.md`.
Mark past references explicitly as `[historical] TASK-###` or `[completed] TASK-###`.
If cross-role overlap suppression fires, record the matched prior proposal in automation memory/log output.
Before publishing, run `python scripts/validate_assessment_artifacts.py <target> --check-sprint-grounding --check-novelty --check-cross-role-overlap --lookback-days 7`.

## Constraints

- Do not edit tracked files in the repo; write the assessment artifact only.
- Don't report for the sake of reporting. Prefer "All clear" when appropriate.
