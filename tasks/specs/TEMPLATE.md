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
