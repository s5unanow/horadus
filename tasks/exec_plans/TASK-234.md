# TASK-234: Make Uncertainty and Momentum First-Class Trend State

## Status

- Owner: Codex automation
- Started: 2026-03-26
- Current state: In progress - validation complete, shipping
- Planning Gates: Required — task materially touches allowlisted oversized Python modules in trend API/report surfaces

## Goal (1-3 lines)

Promote uncertainty and recent directional momentum from implied presentation
details to explicit, bounded trend-state outputs that stay stable across API
and report paths without adding a second mutable scoring system.

## Inputs

- Spec/backlog references:
  `tasks/CURRENT_SPRINT.md`, `tasks/BACKLOG.md`
- Runtime/code touchpoints:
  `src/core/risk.py`, `src/api/routes/trends.py`,
  `src/core/report_generator.py`, `src/core/trend_engine.py`,
  `src/api/routes/trend_api_models.py`, `tests/unit/api/test_trends.py`,
  `tests/unit/core/test_report_generator.py`
- Preconditions/dependencies:
  clean/synced `main`, guarded task branch start, task remains non-human-gated

## Outputs

- Expected behavior/artifacts:
  shared deterministic helpers for bounded uncertainty/momentum,
  trend API responses expose them directly,
  weekly/monthly report statistics include them directly
- Validation evidence:
  targeted unit tests for API/report/state helper behavior and `make agent-check`

## Non-Goals

- Explicitly excluded work:
  new operator-managed scoring knobs, reworking core log-odds math,
  changing report narrative prompts beyond consuming new stats,
  separate workflow repair for the `context-pack TASK-234` archived mismatch

## Scope

- In scope:
  deterministic derivation from recent evidence/snapshot windows,
  first-class response/report payload fields,
  regression coverage for stable/accelerating/high-uncertainty cases
- Out of scope:
  entity registry work, source credibility redesign, migration-heavy trend-state persistence

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  derive bounded state from existing evidence and snapshot history in shared helpers
  so API and reports consume one contract
- Rejected simpler alternative:
  leave uncertainty/momentum as scattered presentation-only calculations; that
  fails the task goal and keeps outputs inconsistent across surfaces
- First integration proof:
  trend API unit tests plus report statistics unit tests
- Waivers:
  no schema migration unless implementation proves deterministic derivation is insufficient

## Plan (Keep Updated)

1. Preflight (branch, tests, context) - completed
2. Implement - completed
3. Validate - completed
4. Ship (PR, checks, merge, main sync) - in progress

## Decisions (Timestamped)

- 2026-03-26: Use deterministic derived state instead of new stored columns first. (reason: satisfies task requirements with lower migration and drift risk)
- 2026-03-26: Prefer helper extraction over expanding allowlisted route/report modules directly. (reason: repo code-shape policy)
- 2026-03-26: Make snapshot-history gaps fail safe to stable/unknown momentum instead of forcing every API test to seed synthetic snapshots. (reason: production-safe fallback and reduced mock brittleness)

## Risks / Foot-guns

- Momentum can duplicate raw probability if it is only a renamed delta -> bind it to explicit lookback windows and directional classification
- Uncertainty can drift between API and reports if each computes it separately -> centralize in shared helper functions
- Snapshot gaps can make momentum unstable -> degrade safely to neutral/stable semantics when history is insufficient

## Validation Commands

- `pytest tests/unit/api/test_trends.py`
- `pytest tests/unit/api/test_trend_forecast_contracts.py tests/unit/api/test_trends_additional.py tests/unit/api/test_trend_response_state.py tests/unit/api/test_trends.py`
- `pytest tests/unit/core/test_report_generator.py tests/unit/core/test_trend_state_presentation.py`
- `python scripts/check_code_shape.py`
- `make agent-check`

## Notes / Links

- Spec: `tasks/BACKLOG.md`
- Relevant modules:
  `src/core/risk.py`, `src/core/trend_engine.py`,
  `src/api/routes/trends.py`, `src/core/report_generator.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
