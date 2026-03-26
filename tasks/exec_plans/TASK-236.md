# TASK-236: Add Canonical Entity Registry for Actors, Organizations, and Locations

## Status

- Owner: Codex automation
- Started: 2026-03-26
- Current state: Validation complete; ready for finish workflow
- Planning Gates: Required - migration scope, multiple runtime surfaces, and material edits to allowlisted `src/storage/models.py`

## Goal (1-3 lines)

Add a bounded canonical-entity registry with alias support so event extraction
can attach actor/location references to durable entities, expose those
references in event detail payloads, and stay fail-safe when resolution is
ambiguous or incomplete.

## Inputs

- Spec/backlog references:
  - `tasks/CURRENT_SPRINT.md`
  - `tasks/BACKLOG.md` (`TASK-236`)
- Runtime/code touchpoints:
  - `src/storage/models.py`
  - `src/storage/entity_models.py`
  - `src/processing/tier2_classifier.py`
  - `src/processing/tier2_runtime.py`
  - `src/processing/entity_registry.py`
  - `src/api/routes/events.py`
  - `ai/prompts/tier2_classify.md`
  - `alembic/versions/`
  - `tests/unit/storage/`
  - `tests/unit/processing/`
  - `tests/unit/api/`
  - `tests/integration/`
- Preconditions/dependencies:
  - Reuse the existing Tier-2 extraction flow as the source of structured entity mentions
  - Keep `src/storage/models.py` to registration-only deltas when possible because it is at the code-shape ratchet

## Outputs

- Expected behavior/artifacts:
  - Canonical entity tables with alias and event-link records
  - Deterministic entity normalization/resolution that resolves exact unique aliases, leaves ambiguous matches unresolved, and can seed new canonical rows when no existing match exists
  - Event detail payloads that expose canonical entity references and unresolved mention metadata
  - Tier-2 prompt/runtime contract updates needed to emit typed entity mentions safely
- Validation evidence:
  - Focused unit coverage for normalization, alias resolution, ambiguous/unresolved cases, and API payload shape
  - Integration proof for Tier-2 persistence and event-detail exposure
  - `make agent-check`
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Explicitly excluded work:
  - Cross-event entity deduplication beyond exact normalized alias matching
  - Fuzzy multilingual transliteration or embedding-based entity matching
  - New operator CRUD endpoints for manual entity curation

## Scope

- In scope:
  - Schema for canonical entities, aliases, and event-entity links
  - Bounded entity normalization and resolution helpers
  - Tier-2 extraction contract changes needed to capture entity type/role
  - Event detail payload updates plus regression coverage
- Out of scope:
  - Broad clustering redesign around entity graphs
  - Full analyst review workflow for resolving ambiguous entities

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Use exact normalized alias matching with explicit ambiguous/unresolved states instead of fuzzy scoring
  - Keep new ORM ownership in dedicated storage modules and import them through `src/storage/models.py`
- Rejected simpler alternative:
  - Reusing only `extracted_who` / `extracted_where` strings without durable entity rows would not satisfy the canonical-registry or alias-resolution contract
- First integration proof:
  - 2026-03-26: `make test-integration-docker`
- Waivers:
  - None

## Plan (Keep Updated)

1. Preflight (branch, context, exec plan, schema/runtime inventory) - completed
2. Implement canonical entity storage + deterministic resolver + Tier-2 persistence hook - completed
3. Expose event entities in API responses and cover alias/ambiguous/mixed-language paths - completed
4. Validate with targeted tests, `make agent-check`, local gate, and ship through `horadus tasks finish` - in progress

## Decisions (Timestamped)

- 2026-03-26: Treat the `context-pack` archived warning as a retrieval mismatch and continue after the documented `--include-archive` recovery path returned the active backlog/sprint contract.
- 2026-03-26: Prefer exact normalized alias matching with explicit unresolved/ambiguous outcomes to keep multilingual handling bounded and explainable.

## Risks / Foot-guns

- Ambiguous aliases could silently attach the wrong entity -> preserve an explicit unresolved/ambiguous state instead of auto-picking.
- `src/storage/models.py` is already at the ratchet -> keep new table ownership in `src/storage/entity_models.py` and touch `models.py` only for registration imports.
- Tier-2 contract drift could break cached or fake responses -> update prompt/runtime tests together with response-model changes.

## Validation Commands

- `pytest tests/unit/storage/test_model_metadata.py tests/unit/storage/test_entity_models.py -v`
- `pytest tests/unit/processing/test_entity_registry.py tests/unit/processing/test_tier2_classifier.py -v`
- `pytest tests/unit/api/test_events.py tests/integration/test_processing_pipeline.py tests/integration/test_events_api.py -v`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none; backlog entry in `tasks/BACKLOG.md`
- Relevant modules:
  - `src/storage/models.py`
  - `src/storage/entity_models.py`
  - `src/processing/entity_registry.py`
  - `src/processing/tier2_classifier.py`
  - `src/api/routes/events.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
