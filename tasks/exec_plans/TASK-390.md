# TASK-390: Add dirty-main watchdog for agent sessions

## Status

- Owner: Codex
- Started: 2026-04-22
- Current state: Not started
- Planning Gates: Required — guardrail work touches shared workflow enforcement and operator-facing policy surfaces.

## Goal (1-3 lines)

Add a repo-owned safeguard that detects tracked diffs on `main` during chat/agent work and
reports a clear workflow violation before work drifts outside the task-branch flow.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-390`)
- Runtime/code touchpoints: `tools/horadus/python/horadus_workflow`, `docs/AGENT_RUNBOOK.md`, `AGENTS.md`, `tests`
- Preconditions/dependencies: map the current task-start and worktree guard surfaces before choosing the watchdog entry point

## Outputs

- Expected behavior/artifacts: a documented repo-owned dirty-main guardrail with focused regression coverage for the intended trigger path
- Validation evidence: shared-workflow unit coverage, docs updates, and full repo workflow gates

## Non-Goals

- Explicitly excluded work: speculative Codex-app integration beyond the repo-owned Horadus surface, or broader worktree-isolation design

## Scope

- In scope: selecting the watchdog surface, guard behavior, docs updates, and regression tests
- Out of scope: unrelated review/merge policy changes or the separate worktree-isolation design tracked by `TASK-394`

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: add the guardrail at the narrowest repo-owned workflow surface that can reliably detect tracked diffs on `main`.
- Rejected simpler alternative: document the rule only and keep enforcement entirely manual.
- First integration proof: run focused workflow unit coverage plus the canonical local gate once the watchdog surface is implemented.
- Hotspot Outcome: keep-flat-with-rationale — the task must edit existing workflow hotspots because the enforcement contract already lives in shared Horadus workflow code.
- Waivers: none.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-04-22: Require an exec plan up front because the task changes shared workflow and operator-facing guardrail behavior. (reason: the task is small in runtime scope but high leverage in repo workflow policy)

## Risks / Foot-guns

- Over-eager detection could block legitimate task-branch work -> scope the check to tracked diffs on `main`.
- Workflow helpers have many callers -> keep the caller inventory explicit before implementation and preserve unaffected entry points with regression coverage.

## Validation Commands

- `make typecheck`
- `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit`
- `uv run --no-sync horadus tasks local-review --format json`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none yet
- Relevant modules: `tools/horadus/python/horadus_workflow`, `AGENTS.md`, `docs/AGENT_RUNBOOK.md`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
