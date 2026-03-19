# TASK-335: Move Trend-Impact Mapping Fully Into Deterministic Code

## Status

- Owner: Codex automation
- Started: 2026-03-19
- Current state: In progress
- Planning Gates: Required — task changes allowlisted Python hotspots and the Tier-2 business-semantics boundary

## Goal (1-3 lines)

Move Tier-2 from direct trend/action selection to extracted-facts-only output.
Deterministic code must map extracted claims/entities/location context onto
eligible trend indicators, emit explicit ambiguous/no-match diagnostics, and
keep downstream evidence scoring stable when structured extraction is unchanged.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` → `TASK-335`
  - `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints:
  - `src/processing/tier2_classifier.py`
  - `src/processing/pipeline_orchestrator.py`
  - `src/processing/trend_impact_reconciliation.py`
  - `src/core/trend_config.py`
  - `src/storage/models.py`
  - `ai/prompts/tier2_classify.md`
  - `src/eval/benchmark.py`
  - `src/processing/tier2_canary.py`
  - `tests/unit/processing/`
  - `tests/unit/eval/`
- Preconditions/dependencies:
  - `src/processing/pipeline_orchestrator.py`, `src/processing/tier2_classifier.py`,
    and `src/storage/models.py` are code-shape allowlisted hotspots.
  - Downstream consumers still expect `event.extracted_claims["trend_impacts"]`
    as the authoritative runtime contract after Tier-2 classification.

## Outputs

- Expected behavior/artifacts:
  - New deterministic trend-impact mapping layer that derives runtime
    `trend_impacts` from extracted claims/entities/location context and active
    trend config, not from first-class LLM-selected `trend_id`/`signal_type`.
  - Explicit ambiguous/no-match diagnostics preserved on the event payload and
    recorded into taxonomy-gap storage for operator review/debug visibility.
  - Tier-2 prompt/runtime contract updated to extracted facts only.
  - Benchmark/canary/test surfaces updated to the new contract.
- Validation evidence:
  - Targeted unit tests for deterministic mapped, ambiguous, and unmapped cases.
  - Prompt-contract and classifier regression tests covering at least two
    prompt/model variants with identical structured extraction.
  - `make agent-check`

## Non-Goals

- Explicitly excluded work:
  - Reworking the trend scoring formula itself.
  - Replacing event-claim identity or evidence reconciliation lineage.
  - Broad taxonomy-authoring changes outside the minimal metadata needed for
    deterministic mapping.

## Scope

- In scope:
  - Extract mapping logic out of Tier-2 outputs into deterministic code.
  - Persist/propagate debug-friendly mapping outcomes.
  - Update prompt/docs/tests/eval/canary consumers to the new contract.
- Out of scope:
  - Replay/versioning tasks covered by `TASK-337` and `TASK-339`.
  - UI/operator workflow redesign beyond docs/debug payloads.

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Keep the downstream `trend_impacts` payload shape stable, but generate it
    after Tier-2 extraction via a deterministic mapper keyed off extracted
    claims plus trend config metadata.
- Rejected simpler alternative:
  - Keeping Tier-2 responsible for `trend_id`/`signal_type` and merely
    validating or post-filtering those outputs would still let prompt/model
    changes alter business semantics without a code change.
- First integration proof:
  - Tier-2 classifier produces mapped impacts and unresolved mapping diagnostics
    from the same extracted-facts payload; pipeline reconciliation and benchmark
    consumers continue reading the same authoritative `trend_impacts` field.
- Waivers:
  - None planned.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Add deterministic mapping module and migrate Tier-2 output contract
3. Wire ambiguous/no-match diagnostics into taxonomy-gap capture and debug paths
4. Update prompt/docs/tests/eval/canary consumers
5. Validate with targeted tests + `make agent-check`
6. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-19: Keep `event.extracted_claims["trend_impacts"]` as the downstream
  authoritative contract so reconciliation, canary, and benchmark consumers do
  not need a second runtime payload shape.
- 2026-03-19: Carry unresolved mapping outcomes separately from mapped impacts
  so ambiguous/no-match cases remain visible without applying unsafe deltas.

## Risks / Foot-guns

- Overly loose deterministic matching could create false positives
  -> require explicit signal-support thresholds and ambiguity handling.
- Overly strict matching could collapse recall
  -> preserve no-match diagnostics and taxonomy-gap visibility instead of silent drops.
- Contract drift across benchmark/canary/tests
  -> update those consumers in the same task and regression-test both success and failure paths.
- Allowlisted hotspot growth
  -> extract new logic into a focused helper module and keep touched hotspot deltas flat or smaller.

## Validation Commands

- `pytest tests/unit/processing/test_tier2_classifier.py`
- `pytest tests/unit/processing/test_trend_impact_reconciliation.py`
- `pytest tests/unit/processing/test_pipeline_orchestrator.py`
- `pytest tests/unit/processing/test_pipeline_orchestrator_additional.py`
- `pytest tests/unit/processing/test_tier2_prompt_contract.py`
- `pytest tests/unit/eval/test_benchmark.py`
- `pytest tests/unit/processing/test_tier2_canary.py`
- `make agent-check`

## Notes / Links

- Spec: backlog-only task; no separate spec exists yet
- Relevant modules:
  - `src/processing/tier2_classifier.py`
  - `src/processing/trend_impact_reconciliation.py`
  - `src/processing/pipeline_orchestrator.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
