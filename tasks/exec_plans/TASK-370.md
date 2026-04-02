# TASK-370: Local Task Intake and Deliberate Backlog Promotion

## Status

- Owner: codex
- Started: 2026-04-02
- Current state: In progress
- Planning Gates: Required — shared workflow/tooling contract and live task-capture policy

## Goal (1-3 lines)

Add a gitignored, repo-owned task-intake flow so agents can capture follow-up
work without editing tracked ledgers, and add an explicit promotion path that
turns a selected intake item into a canonical `tasks/BACKLOG.md` task block.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-370`)
  - `tasks/CURRENT_SPRINT.md`
  - `AGENTS.md`
  - `docs/AGENT_RUNBOOK.md`
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_cli/`
  - `tools/horadus/python/horadus_workflow/`
  - `tests/horadus_cli/`
  - `tests/workflow/`
- Preconditions/dependencies:
  - Keep capture local and gitignored under `artifacts/agent/`
  - Preserve canonical backlog task shape and next-id bookkeeping
  - Do not broaden `safe-start` / preflight behavior in this task

## Outputs

- Expected behavior/artifacts:
  - `horadus tasks intake add|list|groom|promote`
  - Local JSONL intake storage under `artifacts/agent/task-intake/entries.jsonl`
  - Canonical backlog promotion that allocates the next `TASK-###`
  - Updated operator/agent docs
- Validation evidence:
  - Parser and workflow unit coverage for intake flows
  - `make typecheck`
  - `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit`
  - `make agent-check`
  - `make test-integration-docker`
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Explicitly excluded work:
  - Shared tracked intake ledgers under `tasks/`
  - Multi-item backlog promotion in one command
  - Changes to `safe-start`, preflight eligibility, or sprint/spec auto-wiring
  - Cross-process locking for intake persistence

## Scope

- In scope:
  - New intake persistence/helpers and CLI wiring
  - Backlog promotion helpers for next-id parsing, canonical block rendering,
    block insertion, and header increment
  - Documentation for when to keep follow-ups on the current task branch versus
    intake them for later grooming
- Out of scope:
  - New backlog schema fields beyond the current canonical task block shape
  - Automation/report integration with intake

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Reuse the existing `tasks` command family and the repo’s gitignored
    `artifacts/agent/` pattern instead of inventing a new tracked intake file.
- Rejected simpler alternative:
  - Writing pending follow-ups directly into `tasks/BACKLOG.md` would preserve
    no local/non-authoritative staging area and would keep causing dirty-tree
    friction during unrelated active work.
- First integration proof:
  - `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit`
- Validation outcomes:
  - `make typecheck` passed on 2026-04-02.
  - `make agent-check` passed on 2026-04-02.
  - `make test-integration-docker` passed on 2026-04-02.
  - `uv run --no-sync horadus tasks local-gate --full` passed on 2026-04-02.
- Waivers:
  - No separate process lock in v1; atomic rewrite is sufficient for the
    single-checkout local usage assumed by the task.

## Plan (Keep Updated)

1. Preflight (create plan, guarded task start, confirm command seams)
2. Implement intake persistence, CLI wiring, and backlog promotion helpers
3. Validate with targeted tests and repo gates
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-04-02: Use gitignored JSONL under `artifacts/agent/task-intake/` for
  pending intake because the repo already treats `artifacts/agent/` as the
  home for local non-authoritative workflow artifacts.
- 2026-04-02: Keep capture minimal and collect backlog-grade fields only during
  promotion to avoid reintroducing capture-time friction.
- 2026-04-02: Treat batched grooming as batch triage/status mutation in v1
  rather than multi-task backlog creation.

## Risks / Foot-guns

- Backlog insertion can drift from the repo’s canonical task shape ->
  implement focused render/insert helpers and test exact output.
- Next-id parsing can fail on malformed backlog headers -> fail closed with a
  validation error and keep intake state unchanged.
- Shared CLI wiring can regress unrelated task commands -> keep a regression
  assertion for an existing unaffected command path.

## Validation Commands

- `make typecheck`
- `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit`
- `make agent-check`
- `make test-integration-docker`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: backlog entry only; no separate task spec
- Relevant modules:
  - `tools/horadus/python/horadus_cli/task_commands.py`
  - `tools/horadus/python/horadus_cli/task_workflow_core.py`
  - `tools/horadus/python/horadus_workflow/task_repo.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_shared.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
