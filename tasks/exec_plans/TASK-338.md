# TASK-338: Separate Provisional and Canonical Extraction State in Degraded Mode

## Status

- Owner: Codex
- Started: 2026-03-23
- Current state: In progress
- Planning Gates: Required — task spans a migration plus multiple runtime surfaces, and it materially touches allowlisted oversized Python modules

## Goal (1-3 lines)

Prevent degraded-mode Tier-2 output from silently overwriting durable event truth.
Persist provisional extraction separately, promote only canonical replay output into
the stable event fields, and surface the status in operator-facing debug responses.

## Inputs

- Spec/backlog references:
  - `tasks/CURRENT_SPRINT.md`
  - `tasks/BACKLOG.md` entry for `TASK-338`
- Runtime/code touchpoints:
  - `src/processing/pipeline_orchestrator.py`
  - `src/processing/tier2_runtime.py`
  - `src/processing/tier2_classifier.py`
  - `src/storage/models.py`
  - `src/storage/event_summary.py`
  - `src/core/report_generator.py`
  - `src/api/routes/events.py`
  - `src/api/routes/reports.py`
  - `src/workers/_task_maintenance.py`
  - `alembic/versions/`
- Preconditions/dependencies:
  - degraded-mode replay remains the only path that can promote held Tier-2 output into trend evidence
  - event lineage replay-pending semantics must continue to work alongside the new provisional/canonical extraction split

## Outputs

- Expected behavior/artifacts:
  - Events persist canonical extraction separately from degraded provisional extraction
  - Degraded runs stop overwriting canonical event/report fields while still storing provisional debug context
  - Replay / healthy Tier-2 writes clear or supersede provisional extraction with explainable provenance
  - Event/report debug responses expose extraction status
  - Alembic migration backfills existing rows safely
- Validation evidence:
  - targeted unit coverage for provisional persistence, replay promotion, summary resolution, and report/event debug payloads
  - `make agent-check`

## Non-Goals

- Explicitly excluded work:
  - redesigning degraded-mode entry/exit policy
  - changing trend delta math or replay queue prioritization
  - broad event API redesign outside the extraction-status/debug surface

## Scope

- In scope:
  - add durable storage for provisional extraction payload/status
  - restore prior canonical fields when the just-produced Tier-2 result must be held as provisional
  - keep normal report/event summary paths canonical-only
  - record promotion/supersession provenance when replay or healthy Tier-2 replaces provisional state
- Out of scope:
  - new operator mutation endpoints for manual promotion/discard
  - archival of full provisional history beyond the bounded provenance trail needed for explainability

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - introduce a bounded provisional-extraction storage surface plus helper functions so the existing canonical fields remain the durable reporting truth
- Rejected simpler alternative:
  - storing only a provisional flag in `extraction_provenance` while continuing to write degraded output into `event_summary` / `categories` still leaks provisional content into normal reads
- First integration proof:
  - degraded pipeline path writes provisional payload and restores canonical fields before any report/event read sees the degraded output as canonical
- Waivers:
  - none

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement provisional storage + restoration/promotion helpers
3. Validate with targeted tests and `make agent-check`
4. Ship (ledger closure, PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-23: Use separate provisional storage instead of reusing canonical event fields because degraded output must remain inspectable without becoming reporting truth.
- 2026-03-23: Keep allowlisted hotspots flat by moving the new extraction-state transitions into focused helper modules rather than deepening the existing large orchestrator/model files.

## Risks / Foot-guns

- Replay or lineage code may still assume `extraction_provenance.status` is the full extraction state -> keep replay-pending semantics intact and add explicit tests for coexistence.
- Report/event readers may accidentally pick provisional fields through old helpers -> centralize summary/status resolution in storage helpers and reuse them everywhere.
- Migration backfill could mislabel existing rows -> backfill conservatively from existing canonical extraction fields and leave empty rows unclassified.

## Validation Commands

- `uv run --no-sync pytest tests/unit/storage/test_event_summary.py`
- `uv run --no-sync pytest tests/unit/processing/test_pipeline_orchestrator_additional.py`
- `uv run --no-sync pytest tests/unit/processing/test_tier2_classifier.py`
- `uv run --no-sync pytest tests/unit/core/test_report_generator.py tests/unit/api/test_events.py tests/unit/api/test_reports.py`
- `make agent-check`

## Notes / Links

- Spec: backlog entry only
- Relevant modules:
  - `src/storage/event_summary.py`
  - `src/processing/tier2_runtime.py`
  - `src/processing/pipeline_orchestrator.py`
  - `src/workers/_task_maintenance.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
