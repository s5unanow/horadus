# Role: Security

Read and follow:
- `docs/ASSESSMENTS.md` (schema, ID policy, promotion rules)

## Task

Assess security posture for gaps and likely foot-guns (auth, network exposure,
secrets handling, rate limiting, logging leaks). Propose up to 3 improvements.

## Output

- Write final output to: `artifacts/assessments/security/daily/YYYY-MM-DD.md`
- Use real current date for `YYYY-MM-DD`.
- Ensure the output directory exists (create it if needed): `mkdir -p artifacts/assessments/security/daily`.
- Do not allocate `TASK-###` IDs. Use proposal IDs like:
  - `FINDING-YYYY-MM-DD-security-<slug>` or `PROPOSAL-...`

## Content Requirements (per proposal)

Include the minimum fields from `docs/ASSESSMENTS.md` (area must be `security`).
Use the canonical multiline `Verification:` and `Blast radius:` section format.
Compare against Security artifacts from the last 7 days before finalizing.
If nothing materially new remains after that lookback, write `All clear`.
If you intentionally repeat a finding/proposal, include an explicit delta section.
Ground any live `TASK-###` references against `tasks/CURRENT_SPRINT.md`.
Mark past references explicitly as `[historical] TASK-###` or `[completed] TASK-###`.
Before publishing, run `python scripts/validate_assessment_artifacts.py <target> --check-sprint-grounding --check-novelty --lookback-days 7`.

## Constraints

- Do not edit tracked files in the repo; write the assessment artifact only.
- Prefer concrete reproduction and verification steps.
- If nothing material to add, write a short "All clear" report.
