# TASK-044 Human Curation Checklist

Date: 2026-02-17  
Branch: `codex/task-044-human-gold-curation-scaffold`  
Task: `TASK-044` Curated Human-Verified Gold Dataset `[REQUIRES_HUMAN]`

## Purpose

This checklist captures required manual curation and reviewer sign-off for
`ai/eval/gold_set.jsonl`. `TASK-044` must not be marked DONE until this file is
completed and reviewer approval is recorded.

## Current Baseline (Before Human Curation)

Audit command:

```bash
uv run --no-sync horadus eval audit \
  --gold-set ai/eval/gold_set.jsonl \
  --output-dir ai/eval/results \
  --max-items 200
```

Latest audit artifact:
- `ai/eval/results/audit-20260217T212003Z-35618e5e.json`

Baseline summary:
- `passes_quality_gate=false`
- `label_verification`: `llm_seeded=200`, `human_verified=0`
- Content diversity warning: `4/200` unique contents
- Duplicate content warning: `4` groups, largest `50`

## Human Curation Requirements

- [ ] Replace synthetic/template-heavy rows with representative real items.
- [ ] Ensure each curated row is manually reviewed.
- [ ] Set `label_verification=human_verified` only after review.
- [ ] Validate Tier-1/Tier-2 consistency using rubric in `ai/eval/README.md`.
- [ ] Re-run audit and taxonomy validation after curation edits.
- [ ] Record final reviewer sign-off in this checklist and sprint notes.

## Coverage Matrix (Fill During Review)

Use this table to confirm representative coverage across active trends and noise.

| Bucket | Target | Actual | Reviewer Notes |
|---|---:|---:|---|
| `noise / non-queued` | `>=20` |  |  |
| `africa-agri-supply-shift` | `>=5` |  |  |
| `ai-control` | `>=5` |  |  |
| `dollar-hegemony-erosion` | `>=5` |  |  |
| `elite-mass-polarization` | `>=5` |  |  |
| `eu-russia` | `>=5` |  |  |
| `fertility-decline` | `>=5` |  |  |
| `global-infectious-threat` | `>=5` |  |  |
| `normative-deviance-normalization` | `>=5` |  |  |
| `parallel-enclaves-europe` | `>=5` |  |  |
| `protein-transition` | `>=5` |  |  |
| `russia-turkey` | `>=5` |  |  |
| `south-america-agri-supply-shift` | `>=5` |  |  |
| `three-seas-bloc-consolidation` | `>=5` |  |  |
| `ukraine-security-frontier-model` | `>=5` |  |  |
| `us-china` | `>=5` |  |  |
| `us-internal` | `>=5` |  |  |

## Post-Curation Validation Evidence

Audit (quality):

```bash
uv run --no-sync horadus eval audit \
  --gold-set ai/eval/gold_set.jsonl \
  --output-dir ai/eval/results \
  --max-items 200
```

Taxonomy contract (transitional mode for current policy):

```bash
uv run --no-sync horadus eval validate-taxonomy \
  --gold-set ai/eval/gold_set.jsonl \
  --trend-config-dir config/trends \
  --output-dir ai/eval/results \
  --max-items 200 \
  --tier1-trend-mode subset \
  --signal-type-mode warn \
  --unknown-trend-mode warn
```

Fill after review:
- Final audit artifact:
- Final taxonomy artifact:
- `passes_quality_gate`:
- `human_verified` count:
- Remaining warnings (if any):

## Final Human Sign-Off

- Reviewer name: `TBD`
- Review date: `TBD`
- Decision: `Pending` (`Approved` / `Blocked`)
- Blocking issues (if any): `TBD`
- Notes for sprint record: `TBD`

## Sprint Note Snippet (copy after review)

`TASK-044` reviewer sign-off: Reviewer=`<name>`; Date=`<YYYY-MM-DD>`; Decision=`<Approved|Blocked>`; `human_verified`=`<count>`; Notes=`<short rationale>`.
