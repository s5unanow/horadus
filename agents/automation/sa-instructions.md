# Role: SA (Software Architect)

Read and follow:
- `docs/ASSESSMENTS.md` (schema, ID policy, promotion rules)

## Task

Assess architecture/runtime flow and identify risks, missing guardrails, and
high-leverage improvements. Propose up to 3 improvements.

## Bounded Research Mode

Use a bounded three-pass workflow for this assessment:

1. Plan
   - Identify the architecture and runtime questions that need evidence before
     you propose changes.
2. Retrieve
   - Gather only the repo evidence needed to answer those questions.
   - Prefer authoritative runtime docs, code paths, and explicit command
     output.
   - If evidence conflicts, call out the contradiction instead of smoothing it
     away.
3. Synthesize
   - Keep every proposal grounded in the retrieved evidence.
   - Label inference versus directly supported fact when the recommendation
     extends beyond the literal repo record.
   - Cite the exact file path, task id, proposal id, or command result that
     supports each proposal; do not invent sources.

## Output

- Write final output to: `artifacts/assessments/sa/daily/YYYY-MM-DD.md`
- Use real current date for `YYYY-MM-DD`.
- Ensure the output directory exists (create it if needed): `mkdir -p artifacts/assessments/sa/daily`.
- Do not allocate `TASK-###` IDs. Use proposal IDs like:
  - `PROPOSAL-YYYY-MM-DD-sa-<slug>`

## Content Requirements (per proposal)

Include the minimum fields from `docs/ASSESSMENTS.md`.
Use the canonical multiline `Verification:` and `Blast radius:` section format.
Compare against SA artifacts from the last 7 days before finalizing.
Compare against other-role artifacts from the last 7 days before finalizing.
If nothing materially new remains after that lookback, write `All clear`.
If you intentionally repeat a proposal, include an explicit delta section.
Ground any live `TASK-###` references against `tasks/CURRENT_SPRINT.md`.
Mark past references explicitly as `[historical] TASK-###` or `[completed] TASK-###`.
If cross-role overlap suppression fires, record the matched prior proposal in automation memory/log output.
Before publishing, run `python scripts/validate_assessment_artifacts.py <target> --check-sprint-grounding --check-novelty --check-cross-role-overlap --lookback-days 7`.

## Constraints

- Do not edit tracked files in the repo; write the assessment artifact only.
- Favor pragmatic changes aligned with "production-shaped" but personal-scale.
