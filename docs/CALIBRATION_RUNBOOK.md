# Calibration Operations Runbook

This runbook defines operator response for calibration drift and coverage alerts.

## Inputs and Signals

Primary source:

- `GET /api/v1/reports/calibration`

Key fields:

- `drift_alerts`: thresholded drift/coverage alerts
- `coverage`: resolved sample guardrails and low-sample trend list
- `brier_score_over_time`: week-over-week calibration movement
- `trend_movements`: current trend probabilities and weekly deltas

Supporting signals:

- Dashboard export artifacts (`make export-dashboard`)
- API logs for webhook delivery failures (`CALIBRATION_DRIFT_WEBHOOK_URL`)

## Triage Playbook

1. **Capture context**
   - Pull current calibration report for the active window.
   - Snapshot alert payload, sample sizes, and impacted trend IDs/names.
2. **Classify severity**
   - `critical`: immediate incident handling (same day).
   - `warning`: schedule remediation in weekly calibration review.
3. **Check coverage first**
   - If coverage guardrails fail, treat drift metrics as low-confidence and prioritize outcome collection.
4. **Assess drift scope**
   - Single trend/bucket only: targeted remediation.
   - Multi-trend broad drift: systemic remediation.
5. **Take remediation action**
   - Choose path from decision tree below.
   - Record owner, ETA, and expected metric delta.
6. **Verify recovery**
   - Re-check calibration report after new outcomes/evidence are processed.
   - Close incident only after alert clears or mitigation is accepted.

## Weekly Calibration Checklist

Run once per week (or daily when active incidents exist):

1. Export latest dashboard (`make export-dashboard`).
2. Review `drift_alerts` for new/ongoing warnings and criticals.
3. Confirm `coverage.coverage_sufficient` and inspect `low_sample_trends`.
4. Compare `brier_score_over_time` against prior week.
5. Review top mover trends for calibration mismatch patterns.
6. Confirm webhook delivery health from API logs and retry/failure counts.
7. File action items for unresolved drift/coverage issues with owner + due date.

## Remediation Decision Tree

Use this flow to choose response path:

```text
Alert raised?
  ├─ No → Continue weekly checklist only
  └─ Yes
      ├─ Coverage insufficient?
      │   ├─ Yes → Prioritize outcome labeling + defer threshold tuning
      │   └─ No
      ├─ Mean Brier drift?
      │   ├─ Yes → Audit trend evidence weighting and novelty/severity assumptions
      │   └─ No
      ├─ Bucket error drift?
      │   ├─ Yes → Inspect specific probability bucket behavior and trend mix
      │   └─ No
      └─ Persistent >2 review cycles?
          ├─ Yes → Escalate to model/prompt recalibration plan
          └─ No → Continue monitored mitigation
```

## Remediation Reference Actions

- **Coverage gap**: increase outcome capture throughput for low-sample trends.
- **Brier drift**: re-evaluate indicator weights and source-credibility multipliers.
- **Bucket drift**: audit over/under-confidence by probability band.
- **Persistent drift**: schedule prompt and extraction quality review with rollback criteria.

## Exit Criteria

An alert can be closed when all are true:

- Relevant drift/coverage alert is absent for the active window.
- Coverage guardrails meet configured thresholds.
- Remediation notes are recorded in sprint/task tracking artifacts.
