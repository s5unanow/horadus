# Tier 2 — Classification

Purpose: thorough extraction + structured classification for events and per-trend impacts.

Model (current): `gpt-4o-mini` (see `docs/adr/002-llm-provider.md`)

## Runtime Contract

The caller will send JSON with:
- `event_id`
- `summary`
- `context_chunks[]`
- `trends[]` including indicator metadata

Return JSON only, with this exact shape:

```json
{
  "summary": "two-sentence canonical summary",
  "extracted_who": ["entity"],
  "extracted_what": "what happened",
  "extracted_where": "location or null",
  "extracted_when": "ISO-8601 datetime or null",
  "claims": ["factual claim"],
  "categories": ["taxonomy-tag"],
  "trend_impacts": [
    {
      "trend_id": "trend-id",
      "signal_type": "indicator key",
      "direction": "escalatory",
      "severity": 0.8,
      "confidence": 0.9,
      "rationale": "short explanation"
    }
  ]
}
```

Rules:
- Use only provided `trend_id` values.
- `direction` must be `escalatory` or `de_escalatory`.
- `severity` and `confidence` must be floats in `0.0..1.0`.
- Keep `summary` concise (2 sentences).
- Output strict JSON only, no markdown or extra keys.
