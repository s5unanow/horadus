# Automation: Daily Horadus Friction Summary

Run the canonical repo workflow that turns structured Horadus CLI friction
entries into a compact daily report.

## Canonical Command

Use the repo-owned CLI flow, not ad hoc parsing:

```bash
uv run --no-sync horadus tasks summarize-friction --date YYYY-MM-DD --output artifacts/agent/horadus-cli-feedback/daily/YYYY-MM-DD.md
```

Use the real current UTC date for `YYYY-MM-DD`.

## Inputs

- `artifacts/agent/horadus-cli-feedback/entries.jsonl`
- `docs/AGENT_RUNBOOK.md` (for operator workflow context if needed)

## Required Behavior

- Produce the report at `artifacts/agent/horadus-cli-feedback/daily/YYYY-MM-DD.md`.
- Keep the summary compact and grouped by repeated patterns/candidate
  improvements; do not dump raw JSONL rows verbatim into the report.
- If no friction entries exist for the date, still write the empty daily
  checkpoint report.
- Treat the repo-owned automation spec under `ops/automations/` as the source
  of truth. Local `$CODEX_HOME/automations/` content is only the applied runtime
  target.
- Do not create or edit backlog tasks automatically. Candidate follow-up tasks
  remain human-review suggestions inside the report only.

## Final Check

- Confirm the report exists at the expected path before finishing.
