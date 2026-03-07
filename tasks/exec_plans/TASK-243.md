# TASK-243: Stabilize Tier-1 Routing Quality Under Eval and Runtime Load

## Status

- Owner: Codex
- Started: 2026-03-07
- Current state: Done

## Goal (1-3 lines)

Keep Tier-1 routing on a safe default request shape after the gold-set eval
showed materially worse quality when multiple items were scored in one call.

## Scope

- In scope:
  - Runtime Tier-1 default batching policy
  - Benchmark Tier-1 dispatch policy metadata and operator guidance
  - Regression coverage for the chosen safe-default policy
  - Reproduction notes for realtime vs batched evaluation behavior
- Out of scope:
  - Tier-1 prompt rubric changes
  - Tier-2 signal-conditioning changes
  - GPT-5 model migration work

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement safe-default Tier-1 batching policy
3. Validate with unit, docs-freshness, agent, and integration gates
4. Reproduce eval delta, then ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-07: Treat multi-item Tier-1 requests as diagnostic-only until a future benchmark demonstrates they are quality-safe again.
- 2026-03-07: Keep benchmark `dispatch_mode=batch` available for comparison, but mark it explicitly as `diagnostic_multi_item_batch` in artifacts so operators do not confuse it with the accepted safe default.
- 2026-03-07: Fresh paired 10-item human-verified runs still show batch mode underperforming realtime on Tier-1 failures (`10/10` batch vs `9/10` realtime), even though overall Tier-1 quality remains unacceptable in both modes.

## Risks / Foot-guns

- Lowering runtime batching increases Tier-1 API call volume -> keep benchmark batch mode available for future re-evaluation instead of deleting it.
- Docs-freshness cross-ledger rules are strict -> keep new task IDs confined to active sections and avoid accidental completed-task mentions.

## Validation Commands

- `uv run --no-sync pytest tests/unit/processing/test_tier1_classifier.py tests/unit/eval/test_benchmark.py -v`
- `uv run --no-sync python scripts/check_docs_freshness.py`
- `make agent-check`
- `make test-integration-docker`
- `uv run --no-sync horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --trend-config-dir config/trends --output-dir ai/eval/results --max-items 10 --require-human-verified --config baseline --dispatch-mode realtime`
- `uv run --no-sync horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --trend-config-dir config/trends --output-dir ai/eval/results --max-items 10 --require-human-verified --config baseline --dispatch-mode batch`

## Notes / Links

- Spec: none
- Relevant modules: `src/processing/tier1_classifier.py`, `src/eval/benchmark.py`, `src/core/config.py`
- Paired benchmark artifacts:
  - `ai/eval/results/benchmark-20260307T095858Z-3f80a8aa.json` (`dispatch_mode=realtime`, `tier1_batch_size=1`, Tier-1 failures `9/10`)
  - `ai/eval/results/benchmark-20260307T095843Z-21ec6c32.json` (`dispatch_mode=batch`, `tier1_batch_size=10`, Tier-1 failures `10/10`)
