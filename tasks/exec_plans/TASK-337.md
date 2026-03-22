# TASK-337: Pin Live Trend State to Active Definition/Scoring Versions

## Status

- Owner: Codex automation
- Started: 2026-03-22
- Current state: In progress
- Planning Gates: Required

## Goal (1-3 lines)

Make the live trend state explicitly versioned so definition/scoring changes do
not silently continue one mixed probability line. Activation must choose a
deliberate state transition path and persisted derived state must carry the
active contract reference used to produce it.

## Inputs

- Spec/backlog references:
  `tasks/CURRENT_SPRINT.md`, `TASK-337` backlog entry from `horadus tasks show/context-pack`
- Runtime/code touchpoints:
  `src/storage/models.py`, `src/storage/restatement_models.py`,
  `src/core/trend_engine.py`, `src/core/trend_restatement.py`,
  `src/core/report_runtime.py`, `src/core/report_generator.py`,
  `src/api/routes/trends.py`, `src/api/routes/trend_api_models.py`,
  `src/api/routes/trend_response_models.py`, `src/workers/_task_maintenance.py`,
  `src/processing/trend_impact_reconciliation.py`, `alembic/`, `tests/`,
  `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`
- Preconditions/dependencies:
  Existing definition-history rows and evidence/restatement provenance columns
  already exist; this task extends those surfaces to version the live state
  itself.

## Outputs

- Expected behavior/artifacts:
  Introduce an append-only live-state version record for each trend, pin the
  active trend row and derived state to that record, and require explicit
  activation mode selection when material definition/scoring changes would
  otherwise continue the current live state implicitly.
- Validation evidence:
  Targeted unit/integration coverage for activation flows and live-state reads,
  plus `make agent-check` and the stronger local gate if the task footprint
  requires it.

## Non-Goals

- Explicitly excluded work:
  Full historical recomputation of every prior evidence row into new scoring
  formulas; the task will version the live state and define safe activation
  semantics, not backfill every historical artifact into every newer contract.

## Scope

- In scope:
  Schema/model changes for active live-state versions and references
  Worker/report/projection wiring so active-state reads use the pinned version
  API changes exposing active definition/scoring metadata and activation paths
  Migration/backfill for existing trends into an initial active state version
  Regression tests and doc updates for the new invariant
- Out of scope:
  New external operator UI
  Multi-trend bulk activation orchestration beyond the existing sync/update
  entry points

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  Add an append-only `TrendStateVersion` lineage table and pin the mutable
  `trends` row to one active state version plus explicit active
  definition/scoring references. New evidence, restatements, snapshots, and
  active-state debug/report reads will carry or filter by that active state
  version so live-state queries do not mix contracts.
- Rejected simpler alternative:
  Adding only response fields on `trends` or only pinning hashes on the mutable
  row does not isolate live-state reads from older evidence/restatement rows and
  would still leave active probability state semantically ambiguous.
- First integration proof:
  Create/backfill one initial state version per existing trend, then validate
  that evidence application and snapshots stamp the same active state version
  and that explicit activation rolls the active pointer forward.
- Waivers:
  Replay mode will use cutoff/freeze semantics instead of immediate full
  historical recomputation: activation creates a new active state line and
  resets its live state safely, rather than mutating the prior line in place.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement schema/model changes and state-version helpers
3. Wire runtime/state consumers and activation workflow
4. Validate
5. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-22: Use an append-only trend state version lineage instead of only
  adding more columns to `trends`, because live-state readers need one shared
  contract handle.
- 2026-03-22: Replay isolation will use cutoff/freeze semantics for the new
  active line rather than attempting a same-transaction historical recompute.
- 2026-03-22: Carry forward narrow code-shape ratchet increases for
  `trends.py`, `trend_engine.py`, `trend_restatement.py`, and
  `storage/models.py` rather than splitting the activation workflow across
  more files mid-task; keep the debt localized and explicit in
  `config/quality/code_shape.toml`.

## Risks / Foot-guns

- Evidence/restatement reads that forget to filter by active state version could
  still blend contracts -> update report/projection/debug helpers alongside the
  write path and cover with regression tests.
- Migration backfill could leave legacy rows without an initial state version ->
  create deterministic initial state rows and backfill references in the
  migration.
- Sync/update behavior could remain silently permissive for material
  definition/baseline changes -> fail closed unless the explicit activation mode
  is supplied for impacted live trends.

## Validation Commands

- `pytest tests/unit/api/test_trends.py tests/unit/api/test_trends_additional.py`
- `pytest tests/unit/core/test_trend_engine.py tests/unit/core/test_report_runtime.py`
- `pytest tests/unit/processing/test_trend_impact_reconciliation.py`
- `pytest tests/integration/test_processing_pipeline.py`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none; backlog/context-pack only
- Relevant modules:
  `src/api/routes/trends.py`
  `src/core/trend_engine.py`
  `src/core/trend_restatement.py`
  `src/core/report_runtime.py`
  `src/processing/trend_impact_reconciliation.py`
  `src/workers/_task_maintenance.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
