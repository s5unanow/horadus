# TASK-229: Add a Novelty Lane Outside the Active Trend List

## Status

- Owner: Codex
- Started: 2026-03-25
- Current state: In progress
- Planning Gates: Required — task materially touches allowlisted Python hotspots and spans storage, processing, API, tests, and migration surfaces

## Goal (1-3 lines)

Persist a bounded novelty lane for items/events that do not cleanly map to active trends,
rank those candidates with deterministic heuristics, and expose them to operators without
changing the normal trend-scoring path or adding extra LLM cost.

## Inputs

- Spec/backlog references:
  - `tasks/CURRENT_SPRINT.md`
  - `TASK-229` backlog entry via `horadus tasks context-pack TASK-229`
- Runtime/code touchpoints:
  - `src/processing/pipeline_orchestrator.py`
  - `src/processing/tier1_classifier.py`
  - `src/api/routes/feedback.py`
  - `src/api/routes/feedback_models.py`
  - `src/storage/models.py`
  - `alembic/versions/`
  - `tests/unit/processing/`
  - `tests/unit/api/`
  - `tests/integration/`
- Preconditions/dependencies:
  - Keep novelty capture deterministic and budget-safe
  - Do not apply novelty-derived trend deltas
  - Avoid growing hotspot modules more than needed; prefer extraction into ownership-local helpers

## Outputs

- Expected behavior/artifacts:
  - novelty persistence table + migration
  - deterministic novelty capture service for near-threshold Tier-1 misses and unmapped/low-signal events
  - operator novelty queue endpoint
  - regression coverage for persistence, ranking, and API response shape
- Validation evidence:
  - targeted unit tests for novelty capture and API sorting/filtering
  - targeted integration proof for persistence through pipeline/API
  - `make agent-check`
  - `make test-integration-docker`
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Explicitly excluded work:
  - adding new LLM stages or prompts
  - auto-promoting novelty candidates into trends
  - changing the existing review-queue scoring semantics for trend-backed events

## Scope

- In scope:
  - new novelty candidate persistence surface
  - deterministic candidate upsert/ranking from existing Tier-1/Tier-2 outputs
  - operator-facing novelty queue endpoint
  - docs updates for data model / operator-facing API additions
- Out of scope:
  - broad event list redesign
  - human adjudication workflow expansion beyond read-only novelty surfacing

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - capture novelty only from existing pipeline signals and bounded deterministic heuristics
- Rejected simpler alternative:
  - ephemeral in-memory novelty ranking; rejected because the task requires persistence and recurrence tracking across runs
- First integration proof:
  - end-to-end pipeline test that leaves novelty surfaced without trend evidence updates
- Waivers:
  - none currently

## Plan (Keep Updated)

1. Preflight (branch, tests, context) — completed
2. Implement — in progress
3. Validate — pending
4. Ship (PR, checks, merge, main sync) — pending

## Decisions (Timestamped)

- 2026-03-25: Use a separate novelty persistence/service surface and keep existing large route/model files as thin wiring only. (Reduces hotspot growth.)
- 2026-03-25: Novelty capture remains deterministic and bounded, reusing Tier-1/Tier-2 outputs instead of adding any extra LLM calls. (Meets budget-safety requirement.)

## Risks / Foot-guns

- Near-threshold item grouping can over-collapse unrelated items -> use explicit deterministic cluster keys and keep raw signal details on the candidate row.
- Novelty lane can leak into normal scoring semantics -> ensure capture is side-effect-only and only runs on no-delta / low-signal branches.
- API queue can become noisy -> cap ranking inputs, default to open candidates only, and bound result count.

## Validation Commands

- `uv run --no-sync pytest tests/unit/processing/test_novelty_lane.py -v -m unit`
- `uv run --no-sync pytest tests/unit/api/test_feedback.py -v -m unit`
- `uv run --no-sync pytest tests/integration/test_processing_pipeline.py -v`
- `make agent-check`
- `make test-integration-docker`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none; using backlog entry + context pack
- Relevant modules:
  - `src/processing/pipeline_orchestrator.py`
  - `src/api/routes/feedback.py`
  - `src/storage/models.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
