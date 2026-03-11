# TASK-295: Enforce Pre-Merge Task Closure State

## Status

- Owner: Codex
- Started: 2026-03-10
- Current state: In progress

## Goal (1-3 lines)

Make task completion fail closed unless the PR head already contains the final
ledger/archive closure state and the branch/PR head SHAs are aligned. Ensure
stale review threads do not block completion once they are outdated or resolved.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-295`)
- Runtime/code touchpoints: `src/horadus_cli/task_commands.py`, `src/horadus_cli/task_repo.py`, `scripts/check_pr_review_gate.py`
- Preconditions/dependencies: `TASK-294` landed quarterly closed-task archiving and `horadus tasks close-ledgers`

## Outputs

- Expected behavior/artifacts:
  - `horadus tasks finish` blocks merge until backlog/current sprint/completed/archive closure invariants hold on the PR head
  - strict lifecycle verification reports the same closure invariant
  - repo-side CI enforces the closure invariant for PR heads
  - stale/outdated review threads no longer block finish
- Validation evidence:
  - focused unit tests for finish/lifecycle/review-thread paths
  - script/unit coverage for repo-side closure guard
  - full local gate

## Non-Goals

- Explicitly excluded work:
  - guarded task-start ergonomics (`TASK-296`)
  - CLI test fixture decoupling (`TASK-293`)

## Scope

- In scope:
  - closure-state inspection helpers
  - head alignment enforcement
  - current-head vs outdated-thread review gating
  - CI workflow guard for closure invariants
- Out of scope:
  - changing the overall review timeout policy
  - redesigning the task ledgers again

## Plan (Keep Updated)

1. Inspect finish/lifecycle/review-gate/CI paths and map callers
2. Implement closure-state and head-alignment enforcement
3. Add CI guard and regression coverage
4. Validate and ship

## Decisions (Timestamped)

- 2026-03-10: Reuse the quarterly archive shard introduced in `TASK-294` as part of the completion invariant, so finish/lifecycle/CI all validate the same closed-task source of truth.

## Risks / Foot-guns

- Blocking early PRs too aggressively -> keep the CI guard focused on the `Primary-Task` closure invariant and make failures explicit
- Breaking unrelated finish paths -> add regression tests for unaffected happy paths and stale-thread paths

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v1/test_cli.py -q`
- `uv run --no-sync pytest tests/unit/scripts/test_check_pr_review_gate.py -q`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: `tasks/BACKLOG.md`
- Relevant modules: `src/horadus_cli/task_commands.py`, `src/horadus_cli/task_repo.py`, `scripts/check_pr_review_gate.py`
