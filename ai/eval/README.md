# Evaluation

This folder is the home for model/provider evaluation artifacts (`TASK-041`).

Recommended layout:

- `ai/eval/gold_set.jsonl` — labeled items (inputs + expected structured outputs)
- `ai/eval/results/` — benchmark outputs (timestamped)

Each JSONL row supports:

- `label_verification` — label provenance (`human_verified`, `llm_seeded`, etc.)
- `expected.tier1` and optional `expected.tier2` — target labels for scoring

Run benchmark:

```bash
uv run --no-sync horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --output-dir ai/eval/results --max-items 50
```

Run benchmark on only human-reviewed rows:

```bash
uv run --no-sync horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --output-dir ai/eval/results --max-items 200 --require-human-verified
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
- `tier1_metrics.queue_threshold`: routing cutoff used for queue-accuracy scoring.
- `tier2_metrics.*_accuracy`: higher is better for structured extraction fields.
- `tier2_metrics.*_mae`: lower is better for severity/confidence calibration.
- `usage.estimated_cost_per_item_usd`: compare cost-efficiency across configs.

Notes:
- Treat only `label_verification=human_verified` rows as the true gold set.
- Use LLM-seeded labels as silver/pre-label drafts, then human-correct.
- Keep gold data small, curated, and representative.
- Avoid storing sensitive content.
