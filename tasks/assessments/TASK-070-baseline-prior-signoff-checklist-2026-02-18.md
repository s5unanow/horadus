# TASK-070 Baseline Prior Review Checklist

Date: 2026-02-18  
Branch: `codex/task-070-baseline-prior-signoff`  
Task: `TASK-070` Trend Baseline Prior Review and Sign-Off `[REQUIRES_HUMAN]`

## Purpose

Capture required human analyst review/sign-off for baseline priors on active
trends before launch. `TASK-070` must not be marked DONE until this checklist
is fully completed and reviewer approval is recorded.

## Scope Reviewed

- Trend config source: `config/trends/*.yaml` (16 configured trends)
- Runtime trend baseline fields:
  - `trends.baseline_log_odds` (canonical baseline for decay/runtime)
  - `trends.definition.baseline_probability` (synced metadata)

## Config Baseline Snapshot (Pre-Review)

Use status values: `Approve`, `Needs Revision`, `Reject`.
`TASK-070` remains blocked until each active trend row is either `Approve` or
has a follow-up task recorded.

| Trend ID | Name | Config Baseline | File | Status | Reviewer | Date | Rationale / Notes |
|---|---|---:|---|---|---|---|---|
| `africa-agri-supply-shift` | Africa as an Emerging Global Food Basket | 0.11 | `config/trends/africa-agri-supply-shift.yaml` | Pending | `TBD` | `TBD` | `TBD` |
| `ai-control` | AI-Mediated Human Control Expansion | 0.25 | `config/trends/ai-human-control-expansion.yaml` | Pending | `TBD` | `TBD` | `TBD` |
| `dollar-hegemony-erosion` | Dollar Hegemony Erosion and Alternative Settlement Blocs | 0.25 | `config/trends/dollar-hegemony-erosion.yaml` | Pending | `TBD` | `TBD` | `TBD` |
| `elite-mass-polarization` | Elite-Mass Polarization and Agency Erosion | 0.38 | `config/trends/elite-mass-polarization.yaml` | Pending | `TBD` | `TBD` | `TBD` |
| `eu-russia` | Russia-Europe Direct Conflict Escalation | 0.08 | `config/trends/eu-russia.yaml` | Pending | `TBD` | `TBD` | `TBD` |
| `fertility-decline` | Fertility Decline Acceleration | 0.35 | `config/trends/fertility-decline-acceleration.yaml` | Pending | `TBD` | `TBD` | `TBD` |
| `global-infectious-threat` | Emergence of Globally Significant Infectious Threats | 0.12 | `config/trends/global-infectious-threat-emergence.yaml` | Pending | `TBD` | `TBD` | `TBD` |
| `normative-deviance-normalization` | Normalization of Extreme Taboo Violations in Public Discourse | 0.10 | `config/trends/normative-deviance-normalization.yaml` | Pending | `TBD` | `TBD` | `TBD` |
| `parallel-enclaves-europe` | Parallel Governance Zones in Europe | 0.12 | `config/trends/parallel-enclaves-europe.yaml` | Pending | `TBD` | `TBD` | `TBD` |
| `protein-transition` | Protein Transition from Traditional Meat to Alternatives | 0.14 | `config/trends/protein-transition-alternative-sources.yaml` | Pending | `TBD` | `TBD` | `TBD` |
| `russia-turkey` | Russia-Turkey Direct Conflict Escalation | 0.05 | `config/trends/russia-turkey-conflict-escalation.yaml` | Pending | `TBD` | `TBD` | `TBD` |
| `south-america-agri-supply-shift` | South America Strengthening Global Food Supply Leadership | 0.33 | `config/trends/south-america-agri-supply-shift.yaml` | Pending | `TBD` | `TBD` | `TBD` |
| `three-seas-bloc-consolidation` | Three Seas Bloc Consolidation | 0.14 | `config/trends/three-seas-bloc-consolidation.yaml` | Pending | `TBD` | `TBD` | `TBD` |
| `ukraine-security-frontier-model` | Ukraine as a Long-Horizon Militarized Frontier | 0.40 | `config/trends/ukraine-security-frontier-model.yaml` | Pending | `TBD` | `TBD` | `TBD` |
| `us-china` | US-China Direct War Escalation | 0.09 | `config/trends/us-china-war-escalation.yaml` | Pending | `TBD` | `TBD` | `TBD` |
| `us-internal` | US Internal Armed Conflict Risk | 0.05 | `config/trends/us-internal-armed-conflict-risk.yaml` | Pending | `TBD` | `TBD` | `TBD` |

## Human Review Gate Checklist

- [ ] Confirm each active trend baseline prior is defensible for current horizon.
- [ ] Confirm adjusted priors (if any) are applied via API/config with rationale.
- [ ] Confirm each reviewed trend has reviewer/date stamped in the table above.
- [ ] Confirm non-approved rows have explicit follow-up task IDs recorded.
- [ ] Confirm final reviewer sign-off fields are completed below.

## Post-Review Baseline Consistency Check

Run after any baseline edits to ensure DB canonical baseline and metadata are in
sync for active trends:

```sql
SELECT
  name,
  ROUND((1 / (1 + exp(-baseline_log_odds::numeric)))::numeric, 6) AS baseline_prob_from_log_odds,
  ROUND(COALESCE((definition->>'baseline_probability')::numeric, NULL), 6) AS baseline_prob_in_definition,
  ROUND(
    ABS(
      (1 / (1 + exp(-baseline_log_odds::numeric))) -
      COALESCE((definition->>'baseline_probability')::numeric, NULL)
    )::numeric,
    6
  ) AS abs_diff
FROM trends
WHERE is_active = true
ORDER BY name;
```

Pass condition:
- Every active trend has non-null `baseline_prob_in_definition`
- Every active trend has `abs_diff <= 0.0001`

## Final Task-Level Sign-Off

- Reviewer name: `TBD`
- Review date: `TBD`
- Decision: `Pending` (`Approved` / `Blocked`)
- Blocking issues (if any): `TBD`
- Notes for sprint record: `TBD`

## Sprint Note Snippet (copy after review)

`TASK-070` reviewer sign-off: Reviewer=`<name>`; Date=`<YYYY-MM-DD>`; Decision=`<Approved|Blocked>`; Notes=`<short rationale>`.
