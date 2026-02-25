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

Directory convention for raw outputs:

- `artifacts/assessments/<role>/daily/YYYY-MM-DD.md`

Roles are free-form but should stay stable (e.g. `security`, `sa`, `po`, `ba`,
`agents`).

## Validation

To validate the most recent assessment artifacts locally:

- `python scripts/validate_assessment_artifacts.py`

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

Suggested Markdown template:

```md
### PROPOSAL-2026-02-25-security-metrics-auth
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
