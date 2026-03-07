# TASK-242: Unblock Gold-Set Benchmark and Capture Quality Blockers

## Status

- Owner: Codex
- Started: 2026-03-06
- Current state: Done

## Goal (1-3 lines)

Restore a runnable, current benchmark path for Tier-1/Tier-2 prompt/model
evaluation against the gold set, then capture the concrete blockers preventing
prompt/model promotion.

## Scope

- In scope:
  - Benchmark harness fixes needed to run against the current gold set
  - Alignment of benchmark defaults with accepted runtime model defaults
  - Prompt-eval documentation updates
  - Gold-set benchmark artifact generation
  - Backlog/sprint capture for the blocking follow-up work
- Out of scope:
  - Gold-set content relabeling
  - New trend taxonomy additions
  - Report/retrospective prompt redesign beyond direct eval prerequisites

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement benchmark and documentation changes
3. Validate with targeted tests and eval commands
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-06: Treat benchmark unblock as the prerequisite before prompt iteration because the current prompt path lacks a trustworthy comparison artifact.
- 2026-03-06: Allow sparse Tier-1 gold-set labels in benchmark preflight; strict full-taxonomy coverage remains the responsibility of `horadus eval validate-taxonomy`.
- 2026-03-06: Do not promote a new pinned baseline from the 10-item human-verified run; use it as a candidate artifact only because scope differs from the existing 50-item baseline.
- 2026-03-07: Drop exploratory prompt edits from this task branch and treat prompt/model quality fixes as explicit follow-up tasks (`TASK-243`..`TASK-250`).

## Risks / Foot-guns

- Live benchmark depends on OpenAI credentials from `.env` / key-file wiring -> verify before claiming completion
- Benchmark code still contains stale model defaults -> update alongside prompt work to avoid misleading artifacts

## Validation Commands

- `uv run --no-sync pytest tests/unit/eval/ -v`
- `uv run --no-sync pytest tests/unit/processing/test_tier1_classifier.py tests/unit/processing/test_tier2_classifier.py -v`
- `uv run --no-sync horadus eval validate-taxonomy --gold-set ai/eval/gold_set.jsonl --trend-config-dir config/trends --output-dir ai/eval/results --max-items 200 --tier1-trend-mode subset --signal-type-mode warn --unknown-trend-mode warn`
- `uv run --no-sync horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --trend-config-dir config/trends --output-dir ai/eval/results --max-items 200 --require-human-verified --config baseline`

## Notes / Links

- Spec: none
- Relevant modules: `src/eval/benchmark.py`, `docs/PROMPT_EVAL_POLICY.md`
- Candidate benchmark artifacts:
  - `ai/eval/results/benchmark-20260306T201922Z-b856f658.json` (`max_items=1`, realtime sanity check)
  - `ai/eval/results/benchmark-20260306T202407Z-7706dc46.json` (`max_items=10`, human-verified, realtime)
