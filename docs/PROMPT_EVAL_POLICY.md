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
- Current project status: human verification is still in progress (`TASK-044`)

Until `TASK-044` is complete:
- Treat benchmark outcomes as provisional.
- Still run the workflow to catch regressions.

## Baseline Source of Truth

Two artifact types are required:

1. Candidate run artifacts (always timestamped):
- `ai/eval/results/benchmark-*.json`
- `ai/eval/results/audit-*.json`

2. Accepted baseline artifact (pinned):
- Keep one committed baseline JSON in Git, e.g. `ai/eval/baselines/current.json`.
- Update this file only when a prompt change is explicitly accepted.
- Keep previous accepted baselines under `ai/eval/baselines/history/` when replacing `current.json`.

Without a pinned baseline, comparisons become ambiguous over time.

## Gold-Set Change Supersession Rule

When `ai/eval/gold_set.jsonl` content or labels change, prior pass/fail comparisons are superseded.

Required handling:
- Treat existing `current.json` comparisons as historical-only for the previous dataset version.
- Run fresh audit + benchmark against the updated dataset before any promotion decision.
- Promote a new `current.json` only from runs that share the same dataset fingerprint metadata.
- Archive the replaced baseline under `ai/eval/baselines/history/` with a date/tag.

## Release Gate Workflow

1. Validate dataset quality
- Run: `uv run --no-sync horadus eval audit --gold-set ai/eval/gold_set.jsonl --output-dir ai/eval/results --max-items 200 --fail-on-warnings`
- If audit fails, do not promote prompt changes.

2. Run benchmark
- Preferred (true gold): `uv run --no-sync horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --output-dir ai/eval/results --max-items 200 --require-human-verified`
- Temporary fallback (until TASK-044): run without `--require-human-verified`, and mark run as provisional.

3. Compare candidate vs pinned baseline
- Compare the same config(s), same dataset scope, same dataset fingerprint, and same queue threshold assumptions.
- Record comparison notes in PR description.

4. Decision
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
3. Deploy worker/runtime before the next scheduled processing window.

Operational note:
- Prompts are loaded from file when classifiers are initialized, so new runs use new prompt files after deployment/startup.

## Rollback

If post-deploy quality issues appear:

1. Revert prompt commit.
2. Redeploy worker/runtime.
3. Re-run benchmark to confirm metrics return near baseline.
4. Document rollback reason in sprint/task notes.
