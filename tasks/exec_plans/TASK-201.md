# TASK-201: Preserve audited, atomic manual trend overrides

## Status

- Owner: Codex
- Started: 2026-03-22
- Current state: In progress
- Planning Gates: Required — shared runtime change across API write paths and trend-engine mutation semantics

## Goal (1-3 lines)

Keep `PATCH /api/v1/trends/{id}` from mutating live probability state directly.
Manual probability changes must continue to flow only through the audited
override path that records `HumanFeedback` lineage and uses atomic delta logic.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-201`), `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints: `src/api/routes/trends.py`, `src/api/routes/_trend_write_mutations.py`, `src/api/routes/trend_api_models.py`, `src/api/routes/feedback.py`
- Preconditions/dependencies: existing `POST /api/v1/trends/{id}/override` path remains the canonical manual override surface

## Outputs

- Expected behavior/artifacts: generic trend patch rejects `current_probability`; override endpoint remains unchanged for audited manual deltas
- Validation evidence: targeted unit tests for route/mutation rejection plus existing override-path tests; `make agent-check`; `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Explicitly excluded work: redesigning the override payload, changing trend-create semantics, or altering evidence/restatement math

## Scope

- In scope: reject direct live-probability rewrites on trend patch, keep API contract/docs honest, add regression tests
- Out of scope: new override capabilities, UI/client migrations, bulk replay/state backfills

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: reject `current_probability` on generic patch and point callers to the dedicated override endpoint
- Rejected simpler alternative: keep accepting `current_probability` on patch and mirror override-side auditing inside the generic route
- First integration proof: targeted unit tests show `PATCH` rejection while override tests still exercise compensating restatement flow
- Waivers: none

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-22: Use explicit rejection on `PATCH /api/v1/trends/{id}` instead of silently rerouting to override flow so callers cannot bypass the dedicated audit surface by accident.

## Risks / Foot-guns

- Existing callers may still send `current_probability` on patch -> return a clear error pointing to the override endpoint
- Trend update tests previously encoded the unsafe behavior -> replace them with rejection coverage instead of preserving the bug as contract

## Validation Commands

- `pytest tests/unit/api/test_trends.py tests/unit/api/test_trend_write_mutations.py tests/unit/api/test_trend_write_contract.py tests/unit/api/test_feedback.py`
- `make agent-check`
- `uv run --no-sync horadus tasks local-review --format json`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none
- Relevant modules: `src/api/routes/_trend_write_mutations.py`, `src/api/routes/trends.py`, `src/api/routes/feedback.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
