# TASK-367: Ratchet Changed-File Code-Health Regressions in Local Gates

## Status

- Owner: Codex
- Started: 2026-04-09
- Current state: Done
- Planning Gates: Required — shared workflow/gate behavior across agent-check and canonical local validation

## Goal (1-3 lines)

Use the existing deterministic changed-file code-health eval as an author-facing
ratchet in local workflow commands. Regressions on touched Python files should
fail fast, while untouched legacy debt must remain non-blocking.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` `TASK-367`
  - `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints:
  - `Makefile`
  - `tools/horadus/python/horadus_workflow/task_workflow_gate_steps.py`
  - `tools/horadus/python/horadus_cli/ops_commands.py`
  - `tests/horadus_cli/v2/test_task_workflow.py`
  - `tests/unit/eval/test_code_health.py`
- Preconditions/dependencies:
  - `TASK-366` provides the deterministic `horadus eval code-health` command and artifact format.
  - The no-diff branch case already exits cleanly with `Compared files: 0`.

## Outputs

- Expected behavior/artifacts:
  - `make agent-check` runs the code-health eval and surfaces its summary in the normal fast-gate output.
  - `uv run --no-sync horadus tasks local-gate --full` includes a fail-closed changed-file code-health step.
  - Existing untouched hotspots remain allowed unless the current diff makes them worse.
- Validation evidence:
  - Unit coverage for the local-gate step list and agent-check contract updates.
  - Eval coverage for no-op, improving, regressing, and unaffected-file diff behavior.

## Non-Goals

- Explicitly excluded work:
  - Changing the metric set or artifact schema introduced in `TASK-366`
  - Blocking on non-Python files or whole-repo historical debt unrelated to the current diff
  - Reworking CI/pre-commit policy unless the current local-gate wiring proves insufficient

## Scope

- In scope:
  - Reuse the existing `horadus eval code-health` CLI path in local gate commands
  - Keep the full gate step list deterministic and testable
  - Update operator-facing workflow guidance where command behavior changes
- Out of scope:
  - Local-review prompt changes planned for `TASK-369`
  - New allowlist or exception mechanisms for changed-file regressions

## Phase -1 / Pre-Implementation Gates

- `Simplicity Gate`: Reuse the existing CLI command directly in `Makefile` and
  the canonical gate-step list instead of adding a wrapper script or second
  implementation path.
- `Anti-Abstraction Gate`: Keep any new helper in the existing gate-step module
  if command construction needs reuse; do not introduce a new workflow layer
  for one eval command.
- `Integration-First Gate`:
  - Validation target: fast-gate Makefile wiring, full local-gate step list,
    and changed-file eval regressions in fixture repos.
  - Exercises: no-op diff, improving diff, regressing diff, and unaffected-file
    behavior.
- `Determinism Gate`: Required — the ratchet must stay fully deterministic and
  artifact-backed because it gates author workflow.
- `LLM Budget/Safety Gate`: Not applicable — no LLM path changes.
- `Observability Gate`: Required — the fast gate and full gate must expose the
  existing eval summary clearly enough that authors can see which files and
  metrics regressed.

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Invoke `horadus eval code-health --output-dir ai/eval/results` directly from
    `make agent-check` and from the canonical `full_local_gate_steps()` list so
    both paths share the same exit behavior and human-readable summary.
- Rejected simpler alternative:
  - Folding the ratchet into `scripts/check_code_shape.py` would couple
  unrelated policy layers and lose the explicit base/head diff semantics already
  implemented in the dedicated eval command.
- First integration proof:
  - Targeted unit coverage for the Makefile/gate-step contracts plus direct eval
    fixture coverage for clean, improving, regressing, and unaffected diffs.
- Waivers:
  - N/A currently.

## Plan (Keep Updated)

1. Preflight (branch, context pack, required exec plan, inspect existing code-health output)
2. Implement gate wiring in `Makefile` and `task_workflow_gate_steps.py`
3. Update regression tests and operator docs
4. Validate with targeted tests, `make agent-check`, integration proof, and full local gate
5. Ship through the normal Horadus finish flow

## Decisions (Timestamped)

- 2026-04-09: Use an exec plan rather than a short spec because the task changes shared local-gate behavior and operator-facing workflow guidance.
- 2026-04-09: Keep the ratchet on the existing `horadus eval code-health` command so both gate paths share one source of truth for exit codes, output, and artifacts.
- 2026-04-09: Implementation and targeted validation passed, but strict completion is blocked by unrelated dependency-audit failure on `cryptography 46.0.6` (`CVE-2026-39892`); captured as `INTAKE-0002` instead of mixing the dependency bump into this branch.
- 2026-04-11: `TASK-373` cleared the repo-wide dependency-audit blocker, and the full `TASK-367` validation stack then passed unchanged on top of the updated mainline.

## Risks / Foot-guns

- Adding the step in the wrong order could hide failures behind later noisy gates -> place it early enough to be visible, but after code-shape so structural context remains adjacent.
- A changed-file ratchet can become noisy if it accidentally inspects unchanged files -> rely on the current diff-scoped eval behavior and retain coverage for unaffected-file cases.
- Updating only one local workflow path would create policy drift -> cover both `make agent-check` and `full_local_gate_steps()` in tests.
- Unrelated repo-wide gate failures can block task completion after implementation -> capture them in intake and keep the task branch scoped to `TASK-367`.

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
  - `tools/horadus/python/horadus_workflow/task_workflow_gate_steps.py`
  - `tools/horadus/python/horadus_cli/ops_commands.py`
  - `tools/horadus/python/horadus_workflow/code_health.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
