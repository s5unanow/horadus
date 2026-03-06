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

Use the canonical multiline section format from `docs/ASSESSMENTS.md`:
- metadata fields near the top (`area`, `priority`, `confidence`, `estimate`, `recommended_gate`)
- `Verification:` with bullet lines
- `Blast radius:` with bullet lines
- compare against same-role artifacts from the last 7 days before finalizing
- compare against other-role artifacts from the last 7 days before finalizing
- if no materially new proposal remains, write `All clear` instead of repeating prior themes
- if repeating a proposal intentionally, include an explicit delta section such as `Delta since prior report:`
- ground any live `TASK-###` references against `tasks/CURRENT_SPRINT.md`
- mark past references explicitly as `[historical] TASK-###` or `[completed] TASK-###`
- if cross-role overlap suppression fires, record the matched prior proposal in automation memory/log output
- before publishing, run `python scripts/validate_assessment_artifacts.py <target> --check-sprint-grounding --check-novelty --check-cross-role-overlap --lookback-days 7`

## Constraints

- Do not edit tracked files in the repo; write the assessment artifact only.
- Keep it additive and concrete: actionable steps, minimal speculation.
- If nothing material to add, write a short "All clear" report.
