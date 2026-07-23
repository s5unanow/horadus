# TASK-422: Guard lineage-repair evidence invalidation against double-reversal

## Status

- Owner: Codex
- Started: 2026-07-23
- Current state: Validation complete; shipping lifecycle in progress
- Planning Gates: Required — correctness-critical concurrent probability repair

## Goal (1-3 lines)

Make split/merge evidence invalidation an atomic claim so only one concurrent
repair can reverse any original evidence delta.

## Inputs

- Spec/backlog references: `tasks/specs/422-lineage-invalidation-double-reversal.md`
- Runtime/code touchpoints: `_repair_affected_events`,
  `_claim_evidence_invalidation`, `TrendEvidence`, `TrendRestatement`
- Preconditions/dependencies: PostgreSQL `UPDATE ... RETURNING`

## Outputs

- Expected behavior/artifacts: lineage-owned guarded claim, claim-aware
  compensation, focused unit/concurrency tests, corrected architecture/data-model docs
- Validation evidence: targeted unit and PostgreSQL integration tests, typecheck,
  agent check, full local gate

## Non-Goals

- Explicitly excluded work: reconciliation refactor, restatement/decay changes,
  split/merge route contract changes

## Scope

- In scope: lineage-repair evidence invalidation and its direct tests/docs
- Out of scope: already-guarded reconciliation behavior and shared abstraction

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: copy the existing conditional
  `UPDATE ... RETURNING` claim into a lineage-owned companion module and gate
  compensation on its boolean result
- Rejected simpler alternative: row locking broadens lock duration and still
  duplicates the atomic state transition already proven in reconciliation
- First integration proof: two transactions claim one evidence row and exactly
  one returns success
- Hotspot Outcome: keep-flat-with-rationale — no allowlisted hotspot changes;
  keep the existing production module structurally flat
- Waivers: none

## Plan (Keep Updated)

1. Completed — preflight, branch, caller enumeration, and baseline tests
2. Completed — guarded claim and claim-aware repair loop
3. Completed — unit/concurrency regressions, docs, and pre-commit gates
4. In progress — closed ledgers; complete PR/merge/main-sync lifecycle

## Decisions (Timestamped)

- 2026-07-23: Leave reconciliation unchanged and duplicate its private guarded
  claim locally, avoiding behavioral drift in an already-correct path.
- 2026-07-23: Test the claim with independent PostgreSQL transactions because
  mock row counts cannot prove the concurrency guarantee.

## Risks / Foot-guns

- ORM identity state can remain stale after a Core update -> synchronize the
  successfully claimed in-memory row explicitly, matching reconciliation.
- Concurrent test can deadlock if neither claimant commits -> each worker
  commits immediately after its claim before returning.
- Production module structural growth -> keep the claim and tests in new
  lineage-owned modules.

## Validation Commands

- `uv run --no-sync pytest tests/unit/processing/test_event_lineage_invalidation.py`
- PostgreSQL integration test for concurrent claim
- `make typecheck`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

Validation evidence on 2026-07-23:

- Focused lineage unit tests: 40 passed
- PostgreSQL integration and migration suite: 22 passed, including the
  two-transaction single-winner claim regression
- `make typecheck`: passed
- `make agent-check`: passed
- Code-shape check: passed with `event_lineage.py` held at 643 lines

## Notes / Links

- Spec: `tasks/specs/422-lineage-invalidation-double-reversal.md`
- Relevant modules: `src/processing/event_lineage.py`,
  `src/processing/trend_impact_reconciliation.py`
