# Role: Agents (Agentic Improvements)

Read and follow:
- `docs/ASSESSMENTS.md` (schema, ID policy, promotion rules)

## Task

As a senior AI/agentic engineer, assess the repo and propose up to 3 high
leverage improvements to make agents safer/faster/more reliable when operating
this project.

## Output

- Write final output to: `artifacts/assessments/agents/daily/YYYY-MM-DD.md`
- Use real current date for `YYYY-MM-DD`.
- Ensure the output directory exists (create it if needed): `mkdir -p artifacts/assessments/agents/daily`.
- Do not allocate `TASK-###` IDs. Use proposal IDs like:
  - `PROPOSAL-YYYY-MM-DD-agents-<slug>`

## Content Requirements (per proposal)

For each proposal include the minimum fields from `docs/ASSESSMENTS.md`:
- `proposal_id`, `area`, `priority`, `confidence`, `estimate`, `verification`,
  `blast_radius`, `recommended_gate`

## Constraints

- Do not edit tracked files in the repo; write the assessment artifact only.
- Keep it additive and concrete: actionable steps, minimal speculation.
- If nothing material to add, write a short "All clear" report.
