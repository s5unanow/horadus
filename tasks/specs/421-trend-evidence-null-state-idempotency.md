---
task_id: TASK-421
retrieval:
  kind: task-spec
  status: active
  canonical: true
  supersedes: []
  superseded_by: null
---

# TASK-421: Close trend-evidence idempotency hole for NULL state_version_id

## Problem Statement

Active trend evidence is intended to be idempotent per state version, event
claim, and signal. Both the application pre-check and the partial unique index
use nullable `state_version_id`; PostgreSQL treats nulls as distinct and
`state_version_id = NULL` never matches. A trend without an active state
version can therefore accept the same evidence more than once and double-apply
its log-odds delta.

## Inputs

- `INTAKE-0063` and the `TASK-421` backlog entry
- `src/core/trend_engine.py`, `src/storage/models.py`, and the active Alembic head
- The claim-aware evidence/restatement contract in `docs/ARCHITECTURE.md` and
  `docs/DATA_MODEL.md`

## Outputs

- Evidence application fails closed before persistence or probability mutation
  when a trend has no active state version.
- Database uniqueness also treats null state-version keys as equal, protecting
  legacy rows and concurrent writers.
- Tests pin the service and database invariants; docs describe the actual
  claim-aware uniqueness key.

## Non-Goals

- Backfilling or redesigning trend state-version history
- Changing evidence scoring, reconciliation, restatement, or decay math
- Making `Trend.active_state_version_id` non-null across the entire schema

**Planning Gates**: `Required` — this task adds a migration and materially
touches allowlisted `trend_engine.py`.

## Phase -1 / Pre-Implementation Gates

- `Simplicity Gate`: Extend the existing `apply_evidence` guard and unique index;
  do not introduce a new evidence repository or idempotency service.
- `Anti-Abstraction Gate`: No new wrapper is justified; the service guard and
  schema constraint are the two existing enforcement layers.
- `Integration-First Gate`:
  - Validation target: PostgreSQL uniqueness semantics for two active rows with
    a null state-version key.
  - Exercises: migration-backed integration test plus service-level regression.
- `Code Shape Gate`: Triggered — keep the oversized method and module flat by
  replacing nullable fallback behavior with an early guard.
- Hotspot Outcome: keep-flat-with-rationale — the change adds only a compact
  fail-closed guard to the existing evidence boundary and must not grow the
  allowlisted method maximum.
- `Determinism Gate`: Triggered — duplicate application must deterministically
  become either a service rejection or a database-conflict no-op.
- `LLM Budget/Safety Gate`: Not applicable — no LLM call path changes.
- `Observability Gate`: Triggered — the failure must include the trend identity
  and occur before any stored evidence or probability delta.

## Acceptance Criteria

- [ ] `apply_evidence` rejects trends without an active UUID state version before
  querying, inserting evidence, or applying a delta.
- [ ] The active-evidence unique index uses PostgreSQL nulls-not-distinct
  semantics and its migration safely replaces the prior index.
- [ ] Unit tests cover the fail-closed null-state path and preserve the valid
  duplicate/race no-op paths.
- [ ] Integration coverage proves duplicate null-state active evidence cannot be
  committed.
- [ ] Architecture and data-model documentation state the current claim-aware
  uniqueness key.

## Validation

- Targeted trend-engine unit tests
- Targeted migration/integration tests
- `make typecheck`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`
