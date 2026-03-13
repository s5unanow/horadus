# TASK-328: Add Code-Shape Guardrails to Prevent Module Sprawl

## Status

- Owner: Codex
- Started: 2026-03-14
- Current state: In progress
- Planning Gates: Required — shared workflow/policy change with repo-wide gate impact

## Goal (1-3 lines)

Define and enforce lightweight code-shape guardrails that stop new oversized
modules from appearing, ratchet existing hotspots downward over time, and make
task authors acknowledge structural debt when they touch known problem files.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-328`)
  - `tasks/specs/328-add-code-shape-guardrails-to-prevent-module-sprawl.md`
- Runtime/code touchpoints:
  - `AGENTS.md`
  - `tasks/specs/TEMPLATE.md`
  - `docs/AGENT_RUNBOOK.md`
  - `Makefile`
  - `.github/workflows/ci.yml`
  - candidate checker location under `scripts/`
  - workflow validation tests under `tests/workflow/`
- Preconditions/dependencies:
  - preserve the current Horadus workflow model: small repo-owned scripts,
    clear task contracts, and static validation in `agent-check` / local gate
  - keep legacy hotspots working while preventing silent growth

## Outputs

- Expected behavior/artifacts:
  - repo-owned code-shape policy in workflow guidance and task-spec guidance
  - repo-owned thresholds/allowlist artifact for legacy exceptions at
    `config/quality/code_shape.toml`
  - lightweight checker for file size, function size, and ratchet semantics
  - gate wiring in local and CI workflows
  - tests that prove pass/fail, legacy allowlist, and waiver behavior
- Validation evidence:
  - targeted workflow/checker tests
  - `make agent-check`
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Explicitly excluded work:
  - decomposing every current oversized module or test file in the same task
  - replacing import-boundary tests or module-ownership tests already present
  - adopting a broad style/composition framework beyond this focused guardrail
    set
  - defining the broader docstring/comment policy that belongs to `TASK-255`

## Scope

- In scope:
  - codify concrete thresholds and ratchet rules for module and function size
  - define how workflow planning gates apply when touching oversized files
  - build a deterministic repo-owned checker with a narrow waiver surface
  - wire the checker into local and CI paths
  - document the contract where authors already look for workflow truth
- Out of scope:
  - large production refactors of `src/core/config.py`,
    `src/processing/pipeline_orchestrator.py`, `src/api/routes/trends.py`, or
    oversized tests
  - subjective architectural review rules that cannot be checked or recorded
    consistently

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - implement one small AST-aware checker that enforces a few high-signal rules
    with deterministic thresholds and explicit allowlisted legacy exceptions
  - treat existing hotspots as baseline inventory and block only new violations
    or regressions that make the allowlisted hotspots worse
  - keep thresholds in a repo-owned artifact so future ratchet changes are
    reviewable without editing checker code blindly
- Rejected simpler alternative:
  - policy-only guidance in `AGENTS.md` would drift because authors could still
    grow large files without any gate feedback
  - a blanket hard fail on every existing oversized file would create a flag
    day and likely prevent adoption
- First integration proof:
  - use current hotspot inventory as seed data for the ratchet/allowlist
  - prove the checker runs through the same fast and full gates agents already
    use
- Waivers:
  - any waiver surface should be repo-owned, explicit, and narrow; avoid a
    free-form ignore list that becomes a second backlog

## Plan (Keep Updated)

1. Establish baseline shape inventory and choose thresholds
2. Define the repo-owned thresholds/allowlist artifact and waiver semantics
3. Codify policy in `AGENTS.md` and the task spec template
4. Implement the checker and explicit legacy-waiver/ratchet format
5. Wire the checker into `make agent-check`, full local gate, and CI
6. Add workflow/checker tests for pass, fail, ratchet, and waiver cases
7. Re-run the relevant gates and adjust thresholds only if failure output shows
   the initial contract is too noisy

## Decisions (Timestamped)

- 2026-03-14: Treat this as a ratchet task, not a cleanup sweep, because the
  repo already contains oversized hotspots and the enforceable goal is to stop
  them from growing further.
- 2026-03-14: Keep the first-pass rule set small and objective: file size,
  function size, single-owner module rule, and workflow obligations when
  touching oversized files.
- 2026-03-14: Prefer a repo-owned checker over a third-party complexity suite
  so thresholds, waivers, and failure messages stay aligned with the Horadus
  task workflow.
- 2026-03-14: Keep threshold values reviewable in a repo-owned data/config
  artifact rather than hard-coding every waiver in the checker logic.
- 2026-03-14: Ship the first-pass budgets as `700` module lines for
  production/tooling/scripts, `1200` for tests, `100` function/method lines
  for production/tooling/scripts, and `160` for tests, with explicit ratchet
  entries for current legacy hotspots.

## Risks / Foot-guns

- Thresholds can be too strict for tests or schema-heavy files -> separate
  production/test budgets and explicit legacy allowlist entries where needed
- A waiver list can become a dumping ground -> require ratchet semantics and
  explicit repo-owned entries rather than ad hoc ignores
- This task can blur into style-policy work -> keep docstring/comment policy
  explicitly out of scope except for the minimum workflow cross-reference
- Failure messages can become noisy or vague -> keep output focused on file,
  measured value, threshold, and next action
- Workflow coupling can drift if only one gate is updated -> wire the checker
  into both local and CI paths and test the documented commands

## Validation Commands

- `uv run --no-sync horadus tasks context-pack TASK-328`
- `uv run --no-sync pytest tests/workflow/ -q`
- targeted `pytest` for the checker module and its workflow wiring
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec:
  - `tasks/specs/328-add-code-shape-guardrails-to-prevent-module-sprawl.md`
- Implemented policy artifact:
  - `config/quality/code_shape.toml`
- Implemented checker:
  - `tools/horadus/python/horadus_workflow/code_shape.py`
  - `scripts/check_code_shape.py`
- Representative current hotspots motivating the ratchet model:
  - `src/core/config.py`
  - `src/processing/pipeline_orchestrator.py`
  - `src/api/routes/trends.py`
  - `tests/horadus_cli/v2/task_finish/test_finish_data.py`
- Canonical example:
  - `tasks/specs/275-finish-review-gate-timeout.md`
