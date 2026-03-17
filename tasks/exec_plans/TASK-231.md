# TASK-231: Extend Event Invalidation into a Compensating Restatement Ledger

## Status

- Owner: Codex
- Started: 2026-03-17
- Current state: In progress
- Planning Gates: Required — probability-math semantics, replay correctness, migrations, and allowlisted Python hotspots are all in scope

## Goal (1-3 lines)

Replace one-off destructive invalidation behavior with an append-only
compensating-restatement ledger so the system can explain and deterministically
recompute how full invalidations, partial reinterpretations, and manual
compensations changed a trend over time.

## Inputs

- Spec/backlog references:
  - `tasks/CURRENT_SPRINT.md`
  - `tasks/BACKLOG.md` (`TASK-231`)
- Runtime/code touchpoints:
  - `src/storage/models.py`
  - `src/api/routes/feedback.py`
  - `src/api/routes/trends.py`
  - `src/core/trend_engine.py`
  - `src/processing/trend_impact_reconciliation.py`
  - `alembic/`
  - `tests/`
- Preconditions/dependencies:
  - Preserve existing active-evidence reads and event suppression behavior
  - Keep `current_log_odds` mutation concurrency-safe while making it verifiable
  - Avoid growing oversized route/model modules past code-shape limits

## Outputs

- Expected behavior/artifacts:
  - New append-only compensating restatement ledger linked to trends and optional evidence/feedback lineage
  - Event invalidation and Tier-2 supersession recorded as explicit compensating entries instead of silent reversals
  - Partial event restatement and manual trend compensation flows recorded in the same ledger
  - Deterministic projection/recompute helper that rebuilds a trend’s log-odds from baseline plus chronological evidence/restatement history with decay applied between state changes
  - Operator-facing read surface for lineage and projection verification
  - Migration, docs, and regression coverage
- Validation evidence:
  - Focused unit/integration tests for full invalidation, partial restatement, manual compensation, and projection rebuild
  - `make agent-check`
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Retroactively rewriting existing `trend_snapshots` or generated `reports`
- Building a broad analyst UI workflow for restatement authoring
- Replacing the current evidence table with a fully general double-entry accounting model

## Scope

- In scope:
  - Add a restatement ledger model + migration
  - Record compensating deltas for event invalidation, event restatement, Tier-2 reclassification, and manual trend overrides
  - Add deterministic trend-projection verification/recompute support
  - Expose ledger lineage and projection status via API responses
  - Document/report policy as belief-at-the-time artifacts with corrected-history available through the ledger/projection surface
- Out of scope:
  - Backfilling synthetic restatement rows for historical invalidations that predate the ledger
  - Changing snapshot cadence or report generation strategy beyond surfacing the policy

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Keep `trend_evidence` as the append-only record of original scored evidence applications.
  - Add a separate append-only restatement ledger for later signed compensating deltas.
  - Define projection as: baseline value advanced through time, with exponential decay applied between chronological evidence/restatement entries and each entry’s signed delta applied at its recorded time.
  - Treat historical snapshots/reports as belief-at-the-time artifacts; do not mutate them retroactively.
- Rejected simpler alternative:
  - Encoding compensation only in `human_feedback.corrected_value` would not provide queryable lineage, deterministic recompute, or a unified contract for Tier-2 supersession and manual overrides.
- First integration proof:
  - A trend with original evidence, a later partial restatement, and a manual compensating override recomputes to the stored `current_log_odds` with negligible drift.
- Waivers:
  - `src/storage/models.py`, `src/api/routes/feedback.py`, `src/api/routes/trends.py`, and `src/core/trend_engine.py` remain legacy hotspots; helper extraction is allowed to keep their ratchets flat rather than shrink them in this task.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-17: Use a separate append-only restatement ledger instead of mutating evidence rows with net-adjusted deltas. This keeps original scoring history intact and makes later corrections explicit.
- 2026-03-17: Model trend recompute as a chronological state machine with decay between entries rather than as a simple sum. This preserves existing lazy-decay semantics while making the value deterministic to verify.
- 2026-03-17: Keep snapshots and reports immutable as historical “belief at the time” artifacts; expose corrected-history semantics through the new ledger/projection surface instead of rewriting history.

## Risks / Foot-guns

- Missing ledger entries on one correction path -> centralize entry creation in shared helpers and regression-test all mutation paths.
- Projection drift due to timestamp ordering or naive decay math -> sort chronologically, normalize to UTC, and add exact reconstruction tests.
- Code-shape regression in already-large modules -> extract helpers/models into new modules instead of adding large inline blocks.

## Validation Commands

- `pytest tests/unit/api/test_feedback.py`
- `pytest tests/unit/api/test_trends.py`
- `pytest tests/unit/storage/test_model_metadata.py`
- `pytest tests/unit/processing/test_trend_impact_reconciliation.py`
- `pytest tests/integration/test_feedback_invalidation.py`
- `pytest tests/integration/test_trend_evidence_reclassification.py`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: backlog-only task; this exec plan is the authoritative planning artifact
- Relevant modules:
  - `src/api/routes/feedback.py`
  - `src/api/routes/trends.py`
  - `src/core/trend_engine.py`
  - `src/processing/trend_impact_reconciliation.py`
  - `src/storage/models.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
