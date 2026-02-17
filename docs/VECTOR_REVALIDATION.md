# Vector Strategy Revalidation

**Last Verified**: 2026-02-16

This runbook defines when and how to revalidate ANN strategy selection
(`exact` vs `ivfflat` vs `hnsw`) as vector volume/distribution evolves.

## Triggers

Run `horadus eval vector-benchmark` when either trigger is hit:

1. **Time cadence**: every `VECTOR_REVALIDATION_CADENCE_DAYS` (default: 30 days)
2. **Dataset growth**: benchmark/profile size grows by
   `VECTOR_REVALIDATION_DATASET_GROWTH_PCT` (default: 20%) vs last revalidation

## Command

```bash
uv run --no-sync horadus eval vector-benchmark --output-dir ai/eval/results
```

Artifacts produced:
- Timestamped benchmark JSON: `ai/eval/results/vector-benchmark-<timestamp>-<hash>.json`
- Rolling recommendation summary: `ai/eval/results/vector-benchmark-summary.json`

## Promotion Criteria

A candidate strategy/index profile is promotable only when:

- `recall_at_k >= 0.95`
- `avg_latency_ms` is at least 5% faster than exact baseline
- Result remains consistent with recent historical runs in summary history
- Change is documented before migration/index profile update

## Operator Checklist

1. Run benchmark and inspect `recommendation.selected_default`.
2. Compare new result with `vector-benchmark-summary.json` history.
3. If recommendation changes, document rationale and rollout plan.
4. Apply index/profile change via migration (or explicit metadata alignment task).
5. Re-run benchmark after rollout to confirm expected performance/recall.
6. If results regress, rollback to previous index/profile and re-run benchmark.
