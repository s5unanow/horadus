# TASK-203: Enforce validated, unique runtime trend identifiers across config and API

## Status

- Owner: Codex
- Started: 2026-03-16
- Current state: In progress
- Planning Gates: Required — touches API validation, DB schema, migration safety, and runtime routing semantics

## Goal (1-3 lines)

Make the runtime trend identifier used by Tier-1/Tier-2/pipeline routing explicit,
validated, and unique across every write path. Prevent ambiguous active-taxonomy
state from silently shadowing one trend behind another.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-203`), `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints: `src/core/trend_config.py`, `src/core/trend_config_loader.py`, `src/api/routes/trends.py`, `src/processing/pipeline_orchestrator.py`, `src/processing/tier1_classifier.py`, `src/processing/tier2_classifier.py`, `src/storage/models.py`, `alembic/`
- Preconditions/dependencies: keep config-sync behavior compatible with existing YAML contract; preserve existing trend UUID primary keys and definition-version audit trail

## Outputs

- Expected behavior/artifacts:
  - shared validation path for config-sync and API create/update trend payloads
  - persisted normalized runtime trend identifier with uniqueness enforcement
  - migration that fails on existing duplicate runtime identifiers before adding the constraint
  - orchestration guard that rejects duplicate active runtime identifiers instead of shadowing
- Validation evidence:
  - focused unit tests for config/API validation parity
  - focused unit tests for duplicate-active-runtime-id rejection in orchestration
  - migration-level or model-level tests for uniqueness enforcement as covered by repo test surfaces

## Non-Goals

- Redesigning trend UUID primary keys or downstream evidence foreign keys
- Changing Tier-2 taxonomy semantics beyond runtime identifier validation/lookup
- Solving adjacent trend-config sync authorization issues tracked elsewhere

## Scope

- In scope:
  - centralize runtime trend payload validation around the same schema contract
  - add a dedicated normalized runtime identifier column on `trends`
  - enforce uniqueness and duplicate detection during migration and runtime loads
  - update API write paths and config sync to populate the normalized identifier
- Out of scope:
  - large refactors of Tier-1/Tier-2 payload builders
  - taxonomy-gap redesign

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: add one dedicated `runtime_trend_id` column instead of repeatedly extracting and normalizing `definition["id"]` from JSON at every call site
- Rejected simpler alternative: relying only on app-level duplicate checks would still leave race windows and existing-row ambiguity; DB enforcement is required
- First integration proof: create/update + config-sync both flow through one validation helper and pipeline startup rejects duplicate active ids before classification/apply paths run
- Waivers: no separate task spec; the exec plan is the authoritative planning artifact for this task

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement shared validation + schema changes
3. Validate tests and local gates
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-16: Use a dedicated `runtime_trend_id` column as the unique routing key while preserving `definition.id` in JSON for audit/export compatibility.
- 2026-03-16: Fail migration on pre-existing duplicates instead of auto-rewriting IDs, because silent rewrite would break existing taxonomy references and auditability.
- 2026-03-16: Fail pipeline closed when active trends contain duplicate runtime ids, even though the DB constraint should prevent new duplicates, to guard legacy/bad state during rollout.

## Risks / Foot-guns

- Existing rows may have blank or duplicate `definition.id` values -> migration must surface concrete duplicates before adding NOT NULL/UNIQUE constraints
- API update path currently accepts partial unvalidated dictionaries -> shared validation helper must preserve partial update semantics without allowing schema drift
- Config-sync currently upserts by name -> runtime-id uniqueness checks must not accidentally allow two names to share one routing id

## Validation Commands

- `uv run --no-sync horadus tasks preflight`
- `uv run --no-sync horadus tasks safe-start TASK-203 --name runtime-trend-ids`
- `pytest tests/unit/api/test_trends.py tests/unit/api/test_trends_additional.py tests/unit/core/test_trend_config_loader.py tests/unit/processing/test_pipeline_orchestrator.py tests/unit/processing/test_pipeline_orchestrator_additional.py`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Relevant modules: `src/core/trend_config_loader.py`, `src/processing/tier1_classifier.py`, `src/processing/tier2_classifier.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
