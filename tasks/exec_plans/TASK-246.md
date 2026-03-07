# TASK-246: Enrich Tier-2 Signal Payload Beyond Keyword Bags

## Status

- Owner: Codex
- Started: 2026-03-07
- Current state: Done

## Goal (1-3 lines)

Improve Tier-2 signal selection quality by passing short human-readable indicator
descriptions alongside keywords and tightening prompt guidance for specificity and
abstention.

## Scope

- In scope:
  - Add optional indicator descriptions to trend config schema/runtime payloads
  - Enrich Tier-2 prompt with specificity and abstention guidance
  - Add regression coverage for ambiguous signal-family selection
  - Capture benchmark notes for enriched metadata impact
- Out of scope:
  - Broad model changes or reasoning-setting plumbing
  - Gold-set label rewrites

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-07: Model indicator descriptions as optional config fields with a code fallback, so existing configs remain valid while key trends can add sharper wording.
- 2026-03-07: Do not promote a new baseline from this task; the 10-item human-verified benchmark showed no measurable Tier-2 accuracy improvement, while Tier-1 collapse and Tier-2 truncation remain larger blockers.

## Risks / Foot-guns

- Payload bloat can reduce available context budget -> keep descriptions short and preserve existing chunk truncation behavior.
- Description drift across trend configs can hurt consistency -> prefer concise operator-written descriptions for ambiguous signal families first.

## Validation Commands

- `uv run --no-sync pytest tests/unit/processing/test_tier2_classifier.py -v`
- `uv run --no-sync pytest tests/unit/core/test_trend_config_loader.py -v`
- `uv run --no-sync python scripts/check_docs_freshness.py`
- `make agent-check`
- `uv run --no-sync horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --trend-config-dir config/trends --output-dir ai/eval/results --max-items 10 --require-human-verified --config baseline`

## Notes / Links

- Spec: `tasks/BACKLOG.md` (`TASK-246`)
- Relevant modules: `src/core/trend_config.py`, `src/core/trend_config_loader.py`, `src/processing/tier2_classifier.py`
- Validation artifact: `ai/eval/results/benchmark-20260307T151007Z-1f6c9da9.json`
- Benchmark note: metadata enrichment preserved contract clarity but did not improve the sampled Tier-2 accuracy metrics versus the prior 10-item baseline slice.
