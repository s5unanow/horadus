# TASK-XXX: Short Title

Use this template for new implementation specs. Keep it lightweight for small
tasks, but make the execution contract explicit.

## Problem Statement

What is wrong, missing, or risky today? State the operator/runtime impact in
1-3 short paragraphs.

## Inputs

- Source-of-truth docs or backlog links the implementer must read first
- Runtime/code paths, configs, fixtures, or data contracts that constrain the work
- Preconditions, dependencies, or required environment assumptions

## Outputs

- Concrete code/docs/artifacts expected from this task
- User-visible or operator-visible behavior changes
- Required validation evidence (tests, local gate, benchmark artifact, etc.)

## Non-Goals

- Explicitly excluded follow-ups or adjacent work
- Any human-gated/manual steps not covered by this task

**Planning Gates**: `Required` | `Not Required` — short reason

Use `Required` when the task has `Exec Plan: Required`, when the task changes
shared workflow/policy behavior, or when the author explicitly opts in.
Use `Not Required` only for the quiet-path small-task case and include a short
reason. The authoritative marker lives on the exec plan when one exists,
otherwise on the spec, otherwise on the backlog entry. If the backlog entry is
the only artifact and planning gates are required, `context-pack` and the
warn-only validator should surface that as a missing planning artifact rather
than treating the backlog body as the permanent gate/waiver home.

## Phase -1 / Pre-Implementation Gates (Only If `Planning Gates: Required`)

- `Simplicity Gate`: What existing surface is being extended, and why is that
  the smallest safe change instead of a new top-level surface?
- `Anti-Abstraction Gate`: What concrete duplication, provider boundary, or
  test seam justifies any new wrapper/adapter/manager/repository?
- `Integration-First Gate`:
  - Validation target:
  - Exercises:
- `Determinism Gate`: Triggered | Not applicable — short reason
- `LLM Budget/Safety Gate`: Triggered | Not applicable — short reason
- `Observability Gate`: Triggered | Not applicable — short reason

Keep the answers short and decision-shaped. If an exec plan also exists, keep
the gate answers here compact and record rejected simpler alternatives or
justified waivers in that plan’s `Gate Outcomes / Waivers` section. Reuse the
canonical example at `tasks/specs/275-finish-review-gate-timeout.md`.

## Shared Workflow/Policy Change Checklist (Only If Applicable)

- Apply these guardrails only when changing shared workflow helpers, shared
  workflow config, or review/merge policy behavior; do not inflate unrelated
  tasks with generic process boilerplate.
- Before changing shared workflow helpers or shared workflow config,
  enumerate every caller that depends on the shared behavior.
- When shared workflow behavior changes, add at least one regression test for
  an unaffected caller so the change does not silently break other workflow
  entry points.
- Before changing review, comment, or reaction handling in merge policy
  logic, define the current-head and current-window semantics for each signal
  and regression-test both the intended pass path and at least one stale or
  non-applicable signal path.

## Acceptance Criteria

- [ ] Add concrete, observable completion checks here
- [ ] Prefer behavior/result statements over implementation trivia

## Validation

- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`
- Add task-specific commands as needed

## Notes

- Keep sections short for small tasks; use bullets instead of prose where possible.
- For larger tasks, add diagrams/examples only when they clarify the contract.
