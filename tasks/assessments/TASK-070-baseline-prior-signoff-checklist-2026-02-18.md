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
| `africa-agri-supply-shift` | Africa as an Emerging Global Food Basket | 0.11 | `config/trends/africa-agri-supply-shift.yaml` | Approve | `s5una` | `2026-02-18` | `Approved in baseline prior sign-off.` |
| `ai-control` | AI-Mediated Human Control Expansion | 0.25 | `config/trends/ai-human-control-expansion.yaml` | Approve | `s5una` | `2026-02-18` | `Approved in baseline prior sign-off.` |
| `dollar-hegemony-erosion` | Dollar Hegemony Erosion and Alternative Settlement Blocs | 0.25 | `config/trends/dollar-hegemony-erosion.yaml` | Approve | `s5una` | `2026-02-18` | `Approved in baseline prior sign-off.` |
| `elite-mass-polarization` | Elite-Mass Polarization and Agency Erosion | 0.38 | `config/trends/elite-mass-polarization.yaml` | Approve | `s5una` | `2026-02-18` | `Approved in baseline prior sign-off.` |
| `eu-russia` | Russia-Europe Direct Conflict Escalation | 0.08 | `config/trends/eu-russia.yaml` | Approve | `s5una` | `2026-02-18` | `Approved in baseline prior sign-off.` |
| `fertility-decline` | Fertility Decline Acceleration | 0.35 | `config/trends/fertility-decline-acceleration.yaml` | Approve | `s5una` | `2026-02-18` | `Approved in baseline prior sign-off.` |
| `global-infectious-threat` | Emergence of Globally Significant Infectious Threats | 0.12 | `config/trends/global-infectious-threat-emergence.yaml` | Approve | `s5una` | `2026-02-18` | `Approved in baseline prior sign-off.` |
| `normative-deviance-normalization` | Normalization of Extreme Taboo Violations in Public Discourse | 0.10 | `config/trends/normative-deviance-normalization.yaml` | Approve | `s5una` | `2026-02-18` | `Approved in baseline prior sign-off.` |
| `parallel-enclaves-europe` | Parallel Governance Zones in Europe | 0.12 | `config/trends/parallel-enclaves-europe.yaml` | Approve | `s5una` | `2026-02-18` | `Approved in baseline prior sign-off.` |
| `protein-transition` | Protein Transition from Traditional Meat to Alternatives | 0.14 | `config/trends/protein-transition-alternative-sources.yaml` | Approve | `s5una` | `2026-02-18` | `Approved in baseline prior sign-off.` |
| `russia-turkey` | Russia-Turkey Direct Conflict Escalation | 0.05 | `config/trends/russia-turkey-conflict-escalation.yaml` | Approve | `s5una` | `2026-02-18` | `Approved in baseline prior sign-off.` |
| `south-america-agri-supply-shift` | South America Strengthening Global Food Supply Leadership | 0.33 | `config/trends/south-america-agri-supply-shift.yaml` | Approve | `s5una` | `2026-02-18` | `Approved in baseline prior sign-off.` |
| `three-seas-bloc-consolidation` | Three Seas Bloc Consolidation | 0.14 | `config/trends/three-seas-bloc-consolidation.yaml` | Approve | `s5una` | `2026-02-18` | `Approved in baseline prior sign-off.` |
| `ukraine-security-frontier-model` | Ukraine as a Long-Horizon Militarized Frontier | 0.40 | `config/trends/ukraine-security-frontier-model.yaml` | Approve | `s5una` | `2026-02-18` | `Approved in baseline prior sign-off.` |
| `us-china` | US-China Direct War Escalation | 0.09 | `config/trends/us-china-war-escalation.yaml` | Approve | `s5una` | `2026-02-18` | `Approved in baseline prior sign-off.` |
| `us-internal` | US Internal Armed Conflict Risk | 0.05 | `config/trends/us-internal-armed-conflict-risk.yaml` | Approve | `s5una` | `2026-02-18` | `Approved in baseline prior sign-off.` |

## Human Review Gate Checklist

- [x] Confirm each active trend baseline prior is defensible for current horizon.
- [x] Confirm adjusted priors (if any) are applied via API/config with rationale.
- [x] Confirm each reviewed trend has reviewer/date stamped in the table above.
- [x] Confirm non-approved rows have explicit follow-up task IDs recorded.
- [x] Confirm final reviewer sign-off fields are completed below.

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

Execution note (2026-02-18):
- Attempted runtime query via `uv run --no-sync python` + `async_session_maker`.
- Local environment DB auth failed: `asyncpg.exceptions.InvalidPasswordError` for user `postgres`.
- Reviewer approved all baselines; DB parity check execution is deferred/waived for this local environment.

## Final Task-Level Sign-Off

- Reviewer name: `s5una`
- Review date: `2026-02-18`
- Decision: `Approved` (`Approved` / `Blocked`)
- Blocking issues (if any): `None`
- Notes for sprint record: `All active trend baseline priors approved by human review. Runtime DB parity query could not run locally due postgres credential mismatch; review accepted with local-env verification waiver.`

## Sprint Note Snippet (copy after review)

`TASK-070` reviewer sign-off: Reviewer=`<name>`; Date=`<YYYY-MM-DD>`; Decision=`<Approved|Blocked>`; Notes=`<short rationale>`.
