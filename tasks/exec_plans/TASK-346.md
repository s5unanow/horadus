# TASK-346: Front-load adversarial review guidance for high-risk cross-surface tasks

## Status

- Owner: Codex automation
- Started: 2026-03-21
- Current state: Done
- Planning Gates: Required - shared workflow/policy behavior and operator-facing guidance changes

## Goal (1-3 lines)

Push high-risk cross-surface tasks toward adversarial review before the first
push by surfacing explicit local-review guidance, fallback behavior, and
review-batching expectations in repo-owned workflow surfaces.

## Inputs

- Spec/backlog references:
  - `tasks/CURRENT_SPRINT.md`
  - `tasks/BACKLOG.md` (`TASK-346`)
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_workflow/task_workflow_query.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_policy.py`
  - `tools/horadus/python/horadus_cli/task_query.py`
  - `tests/horadus_cli/v2/test_task_query.py`
  - `tests/workflow/test_task_workflow.py`
  - `docs/AGENT_RUNBOOK.md`
  - `AGENTS.md`
- Preconditions/dependencies:
  - Reuse the existing `horadus tasks context-pack` and `horadus tasks local-review` surfaces
  - Keep guidance compatible with current provider selection/fallback behavior while `TASK-334` remains open

## Outputs

- Expected behavior/artifacts:
  - Repo-owned detection for high-risk cross-surface tasks in the context-pack path
  - Explicit pre-push adversarial review guidance and fallback instructions
  - Updated operator documentation and policy language that discourages single-fix re-review churn
- Validation evidence:
  - Targeted CLI/workflow unit coverage for the new guidance path
  - `make agent-check`

## Non-Goals

- Explicitly excluded work:
  - Changing provider-specific local-review subprocess contracts
  - Remote PR review-gate logic in `horadus tasks finish`
  - Generic process boilerplate for low-risk tasks

## Scope

- In scope:
  - Defining a minimal repo-owned “high-risk cross-surface” heuristic
  - Surfacing pre-push local-review guidance through context-pack output/data
  - Documenting provider-unavailable fallback behavior and batching expectations before re-review
  - Regression coverage for a high-risk guidance path and an unaffected task-query caller
- Out of scope:
  - New task taxonomy across the entire backlog
  - Provider auto-installation or auth bootstrapping

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Extend `context-pack` because it is already the canonical task-context surface and can recommend pre-push review without changing merge policy.
- Rejected simpler alternative:
  - Doc-only guidance was rejected because the failure mode came from workflow timing and would stay easy to skip without an operator-facing CLI reminder.
- First integration proof:
  - `uv run --no-sync horadus tasks context-pack TASK-346` now surfaces pre-push review guidance for the task, and the focused task-query/workflow suites pass with the new contract.
- Waivers:
  - None

## Plan (Keep Updated)

1. Preflight and planning-intake edits for sprint/exec-plan state
2. Implement high-risk guidance detection and context-pack output/data changes
3. Add tests plus doc/policy updates
4. Validate and ship through the guarded task lifecycle

## Decisions (Timestamped)

- 2026-03-21: Use `context-pack` as the pre-push guidance surface so agents see the advice before implementation/push rather than only inside `finish`.
- 2026-03-21: Keep the heuristic intentionally narrow and repo-owned instead of adding a broad risk classifier that would generate noisy guidance for ordinary tasks.

## Risks / Foot-guns

- Overbroad heuristics could spam low-risk tasks -> gate the guidance to explicit multi-surface/shared-workflow signatures.
- Shared workflow output changes can break adjacent query surfaces -> add one regression test for an unaffected task-query handler.
- Guidance without fallback can still lead to skipped review -> include an explicit provider-unavailable/manual fallback note in both CLI output and docs.

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v2/test_task_query.py tests/workflow/test_task_workflow.py`
- `make agent-check`

## Notes / Links

- Spec: none; backlog entry in `tasks/BACKLOG.md`
- Relevant modules:
  - `tools/horadus/python/horadus_workflow/task_workflow_query.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_policy.py`
  - `tools/horadus/python/horadus_cli/task_query.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
