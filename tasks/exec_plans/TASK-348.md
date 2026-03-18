# TASK-348: Make `horadus tasks finish` fail loudly and recover cleanly in the review window

## Status

- Owner: Codex
- Started: 2026-03-17
- Current state: In progress
- Planning Gates: Required — touches allowlisted oversized workflow files under `tools/horadus/python/horadus_workflow/task_workflow_finish/` and `pr_review_gate.py`

## Goal (1-3 lines)

Make the `horadus tasks finish` review gate visibly alive, fail with concrete
recoverable blockers when GitHub payload reads go bad, and distinguish
actionable current-head review blockers from stale review artifacts.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-348`), `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints: `tools/horadus/python/horadus_workflow/pr_review_gate.py`, `tools/horadus/python/horadus_workflow/task_workflow_finish/`, `tools/horadus/python/horadus_cli/`, `docs/AGENT_RUNBOOK.md`
- Preconditions/dependencies: guarded branch start complete via `uv run --no-sync horadus tasks safe-start TASK-348 --name finish-review-window-recovery`

## Outputs

- Expected behavior/artifacts:
  - `horadus tasks finish` emits periodic review-window status with reviewer, head, and deadline/remaining time
  - malformed/truncated GitHub review-gate payloads become explicit recoverable blockers or are retried safely
  - current-head unresolved threads are surfaced early and remain clearly separated from stale/outdated review artifacts
- Validation evidence:
  - targeted workflow and CLI tests for wait-state output, malformed payload recovery, unresolved-thread blocking, head refresh, and same-head recovery after resolution

## Non-Goals

- Explicitly excluded work:
  - changing repo-wide review policy beyond the finish/review-gate flow
  - redesigning unrelated task lifecycle commands

## Scope

- In scope:
  - review-window status output and timeout messaging
  - robust GitHub payload parsing/failure surfaces in review-gate reads
  - thread-state classification and operator next-step guidance
  - docs and regression tests
- Out of scope:
  - unrelated workflow CLI refactors
  - provider-level GitHub CLI behavior changes outside Horadus handling

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - add focused helpers around status emission and review-gate fetch/parsing instead of broad workflow rewrites
- Rejected simpler alternative:
  - only adding extra print lines would leave malformed payloads and stale/current thread ambiguity unresolved
- First integration proof:
  - targeted finish/review test suites pass with the new blocker/status semantics
- Waivers:
  - none

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-17: planning gates required because the task touches allowlisted oversized workflow modules and should keep them flat or reduce them where practical. (reason: repo policy)

## Risks / Foot-guns

- Review-gate semantics are easy to regress across stale/current-head edge cases -> add targeted fixture-style tests for both pass and block paths.
- Extra status output could become noisy or flaky in tests -> centralize formatting and assert on stable fragments.
- GitHub CLI error handling can mask the real blocker -> preserve concrete next-step text when payload parsing fails.

## Validation Commands

- `pytest tests/horadus_cli/v2/task_finish tests/workflow/test_pr_review_gate_state.py`
- `python scripts/check_code_shape.py`
- `uv run --no-sync horadus tasks local-gate`

## Notes / Links

- Spec: `tasks/BACKLOG.md` (`TASK-348`)
- Relevant modules: `tools/horadus/python/horadus_workflow/pr_review_gate.py`, `tools/horadus/python/horadus_workflow/task_workflow_finish/_review_window.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
