# TASK-318: Decompose `validate_assessment_artifacts.py` Into Focused Internal Modules

## Status

- Owner:
- Started: 2026-03-13
- Current state: Done
- Planning Gates: Required — the refactor must preserve a user-facing script entrypoint, stable CLI output, and multiple independent validation passes with regression-sensitive message ordering

## Goal (1-3 lines)

Break `scripts/validate_assessment_artifacts.py` into smaller focused internal
modules so each validation concern is independently testable and easier to
navigate without changing behavior, CLI output, exit codes, or test
expectations.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-318`)
  - `tasks/CURRENT_SPRINT.md`
  - `AGENTS.md` repo workflow guardrails
- Runtime/code touchpoints:
  - `scripts/validate_assessment_artifacts.py`
  - `tests/unit/scripts/test_validate_assessment_artifacts.py`
  - `docs/ASSESSMENTS.md`
- Preconditions/dependencies:
  - Preserve the existing script entrypoint and flag semantics
  - Keep validation ordering, wording, and exit codes stable
  - Avoid unrelated cleanup or feature changes

## Outputs

- Expected behavior/artifacts:
  - A thin `scripts/validate_assessment_artifacts.py` entrypoint
  - Focused internal validator modules grouped by responsibility
  - Regression tests showing behavior stays unchanged
- Validation evidence:
  - `tests/unit/scripts/test_validate_assessment_artifacts.py` passes
  - Script-level validation output remains unchanged for the covered cases

## Non-Goals

- Explicitly excluded work:
  - New validation rules or schema changes
  - Rewording findings, changing exit behavior, or altering flag names
  - Broad cleanup outside the validator refactor

## Scope

- In scope:
  - Extract markdown/artifact parsing helpers
  - Extract task/sprint/history loading helpers
  - Extract novelty, grounding, and cross-role overlap checks
  - Isolate CLI parsing and result assembly in the entrypoint or a thin facade
- Out of scope:
  - Changing `docs/ASSESSMENTS.md` command examples unless required by test fixture ownership
  - Changing how artifacts are authored or consumed

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Keep `scripts/validate_assessment_artifacts.py` as a stable facade and move logic into sibling internal modules.
- Rejected simpler alternative:
  - Keeping one monolithic script with comment sections would not provide cleaner ownership or independently testable validation passes.
- First integration proof:
  - The existing `tests/unit/scripts/test_validate_assessment_artifacts.py` suite captures the script behavior that must not change.
- Waivers:
  - Small internal indirection is acceptable if it preserves exact output and execution order.

## Plan (Keep Updated)

1. Preflight (task intake, branch, context, baseline tests)
2. Implement focused internal modules and thin entrypoint
3. Validate targeted tests and script behavior
4. Ship (task ledger updates, lifecycle verification)

## Decisions (Timestamped)

- 2026-03-13: Treat this as a new task rather than bundling it into earlier decomposition work. (reason: task ids are global and the user asked for repo workflow compliance)
- 2026-03-13: Keep the script file as the stable entrypoint and move only implementation details behind it. (reason: user explicitly requested unchanged entrypoint semantics)
- 2026-03-13: Preserve current wording and validation ordering even if that means some helpers remain slightly coupled. (reason: behavior preservation is the primary acceptance constraint)

## Risks / Foot-guns

- Finding order drifts after splitting passes -> keep orchestration order identical to the current script
- Moving helpers changes path/module import behavior under `python scripts/validate_assessment_artifacts.py` -> keep imports sibling-safe from the scripts directory
- Refactor quietly changes parsing edge cases -> cover key internal seams with targeted tests only where they do not alter the external assertions

## Validation Commands

- `uv run --no-sync horadus tasks context-pack TASK-318`
- `uv run --no-sync pytest tests/unit/scripts/test_validate_assessment_artifacts.py -q`
- `uv run --no-sync ruff check scripts/validate_assessment_artifacts.py scripts/validate_assessment_artifacts_*.py tests/unit/scripts/test_validate_assessment_artifacts.py`

## Notes / Links

- Spec:
  - Backlog entry only; this exec plan is the authoritative planning artifact.
- Relevant modules:
  - `scripts/validate_assessment_artifacts.py`
  - `tests/unit/scripts/test_validate_assessment_artifacts.py`
  - `docs/ASSESSMENTS.md`
