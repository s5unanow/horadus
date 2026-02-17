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

## TASK-044 Labeling Rubric (Human Review)

Use this rubric when curating/updating `ai/eval/gold_set.jsonl`.

Provenance and sourcing:
- Source candidate rows from real ingested items/events (not synthetic prompt-generated text).
- Keep `label_verification` as `llm_seeded` until manual review is complete.
- Set `label_verification=human_verified` only after reviewer approval.
- Recommended reviewer metadata (optional but strongly encouraged): reviewer name,
  review date, and short rationale in adjacent task artifacts under
  `tasks/assessments/`.

Tier-1 labeling:
- `expected.tier1.max_relevance` should reflect strongest trend relevance:
  `0-3` low/noise, `4-6` ambiguous/contextual, `7-10` clear queue candidate.
- `expected.tier1.trend_scores` keys must map to configured trend IDs, and scores
  should be internally consistent with `max_relevance`.
- Include explicit noise/low-relevance rows to keep queue-precision evaluation
  realistic.

Tier-2 labeling:
- Set `expected.tier2=null` for non-queued/noise rows.
- For queued rows, `expected.tier2.trend_id` must be a configured trend ID.
- `expected.tier2.signal_type` must exist in the selected trend's indicators.
- `direction` must match signal semantics (`escalatory` vs `de_escalatory`).
- Severity/confidence anchors:
  - severity: `0.0-0.3` weak/indirect, `0.4-0.7` material but bounded, `0.8-1.0`
    strong/high-impact
  - confidence: reviewer certainty in correctness of extracted signal and mapping

Coverage and diversity:
- Maintain representative coverage across active trends and noise cases.
- Avoid template-heavy duplicates; include varied regions, actors, and source types.
- Include edge cases: contradictory signals, weak relevance, borderline Tier-1
  items, and ambiguous signal mapping candidates.

Release gate expectation:
- `TASK-044` is complete only when curation review is documented and the dataset
  contains meaningful `human_verified` coverage with reviewer sign-off in sprint
  notes.

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
