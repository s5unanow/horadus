# TASK-343: Add caller-aware validation packs for shared helper changes

## Status

- Owner: Codex automation
- Started: 2026-03-24
- Current state: Done
- Planning Gates: Required - shared workflow/tooling behavior change with cross-caller validation guidance

## Goal (1-3 lines)

Define a repo-owned validation-pack contract for shared helper edits so
`horadus tasks context-pack` can recommend the minimum dependent suites and
stronger type-check coverage before the first push.

## Inputs

- Spec/backlog references:
  - `tasks/CURRENT_SPRINT.md`
  - `tasks/BACKLOG.md` (`TASK-343`)
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_workflow/task_workflow_query.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_policy.py`
  - `tests/horadus_cli/v2/test_task_query.py`
  - `tests/workflow/test_task_workflow.py`
  - `docs/AGENT_RUNBOOK.md`
  - `AGENTS.md`
- Preconditions/dependencies:
  - Keep the guidance repo-owned and deterministic rather than deriving it from ad hoc task text
  - Preserve existing `context-pack` output for unaffected tasks/callers

## Outputs

- Expected behavior/artifacts:
  - A validation-pack contract for shared workflow/domain helper changes
  - `context-pack` recommendations that include dependent regression suites and full-repo type checking when applicable
  - Updated workflow guidance in operator docs/policy
- Validation evidence:
  - Focused task-query/workflow tests for the new recommendation path and an unaffected caller
  - `make agent-check`

## Non-Goals

- Explicitly excluded work:
  - Dynamic diff-aware file analysis inside `context-pack`
  - Replacing task-specific judgment for ordinary low-risk changes
  - Changing remote merge-gate behavior in `horadus tasks finish`

## Scope

- In scope:
  - Define a small repo-owned mapping from shared helper hotspots to dependent validation commands
  - Surface those commands through `context-pack` output/data
  - Document when full-repo type checking is required by the contract
  - Add regression coverage for one shared-helper case and one unaffected caller
- Out of scope:
  - Broad repo-wide automatic test selection
  - New backlog/task metadata fields

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Extend the existing `context-pack` recommendation surface with a narrow validation-pack layer keyed off repo-owned path prefixes and exact files.
- Rejected simpler alternative:
  - Doc-only guidance was rejected because the failure mode comes from operators validating only the obvious direct caller; the CLI needs to surface the dependent suites at runtime.
- First integration proof:
  - `uv run --no-sync horadus tasks context-pack TASK-343` lists dependent workflow/CLI suites plus `make typecheck` for the shared-helper case.
- Waivers:
  - None

## Plan (Keep Updated)

1. Add the exec plan and inspect current `context-pack`/policy helpers plus tests
2. Implement repo-owned validation-pack mapping and output/data surfacing
3. Add doc/policy updates and regression coverage
4. Validate with targeted tests, `make agent-check`, and finish the task lifecycle

## Decisions (Timestamped)

- 2026-03-24: Keep the contract path-based and repo-owned so recommendation behavior stays deterministic and testable without diff parsing.

## Risks / Foot-guns

- Overbroad packs could force unnecessary validation -> keep mappings narrow to shared-helper hotspots and shared math surfaces.
- Output changes can break adjacent task-query consumers -> add an unaffected caller regression test.
- Incomplete type-check guidance could preserve the original failure mode -> include full-repo type checking whenever the pack covers shared Python helpers or shared math.

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v2/test_task_query.py tests/workflow/test_task_workflow.py`
- `make agent-check`

## Notes / Links

- Spec: none; backlog entry in `tasks/BACKLOG.md`
- Relevant modules:
  - `tools/horadus/python/horadus_workflow/task_workflow_query.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_policy.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
