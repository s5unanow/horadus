# TASK-209: Restore `canonical_summary` alignment with `primary_item_id` after Tier-2

## Status

- Owner: Codex
- Started: 2026-03-23
- Current state: In progress (implementation and validation complete; shipping in progress)
- Planning Gates: Required — task estimate is 2-4 hours and it materially touches allowlisted `src/processing/tier2_classifier.py`

## Goal (1-3 lines)

Keep `events.canonical_summary` bound to the current `primary_item_id` even after
Tier-2 classification runs, so the stored event identity does not drift from the
most credible linked item.

## Inputs

- Spec/backlog references: `tasks/CURRENT_SPRINT.md`, `TASK-209` backlog/context-pack entry
- Runtime/code touchpoints: `src/processing/tier2_classifier.py`, `src/processing/event_clusterer.py`, `docs/DATA_MODEL.md`, `tests/unit/processing/test_tier2_classifier*.py`
- Preconditions/dependencies: task branch created via `horadus tasks safe-start`; storage/model/docs summary semantics must stay aligned once the split lands

## Outputs

- Expected behavior/artifacts: Tier-2 leaves `canonical_summary` unchanged; docs describe the invariant clearly; regression tests cover Tier-2 plus post-merge event behavior
- Validation evidence: targeted unit tests, `make agent-check`, canonical local gate

## Non-Goals

- Explicitly excluded work: broader extraction schema redesign beyond the summary split required to preserve API/reporting behavior

## Scope

- In scope: preserve canonical-summary semantics, add a persisted event-level summary, align prompt/docs wording, update readers and tests that assumed Tier-2 rewrites the canonical field
- Out of scope: broader extraction schema redesign or reworking deterministic trend mapping strategy

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: split summary semantics into `events.canonical_summary` (primary-item identity) and `events.event_summary` (persisted synthesized event-level summary used for API/reporting/Tier-2 carry-forward)
- Rejected simpler alternative: drop the Tier-2 write entirely and rely only on `canonical_summary`; rejected because it regresses user-facing summaries and loses the carry-forward seed for later reclassification
- First integration proof: a merged event retains the primary-item summary while Tier-2 persists and reuses a separate synthesized event summary
- Waivers: none

## Plan (Keep Updated)

1. Preflight (branch, tests, context) — completed
2. Implement — completed
3. Validate — completed
4. Ship (PR, checks, merge, main sync) — in progress

## Decisions (Timestamped)

- 2026-03-23: Initial preserve-only draft proved too narrow under review because API/report/reporting surfaces and Tier-2 reclassification still needed a persisted event-level summary.
- 2026-03-23: Switched to a split-field design: keep `canonical_summary` tied to `primary_item_id`, persist Tier-2 synthesized text in `event_summary`, and route event-level readers through the new field with canonical fallback.

## Risks / Foot-guns

- Split summary semantics must stay aligned across storage, API, reports, embeddings, and Tier-2 reuse -> cover the main reader paths with targeted tests and the full local gate
- Existing rows and pre-Tier-2 events still need a usable summary -> migration/backfill plus canonical fallback keeps older data readable

## Validation Commands

- `pytest tests/unit/processing/test_tier2_classifier.py tests/unit/processing/test_tier2_classifier_additional.py tests/unit/processing/test_event_clusterer.py`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none
- Relevant modules: `src/processing/tier2_classifier.py`, `src/processing/event_clusterer.py`, `src/processing/trend_impact_mapping.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
