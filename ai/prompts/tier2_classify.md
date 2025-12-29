# Tier 2 — Classification (Prompt Template)

Purpose: thorough extraction + structured classification for events and per-trend impacts.

Model (current): `gpt-4o-mini` (see `docs/adr/002-llm-provider.md`)

## Inputs (planned)
- `item.title`
- `item.raw_content` (or normalized extracted text)
- `trend definitions` (indicator weights, keywords, disqualifiers)

## Output (planned; strict JSON)
- Event extraction: who/what/where/when/claims + categories
- Per relevant trend:
  - `signal_type`
  - `direction` (`escalatory` / `de_escalatory`)
  - `severity` (`0.0..1.0`)
  - `confidence` (`0.0..1.0`)
- 2-sentence event summary

## Prompt

TBD (define when implementing `TASK-014`).
