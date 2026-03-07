# TASK-244: Persist Per-Item Benchmark Failure Diagnostics

## Status

- Owner: Codex
- Started: 2026-03-07
- Current state: Done

## Goal (1-3 lines)

Make benchmark artifacts directly useful for debugging by persisting per-item
Tier-1 and Tier-2 stage outcomes, not just aggregate metrics.

## Scope

- In scope:
  - Per-item benchmark artifact diagnostics
  - Failure capture for exception and missing-prediction paths
  - Raw response capture where the benchmark can observe it
  - Unit coverage and policy-doc updates for the artifact contract
- Out of scope:
  - Eval artifact git provenance and promotion workflow
  - Tier-1/Tier-2 prompt redesign
  - GPT-5 evaluation work

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Add per-item item-results artifact contract and response capture wrappers
3. Validate with unit, docs-freshness, agent, integration, and one live benchmark run
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-07: Keep per-item diagnostics local to benchmark artifacts instead of changing runtime classifier return types.

## Risks / Foot-guns

- Raw model output is only available when benchmark instrumentation can observe a response -> record it on a best-effort basis and omit when unavailable.
- Batch-mode Tier-1 failures can affect multiple items per call -> copy the same batch failure payload to each impacted item result so the artifact remains item-centric.

## Validation Commands

- `uv run --no-sync pytest tests/unit/eval/test_benchmark.py -v`
- `uv run --no-sync python scripts/check_docs_freshness.py`
- `make agent-check`
- `make test-integration-docker`
- `uv run --no-sync horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --trend-config-dir config/trends --output-dir ai/eval/results --max-items 5 --require-human-verified --config baseline`

## Notes / Links

- Spec: none
- Relevant modules: `src/eval/benchmark.py`, `tests/unit/eval/test_benchmark.py`
- Validation artifact: `ai/eval/results/benchmark-20260307T142121Z-28c26148.json`
