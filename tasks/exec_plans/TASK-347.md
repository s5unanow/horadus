# TASK-347: Investigate and stabilize hanging `horadus tasks local-review` runs

## Status

- Owner: Codex
- Started: 2026-03-17
- Current state: In progress
- Planning Gates: Required — workflow-tooling task expected to touch multiple files and operator-facing command behavior

## Goal (1-3 lines)

Reproduce the hanging `horadus tasks local-review` failure in a stable fixture,
pin it to the provider invocation path, and make the command fail within a
bounded timeout with actionable diagnostics instead of hanging indefinitely.

## Inputs

- Spec/backlog references:
  - `tasks/CURRENT_SPRINT.md`
  - `tasks/BACKLOG.md` (`TASK-347`)
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_workflow/task_workflow_local_review.py`
  - `tools/horadus/python/horadus_workflow/_task_workflow_local_review_provider.py`
  - `tools/horadus/python/horadus_workflow/_task_workflow_local_review_constants.py`
  - `tools/horadus/python/horadus_workflow/_task_workflow_local_review_models.py`
  - `tools/horadus/python/horadus_cli/task_commands.py`
  - `tests/horadus_cli/v2/test_task_local_review.py`
  - `docs/AGENT_RUNBOOK.md`
- Preconditions/dependencies:
  - Preserve healthy provider success behavior and current fallback semantics
  - Keep the fix narrow to local-review orchestration rather than broad provider CLI redesign

## Outputs

- Expected behavior/artifacts:
  - Stable regression fixture that simulates a hung provider command
  - Bounded local-review timeout with explicit operator-facing failure text
  - Updated local-review docs if command behavior or operator expectations change
- Validation evidence:
  - Focused local-review unit tests
  - `make agent-check`

## Non-Goals

- Redesigning the provider prompt contract
- Reworking PR review-gate behavior
- Broad local-review fallback-policy changes beyond hang handling

## Scope

- In scope:
  - Reproduce hang via provider timeout fixture
  - Add bounded provider execution timeout handling
  - Surface timeout diagnostics in local-review command output and artifacts
  - Update tests and docs to match
- Out of scope:
  - Provider-specific quality tuning
  - New review heuristics or scoring behavior

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Treat provider hangs as provider-execution failures with a repo-owned timeout and explicit diagnostics.
- Rejected simpler alternative:
  - Relying on external shell timeouts would keep the failure outside Horadus and would not produce repo-owned diagnostics or regression coverage.
- First integration proof:
  - A simulated hung provider now returns an environment error with timeout lines instead of blocking the test process.
- Waivers:
  - None currently.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-17: Use a stable `TimeoutExpired` fixture to reproduce the hang path instead of relying on a real provider CLI to stall nondeterministically.

## Risks / Foot-guns

- Timeout too short could regress healthy local reviews -> choose a conservative default and keep success-path tests intact.
- Timeout handling could hide partial provider output -> preserve captured stdout/stderr in saved raw output and failure summaries.
- Task workflow module size could creep past the repo budget -> keep the change narrow and concentrated in provider execution helpers.

## Validation Commands

- `pytest tests/horadus_cli/v2/test_task_local_review.py`
- `make agent-check`

## Notes / Links

- Spec: backlog-only task; this exec plan is the authoritative planning artifact
- Relevant modules:
  - `tools/horadus/python/horadus_workflow/task_workflow_local_review.py`
  - `tools/horadus/python/horadus_workflow/_task_workflow_local_review_provider.py`
  - `tests/horadus_cli/v2/test_task_local_review.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
