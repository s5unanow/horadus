# TASK-389: Align Numeric ORM typing with Decimal semantics

## Status

- Owner: Codex
- Started: 2026-04-22
- Current state: Not started
- Planning Gates: Required — Numeric ORM semantics span shared storage and domain hotspots.

## Goal (1-3 lines)

Align Numeric-backed ORM annotations with the Decimal values already used at runtime so
probability, evidence, restatement, and cost paths stay type-safe and explicit.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-389`)
- Runtime/code touchpoints: `src/storage/models.py`, `src/storage/trend_state_models.py`, `src/storage/restatement_models.py`, `src/core/trend_engine.py`, `src/processing/cost_tracker.py`, `tests`
- Preconditions/dependencies: inspect current Numeric annotations, Decimal conversion boundaries, and affected typing/tests before edits

## Outputs

- Expected behavior/artifacts: Decimal-accurate ORM/domain typing plus explicit conversion boundaries where float APIs still exist
- Validation evidence: targeted typing/tests for Decimal semantics plus repo typecheck and affected unit/integration proof

## Non-Goals

- Explicitly excluded work: probability-math redesign, schema shape changes, or unrelated trend-engine refactors

## Scope

- In scope: touched Numeric ORM annotations, boundary conversions, and regression coverage for Decimal-vs-float drift
- Out of scope: unrelated API contract changes or wider storage cleanup beyond the impacted Numeric fields

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: tighten annotations and conversions only where Numeric-backed values already behave as Decimal at runtime.
- Rejected simpler alternative: leave float annotations in place and rely on informal caller discipline.
- First integration proof: run the targeted Decimal typing/tests plus the canonical local gate after the affected storage/domain surfaces are updated.
- Hotspot Outcome: keep-flat-with-rationale — the task must touch existing shared hotspots to align live Numeric semantics; defer extraction unless the implementation expands beyond the declared Decimal boundary.
- Waivers: none.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-04-22: Use an exec plan before implementation because the task touches allowlisted shared hotspots and shared typing surfaces. (reason: planning gates are required even before code changes start)

## Risks / Foot-guns

- Mixed float/Decimal boundaries can pass tests accidentally -> add explicit typing coverage at the conversion seams.
- Shared ORM typing can fan out into unrelated modules -> keep the edit set bounded to the declared Numeric-backed paths first.

## Validation Commands

- `make typecheck`
- `uv run --no-sync pytest tests/unit/ tests/integration/ -v -m "unit or integration"`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none yet
- Relevant modules: `src/storage/models.py`, `src/storage/trend_state_models.py`, `src/storage/restatement_models.py`, `src/core/trend_engine.py`, `src/processing/cost_tracker.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
