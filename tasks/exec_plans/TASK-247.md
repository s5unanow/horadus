# TASK-247: Evaluate GPT-5 Reasoning Models for Tier-1/Tier-2

## Status

- Owner: Codex
- Started: 2026-03-07
- Current state: Done

## Goal (1-3 lines)

Run a controlled benchmark comparison between the current `gpt-4.1-*` baseline
and GPT-5 candidate stage swaps, then document whether the switch is justified
and whether Responses API migration is required for this repo.

## Scope

- In scope:
  - Benchmark-local GPT-5 candidate configs and stage-specific reasoning overrides
  - Cost/latency/quality comparison on a shared human-verified gold-set slice
  - Recommendation and rollback criteria in docs/task notes
- Out of scope:
  - Runtime reasoning-effort env/config plumbing (`TASK-249`)
  - Final production model switch

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-07: Use Chat Completions for GPT-5 evaluation because current OpenAI docs show GPT-5 supports `reasoning_effort` and `response_format` there, while repo Responses-mode strict-JSON parity remains incomplete.
- 2026-03-07: Treat benchmark cost figures for failure-heavy configs as lower bounds, because current classifier benchmark accounting only captures successful call usage after parse/alignment succeeds.
- 2026-03-07: Recommended target rollout after runtime reasoning-effort plumbing lands: Tier 1 `gpt-5-nano` with `minimal`, Tier 2 `gpt-5-mini` with `low`.

## Risks / Foot-guns

- GPT-5 pricing must be current or cost comparisons are misleading -> update pricing tables from official OpenAI pricing before benchmarking.
- Benchmark-local override support can drift from runtime controls -> keep this scoped to eval and defer runtime plumbing to `TASK-249`.

## Validation Commands

- `uv run --no-sync pytest tests/unit/eval/test_benchmark.py -v`
- `uv run --no-sync ruff check src/eval/benchmark.py src/core/config.py src/processing/llm_pricing.py tests/unit/eval/test_benchmark.py`
- `uv run --no-sync ruff format --check src/eval/benchmark.py src/core/config.py src/processing/llm_pricing.py tests/unit/eval/test_benchmark.py`
- `uv run --no-sync python scripts/check_docs_freshness.py`
- `make agent-check`
- `uv run --no-sync horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --trend-config-dir config/trends --output-dir ai/eval/results --max-items 10 --require-human-verified --config baseline --config tier1-gpt5-nano-minimal --config tier1-gpt5-nano-low --config tier2-gpt5-mini-low --config tier2-gpt5-mini-medium`

## Notes / Links

- Spec: `tasks/BACKLOG.md` (`TASK-247`)
- Relevant modules: `src/eval/benchmark.py`, `src/processing/llm_invocation_adapter.py`, `src/processing/llm_policy.py`
- Validation artifact: `ai/eval/results/benchmark-20260307T155840Z-a166f992.json`
- Key result summary:
  - Tier 1: `gpt-5-nano` `minimal` beat baseline and `low` on the sampled slice.
  - Tier 2: `gpt-5-mini` `low` beat baseline and `medium` on the sampled slice.
  - Responses API migration is not required for GPT-5 evaluation in this repo because Chat Completions already covers structured outputs + `reasoning_effort`.
