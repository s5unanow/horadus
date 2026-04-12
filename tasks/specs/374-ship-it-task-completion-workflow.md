# TASK-374: Add /ship-it Task Completion Workflow

## Problem Statement

Recent task work stopped after local code edits even though the repo’s
definition of autonomous completion is the full Horadus lifecycle
(`safe-start` through `finish` and strict lifecycle verification). The current
repo guidance says that clearly in `AGENTS.md`, but chat requests such as
"/ship-it" do not yet map to a repo-owned workflow surface that keeps that
contract front and center.

The repo needs a lightweight, explicit skill for this chat-time intent so the
agent treats "/ship-it" as "take an eligible task through canonical
completion" instead of "implement some code and stop."

## Inputs

- Canonical workflow policy in `AGENTS.md`
- Command index in `docs/AGENT_RUNBOOK.md`
- Existing repo workflow skill in `ops/skills/horadus-cli/SKILL.md`
- Active task selection rules in `tasks/CURRENT_SPRINT.md`

## Outputs

- A repo-owned `ops/skills/ship-it/SKILL.md` skill with a concrete completion
  contract for chat-time task delivery
- Policy/docs updates that make `/ship-it` discoverable and unambiguous for
  repo work in Codex chat
- Clear blocked-state instructions that require exact blocker reporting rather
  than vague partial completion claims

## Non-Goals

- Adding a new Horadus CLI command or automation runner
- Solving broader chat-on-`main`, hooks, worktree, or watchdog guardrails
- Changing the underlying task lifecycle semantics

**Planning Gates**: Required — shared workflow/policy guidance change

## Phase -1 / Pre-Implementation Gates

- `Simplicity Gate`: Add a thin repo-owned skill and explicit policy/doc links
  instead of inventing a second completion mechanism.
- `Anti-Abstraction Gate`: Reuse the existing Horadus CLI workflow and
  `horadus-cli` skill; this task should not add wrapper code around the task
  lifecycle.
- `Integration-First Gate`:
  - Validation target: docs/skill consistency plus the canonical local gate for
    the task branch.
  - Exercises: task selection guidance, completion criteria, and blocked-state
    wording remain aligned across the skill and repo policy docs.
- `Code Shape Gate`: Not applicable — no allowlisted production hotspot is in scope.
- `Determinism Gate`: Not applicable — no persisted state machine, concurrency,
  or math behavior changes.
- `LLM Budget/Safety Gate`: Not applicable — no runtime LLM path is modified.
- `Observability Gate`: Triggered — the skill must make the exact blocker and
  furthest completed lifecycle step explicit when delivery cannot complete.

## Shared Workflow/Policy Change Checklist (Only If Applicable)

- Shared workflow code is not changing in this task; the checklist applies only
  to the operator-facing policy/skill contract.

## Acceptance Criteria

- [ ] A repo-owned `/ship-it` skill exists and tells agents to select or infer
      the active eligible task, honor planning gates, and drive the canonical
      `safe-start` to `finish` lifecycle
- [ ] Repo policy/docs explicitly map `/ship-it` to that skill so chat requests
      use the same workflow contract consistently
- [ ] The skill defines blocked-state reporting in terms of exact blocker and
      furthest completed lifecycle step instead of vague partial completion

## Validation

- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Gate Outcomes / Waivers

- Targeted test proof: N/A — the task changes only docs/skills/ledger surfaces
  and does not introduce a narrower code-path test target beyond the baseline
  gates.
- Integration proof: N/A — the task does not touch integration-covered or
  push/PR workflow implementation paths.
