# Evaluation

This folder is the home for model/provider evaluation artifacts (`TASK-041`).

Recommended layout:

- `ai/eval/gold_set.jsonl` — labeled items (inputs + expected structured outputs)
- `ai/eval/results/` — benchmark outputs (timestamped)

Run benchmark:

```bash
uv run --no-sync horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --output-dir ai/eval/results --max-items 50
```

Run full 200-item benchmark:

```bash
uv run --no-sync horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --output-dir ai/eval/results --max-items 200
```

You can select a specific model pair:

```bash
uv run --no-sync horadus eval benchmark --config baseline
uv run --no-sync horadus eval benchmark --config alternative
```

Interpretation guide:

- `tier1_metrics.score_mae`: lower is better (trend-score calibration quality).
- `tier1_metrics.queue_accuracy`: higher is better (Tier-2 routing precision).
- `tier2_metrics.*_accuracy`: higher is better for structured extraction fields.
- `tier2_metrics.*_mae`: lower is better for severity/confidence calibration.
- `usage.estimated_cost_per_item_usd`: compare cost-efficiency across configs.

Notes:
- Keep gold data small, curated, and representative.
- Avoid storing sensitive content.
