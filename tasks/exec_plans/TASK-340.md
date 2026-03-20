# TASK-340: Split Event Epistemic State from Activity State

## Status

- Owner: Codex automation
- Started: 2026-03-20
- Current state: In progress
- Planning Gates: Required - migration scope, multiple runtime surfaces, and allowlisted Python files

## Goal (1-3 lines)

Split event lifecycle semantics into two explicit axes so corroboration,
contradiction, retraction, dormancy, and closure stop competing for one
overloaded field while keeping a narrow compatibility path for existing callers.

## Inputs

- Spec/backlog references: `tasks/CURRENT_SPRINT.md`, `tasks/BACKLOG.md#task-340`
- Runtime/code touchpoints: `src/storage/models.py`, `src/processing/event_lifecycle.py`, `src/processing/event_clusterer.py`, `src/processing/tier2_classifier.py`, `src/api/routes/events.py`, `src/api/routes/feedback.py`, `src/api/routes/feedback_models.py`, `src/workers/_task_retention.py`, `docs/DATA_MODEL.md`, `alembic/versions/`
- Preconditions/dependencies: clean `main`, passed `horadus tasks eligibility/preflight`, task branch created with `safe-start`

## Outputs

- Expected behavior/artifacts:
  - explicit `epistemic_state` and `activity_state` persisted on `events`
  - compatibility `lifecycle_status` retained but derived/maintained as deprecated legacy projection
  - event mention/decay/feedback flows update the correct axis
  - operator-facing event/review surfaces expose both axes and identify the changed axis
  - migration/backfill for legacy rows including archived feedback cases
- Validation evidence:
  - targeted unit tests for lifecycle manager, event APIs, feedback, retention helpers, and clusterer paths
  - `make agent-check` after Python edits

## Non-Goals

- Explicitly excluded work:
  - redesigning contradiction detection itself
  - removing the legacy compatibility field in the same task
  - broader replay/versioning changes from other sprint tasks

## Scope

- In scope:
  - schema + migration + backfill
  - compatibility mapping helper
  - lifecycle manager split logic
  - API and feedback contract updates
  - retention query updates that currently key off archived lifecycle
- Out of scope:
  - unrelated trend/state versioning tasks
  - non-event operator mutation contract work

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - add two first-class state columns and keep `lifecycle_status` as an explicitly deprecated compatibility projection to avoid breaking all existing callers at once
- Rejected simpler alternative:
  - replacing `lifecycle_status` outright in one pass would create wider churn across APIs, tests, and retention paths than this sprint task needs
- First integration proof:
  - event mention promotes or revives via epistemic/activity axes while legacy lifecycle remains consistent
- Waivers:
  - none

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement schema and state helper
3. Wire processing/API/feedback/retention behavior to the split axes
4. Validate targeted tests + `make agent-check`
5. Ship (ledger updates, `horadus tasks finish TASK-340`)

## Decisions (Timestamped)

- 2026-03-20: Keep `lifecycle_status` as a deprecated compatibility projection for this task because the repo still has several callers and tests depending on it.
- 2026-03-20: Use archived feedback lineage when backfilling legacy `archived` rows so operator noise/invalidation actions map to epistemic retraction instead of looking like normal closure.

## Risks / Foot-guns

- Legacy `archived` rows mix closure and suppression semantics -> backfill must inspect human feedback before assigning epistemic retracted vs confirmed
- API contract churn can sprawl into already-large files -> prefer helper extraction and surgical response-model changes
- Retention relies on archived semantics -> switch retention checks to activity closure rather than epistemic state

## Validation Commands

- `pytest tests/unit/processing/test_event_lifecycle.py tests/unit/processing/test_event_clusterer.py tests/unit/api/test_events.py tests/unit/api/test_feedback.py`
- `pytest tests/unit/workers/test_celery_setup.py tests/unit/workers/test_tasks_additional.py`
- `make agent-check`

## Notes / Links

- Spec: `tasks/BACKLOG.md#task-340`
- Relevant modules: `src/storage/models.py`, `src/processing/event_lifecycle.py`, `src/api/routes/events.py`, `src/api/routes/feedback.py`
