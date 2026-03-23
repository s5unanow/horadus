# TASK-202: Make Degraded Replay Queue Retryable Instead of Fail-Once Terminal

## Status

- Owner: Codex automation
- Started: 2026-03-23
- Current state: In progress
- Planning Gates: Required - estimate exceeds 2 hours and the task changes replay behavior across worker/runtime surfaces

## Goal (1-3 lines)

Keep degraded-mode replay auditable while allowing transient replay failures to
retry automatically with bounded backoff instead of becoming terminal on the
first exception.

## Inputs

- Spec/backlog references: `tasks/CURRENT_SPRINT.md`, `tasks/BACKLOG.md#task-202`
- Runtime/code touchpoints: `src/workers/_task_maintenance.py`, `src/core/config.py`, `docs/ARCHITECTURE.md`, `tests/unit/workers/test_task_maintenance.py`
- Preconditions/dependencies: clean `main`, passed `horadus tasks eligibility/preflight`, task branch created with `safe-start`

## Outputs

- Expected behavior/artifacts:
  - replay worker keeps retryable failures in a bounded retry/backoff loop
  - exhausted or explicitly non-retryable failures become terminal with clear audit metadata
  - replay selection skips pending rows whose next retry window has not opened yet
- Validation evidence:
  - targeted unit coverage for retry classification, deferred retries, retry-success, and exhausted failure behavior
  - `make agent-check` after Python edits

## Non-Goals

- Explicitly excluded work:
  - replay queue schema/migration redesign
  - broader degraded-mode extraction-state work from `TASK-338`
  - changing Celery scheduling cadence itself

## Scope

- In scope:
  - bounded replay retry classification and backoff
  - audit metadata for retry scheduling / terminal disposition
  - focused docs update for replay worker semantics
  - worker-unit regression coverage
- Out of scope:
  - replay queue UI/operator APIs
  - non-replay pipeline retry semantics

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - keep the existing queue schema and use existing status plus audit `details` metadata to represent retry schedule/disposition, because the queue is intentionally small and does not need a migration-backed scheduler field for this task
- Rejected simpler alternative:
  - marking every failure terminal preserves current data shape but leaves transient provider/DB failures unrecoverable, which is the bug this task exists to close
- First integration proof:
  - one transient replay failure leaves the row pending with next-attempt metadata, a later due run succeeds, and an exhausted retry path ends in terminal `error`
- Waivers:
  - none

## Plan (Keep Updated)

1. Preflight (branch, context pack, baseline worker-unit test)
2. Implement bounded replay retry/backoff helpers and terminal disposition tracking
3. Add regression tests plus replay-worker docs update
4. Validate targeted tests + `make agent-check`
5. Ship (ledger updates, `horadus tasks finish TASK-202`)

## Decisions (Timestamped)

- 2026-03-23: Avoid a schema migration unless implementation proves it necessary; the existing queue fields plus JSON details are sufficient for bounded retries on a <=20-item operational queue.

## Risks / Foot-guns

- Retry classification that is too broad could hide permanent data issues -> keep obvious data-contract problems terminal/manual-review and test both paths
- Backoff that is only recorded but not enforced would cause hot-loop retries -> compute due-at consistently in selection and terminal handling helpers
- Audit metadata drift could make lineage/review harder -> update `details` in one helper so retry and terminal paths write the same shape

## Validation Commands

- `uv run --no-sync pytest tests/unit/workers/test_task_maintenance.py -q`
- `make agent-check`

## Notes / Links

- Spec: `tasks/BACKLOG.md#task-202`
- Relevant modules: `src/workers/_task_maintenance.py`, `src/core/config.py`
