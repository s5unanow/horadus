# TASK-383: Switch Agent Workflow Surfaces to Implement Context-Pack Mode

## Status

- Owner: Codex
- Started: 2026-04-21
- Current state: In progress
- Planning Gates: Required — shared workflow guidance and command registry behavior

## Goal (1-3 lines)

Switch canonical implementation-facing Horadus workflow callers from plain
`context-pack` to `context-pack --mode implement --format json` while keeping
default broad-context behavior available for human-oriented usage.

## Inputs

- Spec/backlog references:
  `tasks/BACKLOG.md` (`TASK-383`), `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints:
  `tools/horadus/python/horadus_workflow/repo_workflow.py`,
  `tools/horadus/python/horadus_workflow/task_workflow_policy.py`,
  `tools/horadus/python/horadus_workflow/task_workflow_query.py`,
  `docs/AGENT_RUNBOOK.md`,
  `ops/skills/horadus-cli/SKILL.md`,
  `ops/skills/horadus-cli/references/commands.md`,
  `ops/skills/ship-it/SKILL.md`,
  `tests/workflow/`,
  `tests/horadus_cli/v2/`
- Preconditions/dependencies:
  `TASK-380`, `TASK-381`, and `TASK-365` already landed implement-mode output,
  spec resolution, sprint orientation, and retrieval behavior eval coverage.

## Outputs

- Expected behavior/artifacts:
  canonical implementation workflow command surfaces render
  `context-pack --mode implement --format json`; default-mode broad output
  remains the fallback for human general use and archived/default query paths.
- Validation evidence:
  targeted workflow/CLI unit coverage, explicit `make typecheck`, retrieval
  behavior eval guidance present in operator docs, pre-push local review, full
  local gate, canonical finish/lifecycle completion.

## Non-Goals

- Explicitly excluded work:
  changing the default unflagged `context-pack` payload, changing retrieval
  source-selection logic itself, or broadening RFC-001 beyond the already
  approved Phase 1 implement-mode contract.

## Scope

- In scope:
  enumerate implementation-facing callers, update shared workflow command
  registries and agent skills/docs, preserve unaffected default-mode callers,
  and add regression coverage for both changed and unchanged paths.
- Out of scope:
  human broad-context documentation that intentionally describes plain
  `context-pack` behavior, archived task retrieval semantics, and unrelated
  workflow-command cleanup.

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  centralize the command switch in the canonical workflow registries and update
  only the implementation-facing docs/skills that directly instruct autonomous
  task execution.
- Rejected simpler alternative:
  updating only prose docs without changing the shared workflow registries would
  leave generated/query-backed command surfaces stale and create split guidance.
- First integration proof:
  `make test-integration-docker` because the task changes push/PR workflow
  surfaces and completion guidance.
- Waivers:
  none planned; keep default-mode query/archive helpers on the unchanged path as
  the explicit unaffected-caller proof.

## Plan (Keep Updated)

1. Preflight (branch, context pack, caller inventory, exec plan)
2. Implement shared workflow registry and implementation-surface doc/skill updates
3. Validate updated caller coverage plus unaffected default-mode coverage
4. Ship (local review, local gate, finish, lifecycle)

## Decisions (Timestamped)

- 2026-04-21: Use an exec plan instead of a task spec because the task changes
  shared workflow guidance across code, docs, and skills and already has a
  precise backlog contract.
- 2026-04-21: Treat `task_workflow_query.py` archived/default substitutions as
  intentional unaffected callers; only the implementation workflow registry and
  its direct consumers should switch modes.
- 2026-04-21: Reuse the existing runbook retrieval-eval command section instead
  of introducing separate policy text; update implementation-facing command
  references to point at that trigger.

## Risks / Foot-guns

- Updating only one of the duplicate workflow registries could split CLI versus
  workflow helper guidance -> patch `repo_workflow.py` and
  `task_workflow_policy.py` together and test both.
- Over-eager replacement could break human broad-context or archived retrieval
  instructions -> keep default-mode/archive-specific query strings unchanged and
  assert them in regression tests.
- Doc-only command drift could reappear in skills or runbook references -> audit
  the skill command reference and `/ship-it` workflow in the same branch.

## Validation Commands

- `make typecheck`
- `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit`
- `uv run --no-sync horadus tasks local-review --format json`
- `make test-integration-docker`
- `uv run --no-sync horadus tasks local-gate --full`
- `uv run --no-sync horadus tasks finish TASK-383`
- `uv run --no-sync horadus tasks lifecycle TASK-383 --strict`

## Notes / Links

- Caller audit:
  implementation-facing callers to switch are
  `tools/horadus/python/horadus_workflow/repo_workflow.py`,
  `tools/horadus/python/horadus_workflow/task_workflow_policy.py`,
  `docs/AGENT_RUNBOOK.md`,
  `ops/skills/horadus-cli/SKILL.md`,
  `ops/skills/horadus-cli/references/commands.md`,
  and `ops/skills/ship-it/SKILL.md`.
- Unaffected callers to preserve:
  `tools/horadus/python/horadus_workflow/task_workflow_query.py`,
  `tests/horadus_cli/v2/test_task_query.py`,
  `tests/horadus_cli/v2/test_task_query_context_pack_modes.py`
- Relevant modules:
  `tools/horadus/python/horadus_workflow/task_workflow_context_pack_implement.py`,
  `tools/horadus/python/horadus_workflow/task_workflow_query.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
