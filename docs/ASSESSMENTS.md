# Assessments (Automation Outputs) and Intake Policy

This project uses scheduled "role agents" (security/SA/PO/BA/agentic) to
produce assessment reports. These reports are **advisory inputs** only.

They are not part of the canonical source of truth for execution. Promotion
into real work happens explicitly via backlog/sprint intake.

## Storage Policy

- Raw automation outputs live under `artifacts/assessments/` and are not tracked.
- Curated, human-approved assessment artifacts (checklists, launch-readiness
  sign-offs) live under `tasks/assessments/` and are tracked.

Canonical automation role instructions live in:
- `agents/automation/`
- Repo workflow/triage CLI for agent use:
  - `uv run --no-sync horadus triage collect --lookback-days 14 --format json`

Directory convention for raw outputs:

- `artifacts/assessments/<role>/daily/YYYY-MM-DD.md`

Roles are free-form but should stay stable (e.g. `security`, `sa`, `po`, `ba`,
`agents`).

## Validation

To validate the most recent assessment artifacts locally:

- `python scripts/validate_assessment_artifacts.py`
- `python scripts/validate_assessment_artifacts.py <target> --check-novelty --lookback-days 7`
- `python scripts/validate_assessment_artifacts.py <target> --check-sprint-grounding`
- `python scripts/validate_assessment_artifacts.py <target> --check-cross-role-overlap --lookback-days 7`

Daily artifact integrity enforced by validator:
- Filename date (`artifacts/assessments/<role>/daily/YYYY-MM-DD.md`) must match the top report
  heading date.
- Proposal/Finding IDs in that file must use the same `YYYY-MM-DD` date segment.
- Scratch files under `_raw/` are ignored by the validator; only dated daily
  artifacts are part of the enforced contract.

Novelty policy for daily role assessments:

- Compare draft proposals/findings against same-role artifacts from the previous
  7 days before publishing.
- If a proposal is already captured in recent same-role history or the current
  task ledgers, it is not materially new by default.
- To intentionally repeat a proposal, include an explicit delta section such as
  `Delta since prior report:` or `New evidence:` with the new fact/scope change.
- If no materially new proposals remain after the 7-day lookback, emit a short
  `All clear` report instead of rephrasing prior recommendations.

Current-sprint grounding policy for task references:

- Treat `tasks/CURRENT_SPRINT.md` as the only source of truth for live
  `TASK-###` references in daily assessments.
- Before publishing a current-sprint artifact, run
  `python scripts/validate_assessment_artifacts.py <target> --check-sprint-grounding`.
- If you need to mention a no-longer-active or already completed task, mark it
  explicitly as `[historical] TASK-###` or `[completed] TASK-###`.
- The grounding check only applies to artifacts whose filename date falls inside
  the current sprint date window; older archived artifacts are left untouched.

Cross-role overlap policy for daily role assessments:

- Before publishing, compare draft proposals against other-role artifacts from
  the previous 7 days.
- If another role already covered the same issue and you do not have materially
  new evidence, suppress the duplicate proposal and emit `All clear` if nothing
  else remains.
- Reuse the same explicit delta sections as the novelty gate when repeating a
  cross-role theme with genuinely new scope/evidence.
- Record any suppressed overlap in automation memory/log output with the matched
  prior `(proposal_id, Assessment-Ref)` so operators can audit why the proposal
  was omitted.

PO/BA change-trigger policy under fully human-gated queues:

- When every active sprint task is marked `[REQUIRES_HUMAN]`, PO and BA should
  gate publication through `python scripts/assessment_publish_gate.py`.
- The gate computes a stable blocker-state hash from active task ids, human
  blocker metadata, and launch-scope context in `tasks/CURRENT_SPRINT.md`.
- If the queue is fully human-gated and the blocker-state hash is unchanged from
  the prior run, skip artifact publication for that role.
- If the queue changes or includes any non-human executable task, publish
  normally and record the decision/hash in automation memory.

## Proposal Schema (Minimum Fields)

Assessments must emit proposals/findings with a stable ID that is **not** a
backlog task ID.

Each proposal must include:

- `proposal_id`: `PROPOSAL-...` or `FINDING-...` (do not use `TASK-###`)
- `area`: one of `api|core|storage|ingestion|processing|workers|repo|docs|security|ops`
- `priority`: `P0|P1|P2|P3`
- `confidence`: float in `[0, 1]`
- `estimate`: rough effort (`<1h`, `1-2h`, `2-4h`, `1d`, `2d`, etc.)
- `verification`: concrete commands or checks to validate the change
- `blast_radius`: files/modules likely to change
- `recommended_gate`: `AUTO_OK|HUMAN_REVIEW|REQUIRES_HUMAN`

Canonical Markdown template:

```md
### PROPOSAL-2026-02-25-security-metrics-auth
proposal_id: PROPOSAL-2026-02-25-security-metrics-auth
area: security
priority: P2
confidence: 0.78
estimate: 1-2h
recommended_gate: HUMAN_REVIEW

Problem:
...

Proposed change:
...

Verification:
- make test-unit
- uv run horadus agent smoke

Blast radius:
- src/api/...
- docs/DEPLOYMENT.md
```

Canonical formatting rules:

- Use section-style `Verification:` and `Blast radius:` blocks with one or more
  bullet lines.
- `Problem:` and `Proposed change:` are strongly recommended for readability but
  are not currently required by the validator.
- The `### PROPOSAL-...` / `### FINDING-...` heading is the authoritative ID.
  A `proposal_id:` line is recommended and may repeat the heading for clarity.

Legacy compatibility:

- The validator still accepts historical single-line forms such as
  `verification: make test-unit` and `blast_radius: scripts/`.
- New and updated automations should emit the canonical multiline section form.

## ID Policy (Hard Rule)

- Assessment outputs must never allocate `TASK-###` IDs.
- Backlog task IDs are assigned only during intake when adding items to
  `tasks/BACKLOG.md`.

Rationale: assessment agents run in parallel over time; auto-allocating `TASK`
IDs causes collisions and confusion.

## Promotion Rules (How Proposals Become Backlog Tasks)

Promotion is an explicit act performed during backlog triage / sprint planning:

1. Pick proposals worth doing (based on confidence, priority, and project goals).
2. Create a `TASK-###` entry in `tasks/BACKLOG.md` with clear acceptance criteria.
3. Add a reference line to the source assessment, e.g. `Assessment-Ref:
   artifacts/assessments/security/daily/2026-02-25.md`.

Recommended gating:

- `AUTO_OK`: docs-only, scripts/Make targets, local tooling; no prod guardrail or
  auth changes; no migrations.
- `HUMAN_REVIEW`: most code changes.
- `REQUIRES_HUMAN`: anything involving production secrets, network exposure,
  auth policy, data retention/destructive ops, probability math semantics, or
  migrations (unless already well-covered and explicitly delegated).

## Promotion De-duplication Guard

Use the helper to scaffold backlog entries from assessment proposals:

- `./scripts/promote_assessment_proposal.sh --proposal-id ... --assessment-ref ... --title "..."`

Cross-role duplicate checks are built in:
- default mode: warn-only (prints prior `(proposal_id, Assessment-Ref)` matches)
- strict mode: `--strict-dedupe` (exits non-zero on duplicate matches)
- configurable lookback: `--lookback-days N` (default `14`)
