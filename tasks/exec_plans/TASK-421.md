# TASK-421: Close trend-evidence idempotency hole for NULL state_version_id

## Status

- Owner: Codex
- Started: 2026-07-23
- Current state: Implementation complete; shipping lifecycle in progress
- Planning Gates: Required — migration plus allowlisted probability-engine hotspot

## Goal (1-3 lines)

Make evidence idempotency fail closed when a trend lacks an active state
version and enforce the same invariant at the PostgreSQL index layer.

## Inputs

- Spec/backlog references: `tasks/specs/421-trend-evidence-null-state-idempotency.md`
- Runtime/code touchpoints: `TrendEngine.apply_evidence`, `TrendEvidence`
  constraints, active Alembic head
- Preconditions/dependencies: PostgreSQL supports `NULLS NOT DISTINCT`

## Outputs

- Expected behavior/artifacts: service guard, replacement unique index migration,
  regression tests, corrected architecture/data-model docs
- Validation evidence: targeted unit/integration tests, typecheck, agent check,
  full local gate

## Non-Goals

- Explicitly excluded work: state-version backfill redesign, scoring changes,
  restatement/reconciliation changes

## Scope

- In scope: null-state fail-closed guard and matching database uniqueness
- Out of scope: non-null schema conversion and production data repair beyond
  safe index replacement

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: early reject in `apply_evidence` plus
  `NULLS NOT DISTINCT` on the existing partial unique index
- Rejected simpler alternative: service-only guard leaves legacy/direct writers
  and races unprotected
- First integration proof: duplicate active evidence with null
  `state_version_id` violates the replacement index
- Hotspot Outcome: keep-flat-with-rationale — compact early guard only; do not
  increase the ratcheted method or module limits
- Waivers: local pre-push automation was exhausted (`claude` and `codex`
  timed out; `gemini` authentication was ineligible), so adversarial review is
  delegated to the hosted PR review gate before merge.

## Plan (Keep Updated)

1. Completed — preflight and migration/test context
2. Completed — service guard, nulls-not-distinct schema guard, and regressions
3. Completed — docs, unit/type/code-shape, and PostgreSQL integration validation
4. In progress — close ledgers and complete the PR/merge/main-sync lifecycle

## Decisions (Timestamped)

- 2026-07-23: Fail closed at the domain boundary and retain a database backstop
  because the invariant protects probability correctness under concurrency.
- 2026-07-23: Prefer PostgreSQL `NULLS NOT DISTINCT` over a sentinel expression
  index so the declared key remains readable and migration intent is explicit.
- 2026-07-23: Include `trend_id` in the replacement index so legacy null-state
  rows remain isolated per trend while non-null state versions retain the same
  claim-aware uniqueness semantics.

## Risks / Foot-guns

- Existing duplicate null-key rows could block index creation -> migration must
  detect/fail clearly rather than silently delete or merge evidence.
- SQLAlchemy/PostgreSQL syntax support may differ -> verify generated DDL in the
  repository's integration path.
- Hotspot growth -> use an early guard and keep code-shape ratchets flat.

## Validation Commands

- Targeted trend-engine unit tests
- Targeted migration/integration tests
- `make typecheck`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

Validation evidence on 2026-07-23:

- Targeted trend-engine/model tests: 73 passed
- Full PostgreSQL integration and migration drift suite: 21 passed
- `make typecheck`: passed
- `make agent-check`: passed, including 2,753 unit/workflow tests
- Code-shape check: passed with the `trend_engine.py` ratchet unchanged

## Notes / Links

- Spec: `tasks/specs/421-trend-evidence-null-state-idempotency.md`
- Relevant modules: `src/core/trend_engine.py`, `src/storage/models.py`
