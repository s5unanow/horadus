# Tier 1 — Relevance Filter

Purpose: fast, cheap relevance scoring to decide whether an item should proceed to Tier 2.

Model (current): `gpt-4.1-nano` (see `docs/adr/002-llm-provider.md`)

## Runtime Contract

The caller will send JSON with:
- `threshold`: minimum score for Tier 2 routing (currently 5)
- `trends[]`: `{ trend_id, name, keywords[] }`
- `items[]`: `{ item_id, title, content }`

Return JSON only, with this exact shape:

```json
{
  "items": [
    {
      "item_id": "uuid-string",
      "trend_scores": [
        {
          "trend_id": "trend-id",
          "relevance_score": 0,
          "rationale": "short reason"
        }
      ]
    }
  ]
}
```

Rules:
- Score each `item_id` against every provided `trend_id`.
- `relevance_score` must be an integer `0..10`.
- Use `0` for clearly unrelated trends.
- Keep `rationale` short and factual.
- Do not include extra keys or prose outside JSON.
