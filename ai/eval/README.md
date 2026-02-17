# Evaluation

This folder is the home for model/provider evaluation artifacts (`TASK-041`).

Policy reference:
- `docs/PROMPT_EVAL_POLICY.md` — prompt benchmark gates, promotion, and rollback workflow.

Recommended layout:

- `ai/eval/gold_set.jsonl` — labeled items (inputs + expected structured outputs)
- `ai/eval/results/` — benchmark outputs (timestamped)
- `ai/eval/baselines/current.json` — pinned accepted benchmark baseline artifact

Each JSONL row supports:

- `label_verification` — label provenance (`human_verified`, `llm_seeded`, etc.)
- `expected.tier1` and optional `expected.tier2` — target labels for scoring

Run benchmark:

```bash
uv run --no-sync horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --output-dir ai/eval/results --max-items 50
```

Offline cost-oriented modes:

```bash
# Batch Tier-1 dispatch + flex priority hint (when provider supports service_tier)
uv run --no-sync horadus eval benchmark --dispatch-mode batch --request-priority flex
```

Mode guidance:
- `--dispatch-mode realtime` (default): one-item Tier-1 calls; closest to production request shape.
- `--dispatch-mode batch`: grouped Tier-1 calls for lower-cost offline sweeps/backfills.
- `--request-priority flex`: low-priority provider hint for non-urgent offline runs.
- Keep real-time runtime paths unchanged; these flags are intended for offline eval/backfill workflows.

Run quality audit:

```bash
uv run --no-sync horadus eval audit --gold-set ai/eval/gold_set.jsonl --output-dir ai/eval/results --max-items 200
```

Validate trend-taxonomy and gold-set contract (strict mode):

```bash
uv run --no-sync horadus eval validate-taxonomy --gold-set ai/eval/gold_set.jsonl --trend-config-dir config/trends --output-dir ai/eval/results --max-items 200 --tier1-trend-mode strict --signal-type-mode strict --unknown-trend-mode strict
```

Validate in transitional compatibility mode (subset/warn):

```bash
uv run --no-sync horadus eval validate-taxonomy --gold-set ai/eval/gold_set.jsonl --trend-config-dir config/trends --output-dir ai/eval/results --max-items 200 --tier1-trend-mode subset --signal-type-mode warn --unknown-trend-mode warn
```

Run audit with failing exit code when warnings are present:

```bash
uv run --no-sync horadus eval audit --gold-set ai/eval/gold_set.jsonl --output-dir ai/eval/results --max-items 200 --fail-on-warnings
```

Run benchmark on only human-reviewed rows:

```bash
uv run --no-sync horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --output-dir ai/eval/results --max-items 200 --require-human-verified
```

Run full 200-item benchmark:

```bash
uv run --no-sync horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --output-dir ai/eval/results --max-items 200
```

Run ANN vector strategy benchmark:

```bash
uv run --no-sync horadus eval vector-benchmark --output-dir ai/eval/results
```

Run embedding lineage audit (model drift + re-embed scope):

```bash
uv run --no-sync horadus eval embedding-lineage --target-model text-embedding-3-small
```

Vector benchmark now also maintains:
- `ai/eval/results/vector-benchmark-summary.json` (rolling recommendation history)
- Operator cadence/promote checklist: `docs/VECTOR_REVALIDATION.md`

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
- `audit.passes_quality_gate`: true only when no coverage/diversity/provenance warnings are present.

Notes:
- Treat only `label_verification=human_verified` rows as the true gold set.
- Use LLM-seeded labels as silver/pre-label drafts, then human-correct.
- Keep gold data small, curated, and representative.
- Avoid storing sensitive content.
- CI and `make audit-eval` currently run taxonomy validation in transitional mode
  (`subset`/`warn`) until human-gated taxonomy/gold-set harmonization is complete.

Baseline update procedure:
1. Run `horadus eval audit` (and fail on warnings for release gates).
2. Run `horadus eval benchmark` with the candidate prompt/model config.
3. Confirm `dataset_scope`, `gold_set_fingerprint_sha256`, and `gold_set_item_ids_sha256` match when comparing candidate vs baseline.
4. Compare candidate results against `ai/eval/baselines/current.json` per `docs/PROMPT_EVAL_POLICY.md`.
5. On approval, move previous `current.json` to `ai/eval/baselines/history/<date>-<tag>.json`.
6. Replace `ai/eval/baselines/current.json` with the accepted benchmark artifact and commit.

Gold-set update rule:
- If `ai/eval/gold_set.jsonl` rows or labels change, previous pass/fail baselines are superseded.
- Keep prior baselines for history only; do not use them as gate comparisons for the new dataset version.
