# TASK-233: Support Multi-Horizon Trend Variants for the Same Underlying Theme

## Status

- Owner: Codex
- Started: 2026-03-26
- Current state: In progress
- Planning Gates: Required — task spans multiple Python surfaces, API/report contracts, and targeted validation

## Goal (1-3 lines)

Allow multiple trend records to explicitly represent different forecast horizons for the same
underlying theme while keeping the live probability math isolated per trend record. Expose
that horizon/theme metadata clearly in trend APIs and reporting outputs without breaking
existing single-horizon definitions.

## Inputs

- Spec/backlog references: `tasks/CURRENT_SPRINT.md`, `tasks/BACKLOG.md`
- Runtime/code touchpoints: `src/core/trend_config.py`, `src/core/trend_config_loader.py`, `src/api/routes/_trend_write_contract.py`, `src/api/routes/_trend_write_mutations.py`, `src/api/routes/trend_api_models.py`, `src/api/routes/trends.py`, `src/core/calibration_dashboard.py`, `src/api/routes/reports.py`, `src/core/report_runtime.py`, targeted tests
- Preconditions/dependencies: guarded task branch already started via `horadus tasks safe-start TASK-233 --name multi-horizon-trend-variants`

## Outputs

- Expected behavior/artifacts:
  - trend definitions can optionally encode a stable theme key plus explicit horizon-variant metadata
  - trend create/update/config-sync paths preserve and validate that metadata
  - trend list/detail and reporting/calibration outputs surface the metadata
  - existing single-horizon trends remain valid without new required fields
- Validation evidence:
  - targeted unit coverage for config/write-path normalization and API/report responses
  - `make agent-check`

## Non-Goals

- Explicitly excluded work:
  - changing log-odds scoring math
  - changing event-to-trend impact routing semantics
  - bulk-retrofitting the existing trend catalog to add horizon variants
  - solving the separate `horadus tasks context-pack TASK-233` archived/live ledger inconsistency

## Scope

- In scope:
  - definition schema extension for multi-horizon variant metadata
  - helper normalization/read APIs for that metadata
  - trend response/report response exposure
  - regression tests for backward compatibility and grouped horizon metadata
- Out of scope:
  - new database columns or migration unless definition-backed metadata proves insufficient
  - broader sprint pairing work for `TASK-234`

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: keep horizon/theme metadata in the versioned `definition` payload and derive outward API/report fields from it
- Rejected simpler alternative: rely only on free-form forecast-contract horizon text, because it does not create an explicit stable relationship between multiple records for the same underlying theme
- First integration proof: targeted unit tests across write path and report outputs
- Waivers: no schema migration planned unless implementation reveals a hard querying/persistence gap

## Plan (Keep Updated)

1. Preflight (branch, tests, context) — done
2. Implement — done
3. Validate — done
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-26: Use definition-backed metadata instead of new DB columns to avoid expanding the repo’s allowlisted oversized storage model while still keeping trend lineage/versioning accurate. (reason: smallest safe change that satisfies the task acceptance criteria)
- 2026-03-26: Treat the `context-pack` archived response as a secondary ledger inconsistency and continue from live sprint/backlog state. (reason: eligibility and safe-start succeeded, and the live backlog entry remains authoritative enough for implementation)

## Risks / Foot-guns

- API/report consumers may expect the old trend shape only -> add new fields as optional/backward-compatible extensions
- Variant metadata could drift between create/update/sync paths -> centralize normalization in shared trend-config helpers
- Reporting surfaces could expose incomplete metadata for legacy rows -> derive `None`/empty fields cleanly when variants are absent

## Validation Commands

- `pytest tests/unit/core/test_trend_config_loader.py tests/unit/api/test_trend_write_contract.py tests/unit/api/test_trends.py tests/unit/api/test_reports.py tests/unit/core/test_report_runtime.py tests/unit/core/test_calibration_dashboard.py`
- `make agent-check`

## Notes / Links

- Spec: `tasks/BACKLOG.md`
- Relevant modules: see Inputs
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
