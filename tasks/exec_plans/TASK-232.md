# TASK-232: Strengthen Operator Adjudication Workflow for High-Risk Events

## Status

- Owner: Codex
- Started: 2026-03-25
- Current state: Done
- Planning Gates: Required — multi-surface API/storage changes, migration work, and operator workflow semantics are in scope

## Goal (1-3 lines)

Add a typed, append-only operator adjudication workflow for risky events so the
review queue can distinguish pending review from resolved/escalated work, reuse
the existing compensating-restatement path where applicable, and expose queue
metadata that a future UI can consume directly.

## Inputs

- Spec/backlog references:
  - `tasks/CURRENT_SPRINT.md`
  - `tasks/BACKLOG.md` (`TASK-232`)
- Runtime/code touchpoints:
  - `src/api/routes/feedback.py`
  - `src/api/routes/events.py`
  - `src/api/routes/feedback_models.py`
  - `src/api/routes/feedback_event_helpers.py`
  - `src/api/routes/_feedback_write_mutations.py`
  - `src/storage/restatement_models.py`
  - `src/storage/models.py`
  - `alembic/`
  - `tests/`
- Preconditions/dependencies:
  - Reuse the `TASK-231` compensating-restatement ledger for any event restate path
  - Keep append-only lineage for operator actions
  - Avoid growing the feedback route hotspot by extracting helpers where needed

## Outputs

- Expected behavior/artifacts:
  - Append-only `event_adjudications` ledger with explicit outcome, review state, override intent, and resulting-effect payload
  - Privileged event-adjudication write route that records confirm, suppress, restate, and taxonomy-escalation outcomes
  - Review queue ranking/filtering that surfaces contradiction-heavy, high-delta low-confidence, and taxonomy-gap-linked events with typed queue metadata
  - Event API metadata that exposes current operator-review state for a future UI without depending on a frontend implementation
  - Migration, docs, and regression coverage
- Validation evidence:
  - Focused unit tests for adjudication writes, queue ranking/filtering, and event review metadata
  - `make agent-check`
  - `uv run --no-sync pytest tests/unit/ -v -m unit`
  - `make test-integration-docker`
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Building a frontend workflow or assignment system for operators
- Replacing the existing `human_feedback` and `trend_restatements` lineage tables
- Reworking the whole event-state machine beyond the adjudication effects already owned by current feedback mutations

## Scope

- In scope:
  - Add an append-only event adjudication model + migration
  - Route operator adjudication writes through typed outcomes while reusing existing feedback/restatement side-effect helpers where appropriate
  - Extend review queue filtering/ranking with queue reasons and review status
  - Expose operator-review metadata on event/read surfaces
  - Update API/data-model docs for the new contract
- Out of scope:
  - Multi-operator assignment/claim locks
  - Bulk adjudication endpoints
  - Automatic taxonomy-gap resolution side effects beyond recording escalation status

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Keep `human_feedback` as the lower-level side-effect/audit surface for existing event mutations, but add `event_adjudications` as the canonical typed operator workflow ledger.
  - Map adjudication outcomes onto existing feedback/restatement flows only where those already own the event/trend mutation semantics (`confirm` -> pin/no-op feedback, `suppress` -> mark-noise semantics, `restate` -> existing restatement flow).
  - Treat `escalate_taxonomy_review` as a typed adjudication state that preserves append-only lineage and keeps queue/event metadata explicit without inventing new mutation semantics for taxonomy gaps.
  - Keep review queue ranking explainable by exposing the factors that caused inclusion and the latest review status.
- Rejected simpler alternative:
  - Extending `human_feedback.action` alone would still leave review-state inference ad hoc and would not provide a clean, typed operator workflow contract for queue filtering and future UI work.
- First integration proof:
  - An event can be adjudicated through confirm/suppress/restate/escalate paths, and the review queue/event detail reflect the derived review status plus any linked feedback/restatement effects.
- Waivers:
  - `src/storage/models.py` remains a legacy allowlisted hotspot; only minimal registration edits are allowed here.

## Plan (Keep Updated)

1. Preflight (branch, tests, context) — completed
2. Implement — completed
3. Validate — completed
4. Ship (PR, checks, merge, main sync) — in progress

## Decisions (Timestamped)

- 2026-03-25: Add a dedicated append-only adjudication ledger instead of overloading `human_feedback`, because queue review state and operator intent need a typed contract.
- 2026-03-25: Reuse the existing event feedback/restatement mutation helpers for suppress/restate effects so the task does not fork mutation semantics away from `TASK-231`.
- 2026-03-25: Surface queue reason codes and review status directly in API responses so the future UI can stay thin.

## Risks / Foot-guns

- Duplicating semantics between adjudications and feedback rows -> centralize the outcome mapping in one helper and store feedback linkage on the adjudication row.
- Inflating `feedback.py` past its ratchet -> extract queue/adjudication helpers into dedicated modules.
- Queue-status drift when taxonomy gaps or adjudications change -> compute current status from latest append-only adjudication plus open taxonomy-gap counts and regression-test both pending and escalated paths.

## Validation Commands

- `pytest tests/unit/api/test_feedback.py`
- `pytest tests/unit/api/test_events.py`
- `pytest tests/unit/storage/test_model_metadata.py`
- `make agent-check`
- `uv run --no-sync pytest tests/unit/ -v -m unit`
- `make test-integration-docker`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: backlog-only task; this exec plan is the authoritative planning artifact
- Relevant modules:
  - `src/api/routes/feedback.py`
  - `src/api/routes/events.py`
  - `src/storage/restatement_models.py`
  - `src/storage/models.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
