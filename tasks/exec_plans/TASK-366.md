# TASK-366: Add a Code-Health Erosion Eval for Changed Python Surfaces

## Status

- Owner: Codex
- Started: 2026-04-08
- Current state: In progress
- Planning Gates: Required — shared eval/tooling contract and new structural regression signal

## Goal (1-3 lines)

Add a deterministic repo-owned eval that compares touched Python files against a
base revision and reports whether the changed surfaces got structurally worse.
The signal must reuse existing code-shape analysis rather than inventing a new
parser stack or opaque reviewer score.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` `TASK-366`
  - `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_workflow/code_shape.py`
  - `src/eval/`
  - `tools/horadus/python/horadus_cli/_ops_registration.py`
  - `tests/workflow/test_code_shape.py`
  - `tests/horadus_cli/v2/`
- Preconditions/dependencies:
  - Reuse `TASK-328` / `TASK-350` code-shape analyzers and AST measurements.
  - Keep output deterministic and explainable for later reuse by `TASK-367` and `TASK-369`.

## Outputs

- Expected behavior/artifacts:
  - `horadus eval code-health` command for explicit base/head diff or current branch vs merge-base
  - Deterministic artifact summarizing changed-file structural deltas and any regressions
  - Explainable metric set that extends beyond line count and cyclomatic complexity
- Validation evidence:
  - Targeted workflow + CLI unit coverage for improve / flat / regress scenarios
  - Repo fast gate and strict local gate before completion

## Non-Goals

- Explicitly excluded work:
  - Enforcing the new signal inside `make agent-check` or `local-gate` in this task
  - Rewriting the existing code-shape checker into a second abstraction layer
  - Using LLM scoring or subjective text review to judge code health

## Scope

- In scope:
  - Extract reusable file-level structural measurements from current code-shape logic
  - Compare changed tracked Python files between two revisions
  - Emit human-readable and JSON-friendly regression summaries
  - Wire the eval into the existing Horadus CLI eval surface
- Out of scope:
  - Non-Python files
  - Repo-wide historical trend storage for code-health runs
  - Local-review prompt changes and gate ratcheting work queued in later tasks

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Reuse the existing AST measurement path in `code_shape.py`, add a small comparison layer, and keep the eval artifact as a file-backed deterministic summary.
- Rejected simpler alternative:
  - Shelling out to third-party diff-quality tools would be faster initially but would bypass the repo-owned parser/ratchet logic and create a second metric source of truth.
- First integration proof:
  - Targeted CLI invocation against fixture repos in unit coverage plus the normal local gate stack.
- Waivers:
  - N/A currently.

## Plan (Keep Updated)

1. Preflight (branch, context pack, required exec plan, identify reuse points)
2. Implement reusable structural measurements and base/head diff evaluation
3. Wire `horadus eval code-health` and artifact rendering
4. Validate with improve/flat/regress tests, then run required gates
5. Ship through the normal Horadus finish flow

## Decisions (Timestamped)

- 2026-04-08: Use an exec plan instead of a short spec because the task changes shared workflow/eval contracts and touches CLI wiring. (Matches planning-gate policy.)
- 2026-04-08: Keep the first version file-level and deterministic so downstream tasks can consume a stable artifact before any future member-level refinements. (Minimizes surface area.)

## Risks / Foot-guns

- Merge-base discovery can be brittle in tests -> isolate git resolution behind a narrow helper with fixture-friendly overrides.
- Overly noisy metrics would make later gate use painful -> keep only a small set of explainable deltas and require explicit worsened metrics in every flag.
- Reusing code-shape internals carelessly could bloat `code_shape.py` -> extract the smallest reusable helpers instead of embedding eval logic into the checker path.

## Validation Commands

- `make typecheck`
- `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit`
- `uv run --no-sync pytest tests/unit/eval/ -v -m unit`
- `make agent-check`
- `make test-integration-docker`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none; backlog entry is authoritative task definition
- Relevant modules:
  - `tools/horadus/python/horadus_workflow/code_shape.py`
  - `tools/horadus/python/horadus_cli/_ops_registration.py`
  - `src/eval/regression_intake.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
