# TASK-228: Harden Trend Forecast Contracts with Explicit Horizon and Resolution Semantics

## Status

- Owner: Codex
- Started: 2026-03-17
- Current state: In progress
- Planning Gates: Required — task changes trend config semantics, API contracts, validation behavior, docs, and regression coverage across multiple files

## Goal (1-3 lines)

Make every active trend probability explicitly answerable by adding a
forecast-contract model with a clear question, horizon, resolver basis, and
closure semantics that deterministic validation can enforce.

## Inputs

- Spec/backlog references:
  - `tasks/CURRENT_SPRINT.md`
  - `tasks/BACKLOG.md` (`TASK-228`)
- Runtime/code touchpoints:
  - `src/core/trend_config.py`
  - `src/api/routes/trends.py`
  - `config/trends/`
  - `tests/`
  - `docs/`
- Preconditions/dependencies:
  - Preserve existing trend IDs and active trend sync behavior
  - Keep config and API validation aligned so operator writes fail closed
  - Avoid breaking existing consumers beyond additive response fields and tighter validation

## Outputs

- Expected behavior/artifacts:
  - Explicit forecast-contract schema in trend definitions and API write payloads
  - Deterministic validation for missing/inconsistent horizon, resolver basis, and closure semantics
  - Forecast-contract metadata surfaced in trend API responses
  - Existing trend YAMLs backfilled with the new contract fields without changing IDs
  - Docs and regression tests covering valid and invalid contract cases
- Validation evidence:
  - Focused unit/API tests for config parsing and trend write/read validation
  - `make agent-check`
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Redesigning trend scoring math or probability update rules
- Introducing new trend lifecycle storage beyond contract metadata needed for validation and read surfaces
- Building analyst tooling beyond the existing API/config surfaces

## Scope

- In scope:
  - Define the forecast-contract schema and consistency rules
  - Extend config sync and trend API validation to require that contract
  - Surface the contract in trend API responses
  - Backfill existing YAML definitions and document migration guidance
  - Add regression coverage for missing-horizon, ambiguous-resolution, and valid cases
- Out of scope:
  - Historical backfill or reinterpretation of already-stored trend snapshots
  - Broader changes to event/trend evidence semantics outside the forecast contract

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Treat forecast contract as an explicit nested metadata object on the trend definition/API surface rather than as free-form description prose.
  - Require operator-readable question text, forecast horizon, measurable resolution basis, resolver source/basis, and closure rule for active trends.
  - Validate internal consistency in one shared ruleset so config sync and API writes cannot diverge.
- Rejected simpler alternative:
  - Adding only optional prose fields would keep the forecast object ambiguous and fail the task’s “semantically honest probability” goal.
- First integration proof:
  - A trend definition without horizon or with ambiguous resolver/closure semantics is rejected consistently in both config parsing and API writes, while a valid contract round-trips through the trend API.
- Waivers:
  - None currently; extract helper types if existing modules approach shape limits.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-17: Use a shared nested forecast-contract model across config parsing and API schemas so validation rules are defined once and surfaced consistently.
- 2026-03-17: Keep the initial contract additive in stored definition payloads and API reads while failing closed on future writes/syncs that omit required fields.

## Risks / Foot-guns

- Divergent config-vs-API validation rules -> centralize the contract model and test both entry points.
- Existing YAMLs missing required fields -> backfill all tracked trend configs in the same task before enabling strict validation.
- Route/model sprawl in already busy trend modules -> extract small shared helpers/types instead of inlining more schema logic.

## Validation Commands

- `pytest tests/unit/core/test_trend_config.py`
- `pytest tests/unit/api/test_trends.py`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: backlog-only task; this exec plan is the authoritative planning artifact
- Relevant modules:
  - `src/core/trend_config.py`
  - `src/api/routes/trends.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
