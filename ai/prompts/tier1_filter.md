# Tier 1 — Relevance Filter (Prompt Template)

Purpose: fast, cheap relevance scoring to decide whether an item should proceed to Tier 2.

Model (current): `gpt-4.1-nano` (see `docs/adr/002-llm-provider.md`)

## Inputs (planned)
- `item.title`
- `item.raw_content` (or trimmed excerpt)
- `trends[]` (ids/names + indicator keywords)

## Output (planned; strict JSON)
- Per trend: relevance score `0..10`
- Optional brief rationale (short, non-narrative)

## Prompt

TBD (define when implementing `TASK-013`).
