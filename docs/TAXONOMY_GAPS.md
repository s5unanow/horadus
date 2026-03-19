# Taxonomy Gap Triage

**Last Verified**: 2026-03-19

## Purpose

`taxonomy_gaps` records runtime cases where deterministic trend-impact mapping
could not produce a safe, scoreable indicator assignment:

- `unknown_trend_id`
- `unknown_signal_type`
- `ambiguous_mapping`
- `no_matching_indicator`

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

1. Inspect `details` to see the extracted claim text and any candidate mappings.
2. If the deterministic mapper was missing an equivalent indicator, normalize config and close as `resolved`.
3. If the gap is a genuine new signal, add the indicator in `config/trends/*.yaml`, sync trends, and close as `resolved`.
4. If the case is ambiguous, refine the trend metadata or extraction contract so one unique mapping becomes possible.
5. If the case is out-of-scope/noisy, close as `rejected` with rationale.

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
