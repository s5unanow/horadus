# TASK-235: Add Event Split/Merge Lineage for Evolving Stories

## Status

- Owner: Codex automation
- Started: 2026-03-21
- Current state: In progress
- Planning Gates: Required - multi-surface task with migration/API/processing work and material edits to allowlisted `src/storage/models.py`

## Goal (1-3 lines)

Add an auditable event-lineage path for split/merge corrections, surface bounded
cluster-risk metadata on events, and keep trend evidence/projection state
unambiguous by reversing stale evidence and queueing affected events for replay.

## Inputs

- Spec/backlog references:
  - `tasks/CURRENT_SPRINT.md`
  - `tasks/BACKLOG.md` (`TASK-235`)
- Runtime/code touchpoints:
  - `src/processing/event_clusterer.py`
  - `src/storage/models.py`
  - `src/api/routes/events.py`
  - `src/core/trend_restatement.py`
  - `src/processing/pipeline_orchestrator.py`
  - `tests/unit/api/test_events.py`
  - `tests/unit/processing/test_event_clusterer.py`
  - `tests/integration/test_events_api.py`
  - `alembic/versions/`
- Preconditions/dependencies:
  - Reuse the existing trend-restatement ledger for deterministic compensation
  - Reuse the existing replay queue so repaired events can be reclassified safely

## Outputs

- Expected behavior/artifacts:
  - Append-only event-lineage records for split/merge repairs
  - Event detail payloads expose lineage metadata
  - Events persist bounded split-risk / cohesion metadata
  - Split/merge repair invalidates stale evidence and queues affected events for replay
- Validation evidence:
  - Focused unit + integration coverage for split, merge, and no-op lineage paths
  - `make agent-check`
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Explicitly excluded work:
  - Automatic operator-free split/merge decisioning
  - Perfect claim-level redistribution of prior evidence without replay
  - Broader entity-resolution or clustering-policy redesign outside TASK-235

## Scope

- In scope:
  - New storage schema for lineage and bounded cluster-risk metadata
  - Event repair service/API for split + merge
  - Deterministic stale-evidence reversal and replay enqueue for affected events
  - Event detail/debug response updates and regression coverage
- Out of scope:
  - New review UI surfaces
  - Cross-task backlog cleanup unrelated to TASK-235

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Keep `event_items` as current-state truth and use an append-only lineage ledger
  - Reverse stale active evidence via `trend_restatements` and queue affected events for Tier-2 replay
- Rejected simpler alternative:
  - Only tagging events as merged/split without reversing prior evidence would leave belief state ambiguous
- First integration proof:
  - Pending
- Waivers:
  - None

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement lineage storage + repair service + API
3. Validate with targeted tests, `make agent-check`, and local gate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-21: Use an append-only event-lineage ledger instead of historical `event_items` snapshots to keep current-state queries simple while preserving correction auditability.
- 2026-03-21: Reverse stale trend evidence on repaired events and queue replay rather than attempting unsafe claim-by-claim evidence migration during repair.

## Risks / Foot-guns

- Event repairs can leave stale trend evidence active -> invalidate and restate all active evidence on affected events in the same transaction.
- Replay queue reuse could duplicate pending work -> rely on the existing `(stage, event_id)` uniqueness guard and use bounded repair metadata in `details`.
- `src/storage/models.py` is allowlisted and already at its ratchet -> keep new ORM ownership in a separate model module and only register imports from `models.py`.

## Validation Commands

- `pytest tests/unit/processing/test_event_clusterer.py tests/unit/api/test_events.py`
- `pytest tests/integration/test_events_api.py tests/integration/test_feedback_invalidation.py`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none; backlog entry in `tasks/BACKLOG.md`
- Relevant modules:
  - `src/storage/models.py`
  - `src/storage/restatement_models.py`
  - `src/processing/event_clusterer.py`
  - `src/api/routes/events.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
