# TASK-255: Add a Targeted Docstring Quality Gate for High-Value Surfaces

## Status

- Owner: Codex
- Started: 2026-04-15
- Current state: In progress
- Planning Gates: Required — estimate exceeds 2 hours, the task spans shared quality gates/docs, and the declared scope includes allowlisted production hotspots

## Goal (1-3 lines)

Add a scoped docstring policy for the repo’s high-value Python surfaces so
agents and humans get better guidance on public APIs and complex invariants
without turning the codebase into a blanket "document every helper" exercise.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-255`)
  - `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints:
  - `pyproject.toml`
  - `Makefile`
  - `.github/workflows/ci.yml`
  - `src/core/`
  - `src/processing/`
  - `src/workers/`
  - `docs/AGENT_RUNBOOK.md`
  - `tests/`
- Preconditions/dependencies:
  - keep the policy deterministic and path-scoped rather than adding a blanket
    repo-wide prose requirement
  - preserve the existing quality-gate entrypoints used by local and CI flows
  - avoid forcing verbose docstrings onto trivial private helpers whose names,
    types, and tests already communicate intent

## Outputs

- Expected behavior/artifacts:
  - a documented docstring policy for selected high-value runtime paths
  - automated enforcement for the scoped policy in the repo’s local and CI
    quality gates
  - targeted docstring additions where the new policy requires them
  - regression coverage for pass/fail behavior and scoped exclusions
- Validation evidence:
  - targeted test coverage for the new docstring quality gate
  - `make agent-check`
  - `make test-integration-docker`
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Explicitly excluded work:
  - requiring exhaustive docstrings across the full repository
  - converting private helper internals into prose-heavy documentation
  - broad style-guide changes unrelated to the scoped high-value paths

## Scope

- In scope:
  - define which module surfaces, public APIs, and complex invariant-heavy
    functions in `src/core/`, `src/processing/`, and `src/workers/` need
    docstrings
  - wire an automated, deterministic check into the existing repo gate flow
  - update operator-facing guidance on when to use docstrings vs inline
    comments vs no extra prose
  - add the minimum docstrings needed for the selected surfaces to satisfy the
    new policy
- Out of scope:
  - repo-wide pydocstyle cleanup across unrelated packages
  - non-docstring comment rewrites outside the selected high-value surfaces
  - refactoring allowlisted hotspot modules for structure/size as part of this
    task

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: extend the existing repo-owned quality
  gate flow with a narrow, explicit docstring policy for selected high-value
  paths instead of adding a blanket documentation mandate.
- Rejected simpler alternative: enabling a repo-wide "all public functions need
  docstrings" rule would create noisy failures on low-value helpers and
  encourage stale prose that does not improve comprehension.
- First integration proof: targeted gate tests covering required docstrings,
  permitted omissions for trivial helpers, and gate wiring before the full
  local gate.
- Hotspot Outcome: keep-flat-with-rationale — the task may add docstrings in
  allowlisted runtime hotspots such as `src/core/trend_engine.py`,
  `src/processing/pipeline_orchestrator.py`, or `src/workers/tasks.py`, but it
  will avoid structure-changing refactors because this task’s goal is scoped
  documentation policy rather than hotspot cleanup.
- Waivers: none.

## Plan (Keep Updated)

1. Preflight task start and inspect the current docstring/lint baseline for the
   declared runtime surfaces.
2. Choose the smallest enforceable scoped policy and wire it into the existing
   repo quality-gate entrypoints.
3. Add the minimum required docstrings and operator guidance for the selected
   high-value surfaces.
4. Add targeted regression coverage, run the required local proofs, and finish
   the canonical branch/PR lifecycle.

## Decisions (Timestamped)

- 2026-04-15: Use an exec plan instead of a lightweight spec because the task
  estimate, file count, and hotspot-triggered planning gate all require a
  stronger execution contract.
- 2026-04-15: Keep the policy intentionally scoped to high-value runtime
  surfaces and complex invariants instead of enforcing universal docstrings.

## Risks / Foot-guns

- An over-broad rule could create churn and stale prose -> baseline the current
  surfaces first and keep exclusions explicit for trivial private helpers.
- A narrow rule that is hard to explain could confuse contributors -> document
  path scope and the docstring/comment/no-prose decision points in the runbook.
- Gate drift between local and CI paths could make the rule flaky -> wire the
  enforcement through the existing shared quality-gate entrypoints and test the
  unaffected callers.

## Validation Commands

- `uv run --no-sync horadus tasks context-pack TASK-255`
- targeted `pytest` for the docstring gate and workflow wiring
- `make agent-check`
- `make test-integration-docker`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none
- Relevant modules: `src/core/`, `src/processing/`, `src/workers/`,
  `tools/horadus/python/horadus_workflow/`, `tests/`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
