# Automation: Weekly Backlog Triage

Read and follow:
- `docs/ASSESSMENTS.md` (assessment intake rules)

## Bounded Research Mode

Use a bounded three-pass workflow for this triage run:

1. Plan
   - Identify the 3-6 sub-questions needed to rank backlog candidates.
   - Decide which repo sources can answer each question before you retrieve
     anything else.
2. Retrieve
   - Gather only the repo evidence needed to answer those sub-questions.
   - Prefer structured Horadus CLI output first, then direct file search only
     when the CLI output is empty, partial, or too narrow.
   - When sources disagree, surface the contradiction instead of smoothing it
     away.
3. Synthesize
   - Keep final recommendations evidence-backed and bounded to the retrieved
     repo evidence.
   - Label inference versus directly supported fact when a recommendation goes
     beyond the literal retrieved text.
   - Cite the exact file path, task id, proposal id, or command result that
     supports each claim; do not invent sources.

## Inputs

- `tasks/CURRENT_SPRINT.md`
- `tasks/BACKLOG.md`
- `tasks/COMPLETED.md`
- `PROJECT_STATUS.md`
- Recent assessment artifacts:
  - `artifacts/assessments/**/daily/*.md` (last 14 days if present)
- Preferred structured bundle:
  - `uv run --no-sync horadus triage collect --lookback-days 14 --format json`

## Backlog context policy (cost + hygiene)

- Treat `tasks/BACKLOG.md` as a **search index**, not a document to copy or
  summarize in full.
- Do **not** paste or paraphrase the entire backlog into the report. Instead:
  - Use targeted search (e.g., `rg`) for relevant keywords/areas.
  - Only quote or summarize the specific `TASK-###` sections that are
    potentially overlapping with the candidate proposals.
- If you need a snapshot for de-duplication, include only:
  - the matching task title(s)
  - their `Priority`/`Estimate`
  - and 1-2 sentences of why they overlap.

## Minimum search set (de-dupe coverage)

For each candidate, run and record (in the triage report) at least:

- Candidate keywords (2-4 nouns) across backlog + completed ledgers:
  - Prefer a structured triage bundle first:
    - `uv run --no-sync horadus triage collect --keyword "<kw1>" --keyword "<kw2>" --keyword "<kw3>" --keyword "<kw4>" --lookback-days 14 --format json`
  - Then refine with direct search only when needed:
  - `rg -n "<kw1>|<kw2>|<kw3>|<kw4>" tasks/BACKLOG.md tasks/COMPLETED.md`
- Blast-radius file paths/modules against backlog (to catch same-work-different-title):
  - Prefer:
    - `uv run --no-sync horadus triage collect --path "<path-or-module>" --lookback-days 14 --format json`
  - `rg -n "<path-or-module>" tasks/BACKLOG.md`
  - (repeat for 2-5 key paths/modules from `blast_radius`)
- Proposal/finding ID across recent assessments (to de-dup across roles and days):
  - Prefer:
    - `uv run --no-sync horadus triage collect --proposal-id "<proposal_id>" --lookback-days 14 --format json`
  - `rg -n "<proposal_id>" artifacts/assessments/**/daily/*.md`

If any search returns matches, briefly state whether it is a true overlap, and
if so, reference the prior task/proposal and explain the overlap in 1-2
sentences.

## Output

- Write final output to: `artifacts/backlog_triage/triage-YYYY-MM-DD.md`
- Use real current date for `YYYY-MM-DD`.

## Required Sections

- Assessment hygiene:
  - Run `python scripts/validate_assessment_artifacts.py` over the recent assessment artifacts.
  - If violations are found, summarize the top issues and reference the violating files.
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
- Distinguish directly supported facts from inference in the write-up when the
  recommendation depends on interpretation rather than a literal repo record.
