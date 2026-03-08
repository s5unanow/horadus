# TASK-259: Add a Mechanical Done-State Verifier and Explicit Lifecycle States

## Status

- Owner: Codex
- Started: 2026-03-08
- Current state: Validation complete; ready to ship

## Goal (1-3 lines)

Add a repo-owned task lifecycle verifier to `horadus` so "done" is reported
from one machine-checkable state model instead of inferred from scattered git,
PR, CI, and local sync signals.

## Scope

- In scope:
  - Add a structured lifecycle-state command under `horadus tasks`
  - Model at least local-only, pushed, PR-open, CI-green, merged, and local-main-synced states
  - Add a strict verifier mode for repo-policy completion
  - Reuse the lifecycle-state helper from other workflow commands where practical
  - Update agent-facing docs to define completion by verifier state
  - Add unit tests for lifecycle transitions and strict-failure cases
- Out of scope:
  - Docker readiness recovery (`TASK-261`)
  - Workflow skill/docs drift enforcement (`TASK-263`, `TASK-264`)
  - Additional completion-claim enforcement language beyond verifier-backed guidance (`TASK-262`)

## Plan (Keep Updated)

1. Inventory existing workflow state checks and map them into one lifecycle model
2. Implement a reusable lifecycle snapshot/helper plus CLI command and strict mode
3. Rewire docs/guidance and any finish-path reuse to point at the verifier
4. Validate with focused unit tests and the canonical local gate, then ship

## Decisions (Timestamped)

- 2026-03-08: Use one lifecycle-state helper as the authoritative model for task completion status so CLI commands can consume shared state instead of duplicating git/PR/CI checks.
- 2026-03-08: Resolve post-merge task state from the canonical `Primary-Task: TASK-XXX` PR metadata search plus merge-commit presence on local `main`, so verification still works after branch deletion.

## Risks / Foot-guns

- Post-merge state is harder to resolve once task branches are deleted -> use PR metadata and merge-commit presence on local `main` instead of relying only on the branch ref
- A new verifier can drift from finish semantics -> reuse lifecycle helpers inside workflow commands where completion is asserted
- Over-modeling edge states can make the command noisy -> keep one primary lifecycle state plus supporting detail fields in structured output

## Validation Commands

- `uv run --no-sync pytest tests/unit/test_cli.py -v`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: `tasks/BACKLOG.md` (`TASK-259`)
- Relevant modules: `src/horadus_cli/task_commands.py`, `src/horadus_cli/task_repo.py`, `tests/unit/test_cli.py`
