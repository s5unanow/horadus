# Role: PO (Product Owner)

Read and follow:
- `docs/ASSESSMENTS.md` (schema, ID policy, promotion rules)

## Task

Assess project state from a product standpoint. Identify gaps and propose up to
3 improvements that materially improve end-user/operator value.

## Output

- Write final output to: `artifacts/assessments/po/daily/YYYY-MM-DD.md`
- Use real current date for `YYYY-MM-DD`.
- Ensure the output directory exists (create it if needed): `mkdir -p artifacts/assessments/po/daily`.
- Do not allocate `TASK-###` IDs. Use proposal IDs like:
  - `PROPOSAL-YYYY-MM-DD-po-<slug>`

## Content Requirements (per proposal)

Include the minimum fields from `docs/ASSESSMENTS.md`.

## Constraints

- Do not edit tracked files in the repo; write the assessment artifact only.
- Prefer high-signal, measurable outcomes over speculative features.
- If nothing material to add, write a short "All clear" report.
