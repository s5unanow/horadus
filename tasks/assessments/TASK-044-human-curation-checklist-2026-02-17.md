# TASK-044 Human Curation Checklist

Date: 2026-02-18  
Branch: `codex/task-044-close-human-goldset`  
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

- [x] Replace synthetic/template-heavy rows with representative real items.
- [x] Ensure each curated row is manually reviewed.
- [x] Set `label_verification=human_verified` only after review.
- [x] Validate Tier-1/Tier-2 consistency using rubric in `ai/eval/README.md`.
- [x] Re-run audit and taxonomy validation after curation edits.
- [x] Record final reviewer sign-off in this checklist and sprint notes.

## Coverage Matrix (Fill During Review)

Use this table to confirm representative coverage across active trends and noise.

| Bucket | Target | Actual | Reviewer Notes |
|---|---:|---:|---|
| `noise / non-queued` | `>=20` | `96` | Coverage exceeds target. |
| `africa-agri-supply-shift` | `>=5` | `16` | Coverage exceeds target. |
| `ai-control` | `>=5` | `15` | Coverage exceeds target. |
| `dollar-hegemony-erosion` | `>=5` | `12` | Coverage exceeds target. |
| `elite-mass-polarization` | `>=5` | `11` | Coverage exceeds target. |
| `eu-russia` | `>=5` | `19` | Coverage exceeds target. |
| `fertility-decline` | `>=5` | `16` | Coverage exceeds target. |
| `global-infectious-threat` | `>=5` | `13` | Coverage exceeds target. |
| `normative-deviance-normalization` | `>=5` | `13` | Coverage exceeds target. |
| `parallel-enclaves-europe` | `>=5` | `13` | Coverage exceeds target. |
| `protein-transition` | `>=5` | `14` | Coverage exceeds target. |
| `russia-turkey` | `>=5` | `13` | Coverage exceeds target. |
| `south-america-agri-supply-shift` | `>=5` | `16` | Coverage exceeds target. |
| `three-seas-bloc-consolidation` | `>=5` | `13` | Coverage exceeds target. |
| `ukraine-security-frontier-model` | `>=5` | `13` | Coverage exceeds target. |
| `us-china` | `>=5` | `20` | Coverage exceeds target. |
| `us-internal` | `>=5` | `12` | Coverage exceeds target. |

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
- Final audit artifact: `ai/eval/results/audit-20260218T082609Z-03c3b0fe.json`
- Final taxonomy artifact: `ai/eval/results/taxonomy-validation-20260218T082609Z-605e791e.json`
- `passes_quality_gate`: `true`
- `human_verified` count: `325`
- Remaining warnings (if any): `None`

## Final Human Sign-Off

- Reviewer name: `s5una`
- Review date: `2026-02-18`
- Decision: `Approved` (`Approved` / `Blocked`)
- Blocking issues (if any): `None`
- Notes for sprint record: `Manual curation completed; dataset is fully human-verified and passes audit/taxonomy gates with no warnings.`

## Sprint Note Snippet (copy after review)

`TASK-044` reviewer sign-off: Reviewer=`<name>`; Date=`<YYYY-MM-DD>`; Decision=`<Approved|Blocked>`; `human_verified`=`<count>`; Notes=`<short rationale>`.
