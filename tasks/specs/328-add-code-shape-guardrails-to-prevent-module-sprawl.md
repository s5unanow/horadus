# TASK-328: Add Code-Shape Guardrails to Prevent Module Sprawl

## Problem Statement

The repo already has several modules and tests that have grown into
multi-responsibility files. Recent workflow tasks improved some of the worst
CLI/workflow hotspots through one-off decomposition work, but there is still no
shared rule set that tells an author when a module is too large, when a method
has become too broad, or when touching a legacy hotspot requires explicit
planning instead of another incremental expansion.

Without codified guardrails, structure drift becomes a social problem. The repo
needs cheap, enforceable code-shape rules that match its workflow model:
ratchet legacy hotspots, block new oversized surfaces, and force task authors
to acknowledge code-shape debt when they work in known problem areas.

## Inputs

- `AGENTS.md`
- `tasks/BACKLOG.md` (`TASK-328`)
- `tasks/CURRENT_SPRINT.md`
- `tasks/specs/TEMPLATE.md`
- `docs/AGENT_RUNBOOK.md`
- `Makefile`
- `.github/workflows/ci.yml`
- representative hotspot modules under `src/`, `tools/`, and `tests/`

## Outputs

- Repo-owned code-shape policy covering module size, function size, ownership
  boundaries, ratchet semantics, and workflow expectations for oversized-file
  touches
- A repo-owned thresholds/allowlist artifact that defines any temporary legacy
  exceptions explicitly
- An automated checker for those rules, wired into local and CI gates
- Updated task/spec guidance so code-shape waivers or follow-up cleanup debt
  are recorded explicitly instead of left implicit
- Regression coverage for representative pass, fail, ratchet, and waiver paths

## Non-Goals

- Refactoring every existing oversized module or test in the same task
- Introducing a heavyweight third-party complexity platform when a small
  repo-owned checker is sufficient
- Replacing existing import-boundary tests; this task should complement them
- Defining docstring/comment quality policy beyond any minimal cross-reference
  needed for code-shape workflow guidance; that scope belongs to `TASK-255`

**Planning Gates**: Required — shared workflow/policy change with repo-wide
quality-gate impact

## Phase -1 / Pre-Implementation Gates

- `Simplicity Gate`: Extend the repo's current workflow style with one small
  checker plus policy/docs updates instead of creating a second review process
  or a large lint framework.
- `Anti-Abstraction Gate`: Add only the minimum repo-owned script/config needed
  to enforce budgets and ratchets. Do not introduce new wrapper layers unless a
  stable provider boundary or reusable test seam exists.
- `Integration-First Gate`:
  - Validation target: the new code-shape check runs through the same local and
    CI gates agents already use.
  - Exercises: representative oversized-file failures, ratchet-safe legacy
    file touches, and explicit waiver handling.
- `Candidate first-pass thresholds`: Validate a small starting set such as
  lower budgets for new production modules, higher budgets for tests, and a
  separate cap for normal versus algorithm-heavy functions; finalize only after
  baseline inventory and failure output confirm the numbers are workable.
- `Determinism Gate`: Triggered — the checker must compute results
  deterministically from tracked repo files and stable thresholds.
- `LLM Budget/Safety Gate`: Not applicable — no runtime LLM behavior changes.
- `Observability Gate`: Triggered — failure output must explain which file,
  threshold, and ratchet rule failed so authors can act without re-reading the
  implementation.

## Shared Workflow/Policy Change Checklist

- Callers that depend on the current quality-gate and task-spec behavior:
  - `make agent-check`
  - `uv run --no-sync horadus tasks local-gate --full`
  - `.github/workflows/ci.yml`
  - `tasks/specs/TEMPLATE.md`
  - `docs/AGENT_RUNBOOK.md`
- Unaffected-caller regression target:
  - keep existing import-boundary and task-workflow tests green so the new code
    shape gate extends the workflow contract instead of perturbing unrelated
    task lifecycle behavior

## Acceptance Criteria

- [ ] Define repo-owned code-shape rules for production modules, tests, and
      oversize-file ratchets, including at least module size, function/method
      size, and single-owner module expectations
- [ ] Define when touching an oversized file requires planning gates, an exec
      plan, or an explicit follow-up debt record
- [ ] Add a lightweight automated checker for the rules, with a repo-owned
      thresholds artifact plus an allowlist or waiver format for legacy
      exceptions
- [ ] Fail new violations and regressions that make allowlisted legacy files
      worse, while allowing legacy hotspots to exist temporarily under ratchet
      semantics
- [ ] Wire the checker into repo-local and CI gates
- [ ] Add regression coverage for pass, fail, ratchet, and waiver scenarios
- [ ] Update workflow docs and task/spec guidance to reflect the new contract

## Validation

- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`
- targeted `pytest` coverage for the checker and workflow wiring

## Notes

- The first pass should prefer thresholds and waivers that are explainable and
  cheap to maintain over a wide complexity taxonomy.
- Existing oversized hotspots should be treated as migration inventory, not as
  a reason to delay enforcement on new growth.
