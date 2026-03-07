# TASK-245: Add Explicit Tier-1 Scoring Rubric and Calibration Examples

## Status

- Owner: Codex
- Started: 2026-03-07
- Current state: Done

## Goal (1-3 lines)

Reduce Tier-1 scoring ambiguity by giving the prompt explicit score bands around
the runtime threshold and targeted examples for known false positives.

## Scope

- In scope:
  - Tier-1 prompt scoring rubric
  - Targeted calibration examples for current-event positives and media/history negatives
  - Prompt regression coverage
  - A fresh gold-set benchmark run before any promotion decision
- Out of scope:
  - Tier-2 prompt changes
  - Benchmark artifact shape changes
  - Model migration work

## Plan (Keep Updated)

1. Preflight (branch, context, current prompt)
2. Add score bands and targeted examples to the Tier-1 prompt
3. Add prompt regression tests and run a fresh benchmark
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-07: Keep examples compact and pattern-based instead of embedding long few-shot exemplars.
- 2026-03-07: Treat the fresh benchmark run as a promotion gate, not as proof that the rubric alone solved Tier-1 quality.

## Risks / Foot-guns

- Overfitting to a handful of examples could hurt generalization -> use broad negative classes (documentary, fiction, commentary) rather than specific memorized titles.
- Prompt improvements may still not materially improve quality on current models -> benchmark before any promotion claim.

## Validation Commands

- `uv run --no-sync pytest tests/unit/processing/test_tier1_prompt_contract.py tests/unit/processing/test_tier1_classifier.py -v`
- `uv run --no-sync python scripts/check_docs_freshness.py`
- `make agent-check`
- `make test-integration-docker`
- `uv run --no-sync horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --trend-config-dir config/trends --output-dir ai/eval/results --max-items 10 --require-human-verified --config baseline`

## Notes / Links

- Spec: none
- Relevant modules: `ai/prompts/tier1_filter.md`, `tests/unit/processing/test_tier1_prompt_contract.py`
- Validation artifact: `ai/eval/results/benchmark-20260307T145523Z-9efc6fd2.json` (evaluated before promotion; no baseline promotion)
