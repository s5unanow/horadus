# TASK-205: Requeue retryable pipeline failures instead of permanently erroring items

## Status

- Owner: Codex
- Started: 2026-03-16
- Current state: Done
- Planning Gates: Required - pipeline retry semantics, worker orchestration, and allowlisted pipeline module changes

## Goal (1-3 lines)

Stop converting transient provider/network/LLM pipeline failures into terminal raw-item
`ERROR` states. Retryable failures should bubble to Celery so task retry/backoff runs while
database side effects roll back to a safe retryable state.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` -> `TASK-205`
- Runtime/code touchpoints: `src/processing/pipeline_orchestrator.py`, `src/workers/tasks.py`, `src/workers/_task_processing.py`, `docs/ARCHITECTURE.md`, `tests/unit/processing/`, `tests/unit/workers/`
- Preconditions/dependencies: guarded task start from synced `main`; preserve existing budget-exceeded defer semantics

## Outputs

- Expected behavior/artifacts:
  - retryable per-item failures are classified distinctly from terminal failures
  - retryable failures raise back to the worker task instead of persisting `ERROR`
  - task retries remain safe because transaction rollback clears partial DB side effects
  - docs and tests describe the new retry behavior
- Validation evidence:
  - targeted unit tests for retryable prepare/Tier-1/embedding/clustering/Tier-2 failures
  - worker task retry configuration/assertions still pass
  - local gate covering Python code shape remains green

## Non-Goals

- Explicitly excluded work:
  - changing backlog prioritization beyond activating `TASK-205`
  - redesigning the whole processing transaction model around per-item commits
  - changing unrelated collector retry semantics

## Scope

- In scope:
  - retryability classification helpers for pipeline exceptions
  - worker-visible propagation path for retryable item failures
  - tests for rollback-safe retry behavior and unchanged terminal failure handling
  - architecture doc note for retry semantics
- Out of scope:
  - new database schema or migrations
  - changing budget exceeded handling from `PENDING`
  - broader observability redesign unless required by the code change

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: preserve the current single transaction for one pipeline task and let retryable exceptions abort the run so session rollback restores item/event/trend state before Celery retries.
- Rejected simpler alternative: leaving retryable failures as per-item `ERROR` would continue to strand items and bypass worker retry/backoff.
- First integration proof: `workers.process_pending_items` already uses Celery autoretry; the missing behavior is allowing retryable exceptions to escape the pipeline.
- Waivers: none

## Plan (Keep Updated)

1. Preflight (branch, tests, context) - done
2. Implement - done
3. Validate - done
4. Ship (PR, checks, merge, main sync) - in progress

## Decisions (Timestamped)

- 2026-03-16: Use task-level rollback/retry for retryable failures instead of adding per-item commits. This is the smallest change that restores safe retries without widening transactional complexity.
- 2026-03-16: Extract pipeline carrier types into `src/processing/pipeline_types.py` rather than widening the code-shape allowlist for `pipeline_orchestrator.py`.

## Risks / Foot-guns

- One retryable item failure will roll back successful work earlier in the same batch -> acceptable for current bounded scale; covered in docs/plan as deliberate tradeoff.
- Misclassifying a terminal validation error as retryable could cause noisy repeat retries -> keep retry taxonomy narrow and regression-test terminal paths.
- Misclassifying a retryable provider failure as terminal would preserve the original bug -> add direct tests for known OpenAI/httpx/network failure classes.

## Validation Commands

- `pytest tests/unit/processing/test_pipeline_orchestrator.py tests/unit/processing/test_pipeline_orchestrator_additional.py tests/unit/workers/test_celery_setup.py`
- `python scripts/check_code_shape.py`

## Notes / Links

- Spec: `tasks/BACKLOG.md`
- Relevant modules: `src/processing/pipeline_orchestrator.py`, `src/workers/tasks.py`, `src/workers/_task_processing.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
