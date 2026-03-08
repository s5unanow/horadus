# Role: PO (Product Owner)

Read and follow:
- `docs/ASSESSMENTS.md` (schema, ID policy, promotion rules)

## Task

Assess project state from a product standpoint. Identify gaps and propose up to
3 improvements that materially improve end-user/operator value.

## Bounded Research Mode

Use a bounded three-pass workflow for this assessment:

1. Plan
   - Identify the product and operator questions that must be answered before
     proposing work.
2. Retrieve
   - Gather only the repo evidence needed to answer those questions.
   - Prefer authoritative repo files and command output over broad summaries.
   - If evidence conflicts, call out the contradiction instead of resolving it
     implicitly.
3. Synthesize
   - Keep every recommendation grounded in the retrieved evidence.
   - Label inference versus directly supported fact when a recommendation
     extends beyond the literal repo record.
   - Cite the exact file path, task id, proposal id, or command result that
     supports each proposal; do not invent sources.

## Output

- Write final output to: `artifacts/assessments/po/daily/YYYY-MM-DD.md`
- Use real current date for `YYYY-MM-DD`.
- Ensure the output directory exists (create it if needed): `mkdir -p artifacts/assessments/po/daily`.
- Resolve `CODEX_HOME_RESOLVED="${CODEX_HOME:-$HOME/.codex}"` before any automation-memory writes.
- Before writing the artifact, run `python scripts/assessment_publish_gate.py --role po --memory-file "$CODEX_HOME_RESOLVED/automations/repo-state-po/memory.md"`.
- If the gate returns `decision=skip`, stop without writing today's PO artifact.
- Do not allocate `TASK-###` IDs. Use proposal IDs like:
  - `PROPOSAL-YYYY-MM-DD-po-<slug>`

## Content Requirements (per proposal)

Include the minimum fields from `docs/ASSESSMENTS.md`.
Use the canonical multiline `Verification:` and `Blast radius:` section format.
Compare against PO artifacts from the last 7 days before finalizing.
Compare against other-role artifacts from the last 7 days before finalizing.
If nothing materially new remains after that lookback, write `All clear`.
If you intentionally repeat a proposal, include an explicit delta section.
Ground any live `TASK-###` references against `tasks/CURRENT_SPRINT.md`.
Mark past references explicitly as `[historical] TASK-###` or `[completed] TASK-###`.
If cross-role overlap suppression fires, record the matched prior proposal in automation memory/log output.
Before publishing, run `python scripts/validate_assessment_artifacts.py <target> --check-sprint-grounding --check-novelty --check-cross-role-overlap --lookback-days 7`.

## Constraints

- Do not edit tracked files in the repo; write the assessment artifact only.
- Prefer high-signal, measurable outcomes over speculative features.
- If nothing material to add, write a short "All clear" report.
