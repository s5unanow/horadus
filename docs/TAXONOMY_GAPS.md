# Taxonomy Gap Triage

**Last Verified**: 2026-02-18

## Purpose

`taxonomy_gaps` records runtime cases where Tier-2 emitted a trend impact that was
not scoreable against current trend taxonomy:

- `unknown_trend_id`
- `unknown_signal_type`

Safety rule: these impacts are never applied to trend log-odds deltas.

## Review API

List open/recent gaps and top unknown signal keys by trend:

```bash
curl -sS "$BASE_URL/api/v1/taxonomy-gaps?days=7&limit=100&status=open" \
  -H "X-API-Key: $API_KEY"
```

Mark as resolved after taxonomy update:

```bash
curl -sS -X PATCH "$BASE_URL/api/v1/taxonomy-gaps/$GAP_ID" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "status": "resolved",
    "resolution_notes": "Mapped to existing indicator `military_movement`.",
    "resolved_by": "analyst@horadus"
  }'
```

Reject as out-of-scope:

```bash
curl -sS -X PATCH "$BASE_URL/api/v1/taxonomy-gaps/$GAP_ID" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "status": "rejected",
    "resolution_notes": "Signal is outside launch taxonomy scope.",
    "resolved_by": "analyst@horadus"
  }'
```

## Resolution Workflow

For each open gap:

1. Validate whether the emitted signal maps to an existing indicator.
2. If equivalent, normalize prompt/config and close as `resolved`.
3. If new-but-valid, add indicator in `config/trends/*.yaml`, sync trends, close as `resolved`.
4. If out-of-scope/noisy, close as `rejected` with rationale.

## Benchmark Guard

`horadus eval benchmark` now loads taxonomy from `config/trends/*.yaml` and fails
fast on gold-set mismatch before scoring. Use:

```bash
uv run --no-sync horadus eval benchmark \
  --gold-set ai/eval/gold_set.jsonl \
  --trend-config-dir config/trends \
  --output-dir ai/eval/results \
  --max-items 200 \
  --require-human-verified
```
