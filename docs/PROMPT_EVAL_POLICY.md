# Prompt Evaluation and Promotion Policy

## Purpose

Define a lightweight, repeatable process for changing LLM prompts without degrading extraction quality or exploding cost.

This policy covers:
- Tier-1 prompt: `ai/prompts/tier1_filter.md`
- Tier-2 prompt: `ai/prompts/tier2_classify.md`

## What This Is (and Is Not)

- This is a **pre-release gate** for prompt/model changes.
- This is not a replacement for runtime calibration monitoring (`docs/CALIBRATION_RUNBOOK.md`).

## Golden Set Requirements

- Primary dataset: `ai/eval/gold_set.jsonl`
- True gold rows: `label_verification="human_verified"`
- Current project status: human verification was completed in `TASK-044`

## Baseline Source of Truth

Two artifact types are required:

1. Candidate run artifacts (always timestamped):
- `ai/eval/results/benchmark-*.json`
- `ai/eval/results/audit-*.json`
- These remain ignored/untracked by default and are for exploratory or candidate runs only.

2. Accepted baseline artifact (pinned):
- Keep one committed baseline JSON in Git, e.g. `ai/eval/baselines/current.json`.
- Update this file only when a prompt change is explicitly accepted.
- Keep previous accepted baselines under `ai/eval/baselines/history/` when replacing `current.json`.
- If you need a committed milestone snapshot (for example a major model-switch decision), promote it through the same path by copying the selected artifact into `ai/eval/baselines/history/<date>-<tag>.json` and documenting why it is being retained.

Without a pinned baseline, comparisons become ambiguous over time.

## Gold-Set Change Supersession Rule

When `ai/eval/gold_set.jsonl` content or labels change, prior pass/fail comparisons are superseded.

Required handling:
- Treat existing `current.json` comparisons as historical-only for the previous dataset version.
- Run fresh audit + benchmark against the updated dataset before any promotion decision.
- Promote a new `current.json` only from runs that share the same dataset fingerprint metadata.
- Archive the replaced baseline under `ai/eval/baselines/history/` with a date/tag.

## Release Gate Workflow

1. Validate taxonomy contract
- Strict gate (target state): `uv run --no-sync horadus eval validate-taxonomy --gold-set ai/eval/gold_set.jsonl --trend-config-dir config/trends --output-dir ai/eval/results --max-items 200 --tier1-trend-mode strict --signal-type-mode strict --unknown-trend-mode strict`
- Transitional gate (while taxonomy/gold-set alignment is still in progress): `uv run --no-sync horadus eval validate-taxonomy --gold-set ai/eval/gold_set.jsonl --trend-config-dir config/trends --output-dir ai/eval/results --max-items 200 --tier1-trend-mode subset --signal-type-mode warn --unknown-trend-mode warn`

2. Validate dataset quality
- Run: `uv run --no-sync horadus eval audit --gold-set ai/eval/gold_set.jsonl --output-dir ai/eval/results --max-items 200 --fail-on-warnings`
- If audit fails, do not promote prompt changes.

3. Run benchmark
- Preferred (true gold): `uv run --no-sync horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --trend-config-dir config/trends --output-dir ai/eval/results --max-items 200 --require-human-verified`
- Transitional fallback for broader historical comparison: run without `--require-human-verified`, and mark run as provisional.
- Benchmark accepts sparse Tier-1 `trend_scores` labels, but still fails fast on unknown trend IDs or unknown Tier-2 signal mappings.
- Accepted safe benchmark mode is realtime dispatch, which forces Tier-1 `batch_size=1` and records `tier1_batch_policy=safe_single_item_default`.
- `--dispatch-mode batch` is diagnostic-only while Tier-1 multi-item scoring remains unstable on the current baseline models. Those artifacts record `tier1_batch_policy=diagnostic_multi_item_batch`.
- Do not re-enable multi-item Tier-1 runtime batching by default until a same-slice human-verified benchmark shows no worse failure rate and no worse queue accuracy than realtime dispatch.
- Benchmark artifacts now include per-item stage diagnostics under each config’s `item_results`, including failure category/message, raw model output when available, and compact predicted summaries for successful rows.
- Benchmark artifacts also include reproducibility provenance: source-control state (`git` commit SHA + dirty/clean flag when available), prompt file paths/content hashes, trend-config fingerprint, and per-config invocation provenance (`api_mode`, `reasoning_effort`, normalized request overrides).
- Metadata-only prompt/payload enrichments still require the same benchmark evidence; do not assume richer indicator descriptions improve Tier-2 accuracy without a fresh artifact comparison.
- GPT-5 candidate evaluations may stay on Chat Completions in this repo as long as the benchmark artifact records any stage-specific `reasoning_effort` / `temperature` overrides; current Tier-1/Tier-2 Responses-mode structured-output parity is not required just to compare GPT-5 candidates.

4. Compare candidate vs pinned baseline
- Compare the same config(s), same dataset scope, same dataset fingerprint, and same queue threshold assumptions.
- Record comparison notes in PR description.

5. Decision
- Promote only if candidate passes all required gates below.

## Required Gates (Initial Defaults)

Use these simple thresholds first; tune later if needed:

- `tier1_metrics.score_mae`: must not increase by more than `+0.05`
- `tier1_metrics.queue_accuracy`: must not decrease by more than `-0.02`
- `tier2_metrics.trend_match_accuracy`: must not decrease by more than `-0.03`
- `tier2_metrics.signal_type_accuracy`: must not decrease by more than `-0.03`
- `tier2_metrics.direction_accuracy`: must not decrease by more than `-0.03`
- `tier2_metrics.severity_mae`: must not increase by more than `+0.03`
- `tier2_metrics.confidence_mae`: must not increase by more than `+0.03`
- `usage.estimated_cost_per_item_usd`: must not increase by more than `20%` unless quality materially improves

If any required gate fails, reject or revise the prompt.

## Champion/Challenger Replay Gate

Before promotion, run historical replay on the same time window and scope for
both candidate policies:

- `uv run --no-sync horadus eval replay --output-dir ai/eval/results --champion-config stable --challenger-config fast_lower_threshold --days 90`

Replay artifacts (`ai/eval/results/replay-*.json`) include:
- Shared window + dataset counts (`raw_items`, `events`, `trend_evidence`, `trend_snapshots`, `trend_outcomes`)
- Side-by-side quality/cost/latency metrics
- Numeric deltas and a promotion assessment block

Default replay promotion criteria:
- `quality.decision_accuracy`: challenger must not regress by more than `-0.01`
- `quality.mean_brier_score`: challenger must not worsen by more than `+0.01`
- `cost.estimated_total_cost_usd`: challenger must not increase by more than `20%`
- `latency.estimated_p95_latency_ms`: challenger must not increase by more than `20%`

If replay gate fails, keep champion and revise challenger config/prompt.

## Promotion and Deployment

After acceptance:

1. Merge prompt change.
2. Commit/update pinned baseline artifact.
   - Move old `ai/eval/baselines/current.json` into `ai/eval/baselines/history/` first.
   - Do not commit the raw timestamped file from `ai/eval/results/` directly; promote by copying the chosen artifact into `current.json` or `history/<date>-<tag>.json`.
3. Deploy worker/runtime before the next scheduled processing window.

Operational note:
- Prompts are loaded from file when classifiers are initialized, so new runs use new prompt files after deployment/startup.

## Rollback

If post-deploy quality issues appear:

1. Revert prompt commit.
2. Redeploy worker/runtime.
3. Re-run benchmark to confirm metrics return near baseline.
4. Document rollback reason in sprint/task notes.
