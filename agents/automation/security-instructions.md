# Role: Security

Read and follow:
- `docs/ASSESSMENTS.md` (schema, ID policy, promotion rules)

## Task

Assess security posture for gaps and likely foot-guns (auth, network exposure,
secrets handling, rate limiting, logging leaks). Propose up to 3 improvements.

## Output

- Write final output to: `artifacts/assessments/security/daily/YYYY-MM-DD.md`
- Use real current date for `YYYY-MM-DD`.
- Do not allocate `TASK-###` IDs. Use proposal IDs like:
  - `FINDING-YYYY-MM-DD-security-<slug>` or `PROPOSAL-...`

## Content Requirements (per proposal)

Include the minimum fields from `docs/ASSESSMENTS.md` (area must be `security`).

## Constraints

- Prefer concrete reproduction and verification steps.
- If nothing material to add, write a short "All clear" report.
