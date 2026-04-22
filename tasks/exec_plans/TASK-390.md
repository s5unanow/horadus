# TASK-390: Add dirty-main watchdog for agent sessions

## Status

- Owner: Codex
- Started: 2026-04-22
- Current state: Validating implementation and workflow proofs
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
- First integration proof: N/A — the task does not touch integration-covered or push/PR workflow paths.
- Pre-push local review sequencing: `horadus tasks local-review` needs a committed branch diff, so run it after the task commit and before push.
- Hotspot Outcome: keep-flat-with-rationale — the task must edit existing workflow hotspots because the enforcement contract already lives in shared Horadus workflow code.
- Waivers: none.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-04-22: Require an exec plan up front because the task changes shared workflow and operator-facing guardrail behavior. (reason: the task is small in runtime scope but high leverage in repo workflow policy)
- 2026-04-22: Keep task-start preflight unchanged and add a separate `horadus tasks assert-safe-worktree` watchdog for chat/agent sessions. (reason: it catches dirty `main` drift without broadening task-start enforcement for unrelated callers)
- 2026-04-22: Caller inventory before editing shared preflight helpers: `handle_preflight`, `eligibility_data`, `start_task_data`, `safe_start_task_data`, the `tasks preflight` CLI parser, and the task-workflow compatibility exports. (reason: shared helper changes must preserve existing task-start callers while adding the new watchdog surface)

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
