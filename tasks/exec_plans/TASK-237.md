# TASK-237: Add Dynamic Reliability Diagnostics and Time-Varying Source Credibility

## Status

- Owner: Codex automation
- Started: 2026-03-27
- Current state: In progress
- Planning Gates: Required — task materially changes allowlisted oversized module `src/core/calibration_dashboard.py`

## Goal (1-3 lines)

Add richer advisory reliability diagnostics that segment outcome-linked source behavior by bounded dimensions and expose a conservative recent-vs-baseline advisory credibility signal without mutating configured source credibility automatically.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-237`), `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints: `src/core/calibration_dashboard.py`, `src/core/source_credibility.py`, `src/api/routes/reports.py`, `tests/unit/core/test_calibration_dashboard.py`, `tests/unit/api/test_reports.py`, `docs/ARCHITECTURE.md`
- Preconditions/dependencies: guarded branch start complete on `codex/task-237-dynamic-reliability`; live task definition exists in backlog despite `horadus tasks show/context-pack TASK-237` reporting archived history

## Outputs

- Expected behavior/artifacts:
  - calibration dashboard exposes advisory diagnostics for `source`, `source_tier`, `topic_family`, and `geography`
  - source reliability rows include recent-vs-baseline drift context and a bounded advisory credibility delta that never overrides configured credibility
  - sparse-data handling suppresses advisory deltas and labels low-sample rows clearly
- Validation evidence:
  - targeted unit coverage for stable, drifting, and low-sample diagnostics
  - `make agent-check`
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Explicitly excluded work:
  - changing stored source credibility in the database
  - wiring automated trend math to empirical source adjustments
  - adding new persistence tables or migrations for diagnostics state

## Scope

- In scope:
  - extract diagnostics logic from the dashboard hotspot into a dedicated module
  - add bounded segmentation and advisory signal calculations
  - extend the reports API payload and operator docs for the new diagnostics
- Out of scope:
  - non-dashboard report redesign
  - changing historical calibration/outcome recording semantics

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - keep diagnostics advisory-only in dashboard/report responses and compute recent-vs-baseline drift from existing outcome/evidence data
- Rejected simpler alternative:
  - adding more fields directly inside `src/core/calibration_dashboard.py` would grow an allowlisted hotspot and keep mixed ownership in one file
- First integration proof:
  - targeted unit tests for dashboard diagnostics and reports route
- Waivers:
  - none

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-27: Extract reliability diagnostics into a dedicated core module so the dashboard file shrinks while the task adds new segmentation logic.
- 2026-03-27: Use a conservative recent-vs-baseline advisory delta with explicit suppression on sparse samples instead of mutating configured source credibility.

## Risks / Foot-guns

- Evidence joins may over-associate old source/event context with a trend outcome -> dedupe per dimension/key/outcome and keep the result advisory-only.
- Topic/geography labels can become sparse/noisy -> normalize conservatively and suppress low-sample adjustments.
- API payload growth can break tests or docs -> add route regression coverage and update architecture notes in-branch.

## Validation Commands

- `pytest tests/unit/core/test_calibration_dashboard.py`
- `pytest tests/unit/api/test_reports.py`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: backlog entry only (`tasks/BACKLOG.md`)
- Relevant modules: `src/core/calibration_dashboard.py`, `src/core/source_credibility.py`, `src/api/routes/reports.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
