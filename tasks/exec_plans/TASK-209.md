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
- Preconditions/dependencies: task branch created via `horadus tasks safe-start`; no schema change needed for the smallest safe fix

## Outputs

- Expected behavior/artifacts: Tier-2 leaves `canonical_summary` unchanged; docs describe the invariant clearly; regression tests cover Tier-2 plus post-merge event behavior
- Validation evidence: targeted unit tests, `make agent-check`, canonical local gate

## Non-Goals

- Explicitly excluded work: adding a new persisted event-summary column, changing DB schema, or redesigning the Tier-2 response schema beyond wording/docs cleanup

## Scope

- In scope: preserve canonical-summary semantics, align prompt/docs wording, update tests that assumed Tier-2 rewrites the field
- Out of scope: broader extraction schema redesign or reworking deterministic trend mapping strategy

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: Tier-2 may still emit a synthesized `summary`, but runtime treats it as transient extraction output and does not persist it into `events.canonical_summary`
- Rejected simpler alternative: keep overwriting `canonical_summary` and only soften docs; rejected because it preserves the semantic drift the task exists to remove
- First integration proof: a merged event retains the primary-item summary before and after Tier-2 classification
- Waivers: none

## Plan (Keep Updated)

1. Preflight (branch, tests, context) — completed
2. Implement — completed
3. Validate — completed
4. Ship (PR, checks, merge, main sync) — in progress

## Decisions (Timestamped)

- 2026-03-23: Chose preservation over field-split for this task because the documented invariant is already clear, cluster/provenance code already enforces it, and the smallest safe fix is to stop Tier-2 from violating that invariant.

## Risks / Foot-guns

- Trend-impact mapping still reads `canonical_summary` as fallback context -> cover with targeted Tier-2 tests to ensure extracted fields continue to drive mappings correctly
- Test expectations currently encode the old overwrite behavior -> update them alongside the runtime change to avoid false regressions

## Validation Commands

- `pytest tests/unit/processing/test_tier2_classifier.py tests/unit/processing/test_tier2_classifier_additional.py tests/unit/processing/test_event_clusterer.py`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none
- Relevant modules: `src/processing/tier2_classifier.py`, `src/processing/event_clusterer.py`, `src/processing/trend_impact_mapping.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
