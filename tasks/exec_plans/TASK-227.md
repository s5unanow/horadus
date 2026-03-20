# TASK-227: Make Corroboration Provenance-Aware Instead of Source-Count-Aware

## Status

- Owner: Codex
- Started: 2026-03-20
- Current state: In progress
- Planning Gates: Required - migration scope, corroboration/event semantics changes, and allowlisted Python files

## Goal (1-3 lines)

Replace raw/distinct-source corroboration with a persisted provenance-aware
independence summary so trend scoring and event confirmation both reason about
likely independent evidence groups instead of outlet count inflation.

## Inputs

- Spec/backlog references: `tasks/CURRENT_SPRINT.md`, `tasks/BACKLOG.md#task-227`
- Runtime/code touchpoints: `src/processing/pipeline_orchestrator.py`, `src/processing/event_clusterer.py`, `src/processing/event_lifecycle.py`, `src/storage/models.py`, `src/storage/event_state.py`, `src/api/routes/events.py`, `src/api/routes/feedback_event_helpers.py`, `src/api/routes/trends.py`, `alembic/versions/`, `tests/`
- Preconditions/dependencies: clean synced `main`, passed `horadus tasks preflight`, task branch created with `safe-start`

## Outputs

- Expected behavior/artifacts:
  - persisted event-level provenance summary with raw counts, independent-group counts, weighted corroboration score, and bounded group metadata
  - provenance-aware corroboration grouping extracted into a dedicated helper/module instead of adding more logic to the orchestrator
  - event confirmation semantics keyed to independent-evidence counts when provenance is present, with conservative fallback to existing unique-source counts otherwise
  - event/debug API surfaces that show raw source counts alongside independent-evidence counts and provenance mode
  - migration/backfill for new event provenance columns
- Validation evidence:
  - unit coverage for provenance grouping heuristics, clusterer persistence, lifecycle confirmation, and API projections
  - targeted integration coverage for event API visibility and provenance-aware corroboration persistence
  - `make agent-check`

## Non-Goals

- Explicitly excluded work:
  - redesigning the broader trend-engine factor formula
  - provider/LLM prompt changes
  - full historical replay/versioning work from `TASK-339` or `TASK-337`
  - open-ended publisher ownership normalization beyond bounded deterministic heuristics

## Scope

- In scope:
  - add event-owned provenance/corroboration columns and backfill
  - deterministic provenance grouping based on source family, syndication/near-duplicate heuristics, and reporting type
  - switch event confirmation and trend corroboration reads to the persisted provenance summary
  - expose raw-vs-independent counts on event-facing surfaces
- Out of scope:
  - introducing network-backed provenance lookups
  - changing trend evidence invalidation/replay contracts beyond consuming the new event semantics
  - replacing existing source credibility dimensions

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - persist provenance on `events` as the shared runtime surface, using integer independent-group counts for confirmation semantics plus a weighted corroboration score for trend math
- Rejected simpler alternative:
  - recalculating transient provenance inside `pipeline_orchestrator` only would keep scoring opaque, leave event confirmation on stale unique-source semantics, and fail the persistence/debug acceptance criteria
- First integration proof:
  - an event made of syndicated or reposted items shows lower independent-evidence counts than raw source counts while genuinely independent sources still confirm the event
- Waivers:
  - none

## Plan (Keep Updated)

1. Preflight (branch, context, exec plan)
2. Implement event provenance schema/helper extraction
3. Wire clusterer, lifecycle, scoring, and API surfaces to the persisted summary
4. Validate targeted tests + `make agent-check`
5. Ship (ledger updates, `horadus tasks finish TASK-227`)

## Decisions (Timestamped)

- 2026-03-20: Persist provenance at the event layer instead of only on evidence rows because both event confirmation and trend scoring need the same shared independence summary.
- 2026-03-20: Keep fail-safe fallback to legacy `unique_source_count` whenever an event lacks usable provenance metadata, so partial backfills or malformed rows do not zero out corroboration.
- 2026-03-20: Extract provenance grouping into a dedicated processing helper to avoid growing the allowlisted orchestrator and clusterer files with another embedded mini-subsystem.

## Risks / Foot-guns

- Publisher-family heuristics can over-collapse unrelated coverage -> keep heuristics bounded, deterministic, and conservative; favor source-specific fallback when ambiguous
- Event confirmation semantics can silently drift from stored counts -> recompute/persist provenance at event creation/merge time and read that persisted count from lifecycle helpers
- API/debug payloads can become noisy -> expose compact counts on list responses and reserve detailed provenance breakdowns for detail/review surfaces
- Allowlisted files can grow further -> prefer helper extraction and remove stale logic from the orchestrator instead of layering new branches onto it

## Validation Commands

- `pytest tests/unit/processing/test_event_clusterer.py tests/unit/processing/test_event_lifecycle.py tests/unit/processing/test_pipeline_orchestrator.py tests/unit/storage/test_event_state.py`
- `pytest tests/unit/api/test_events.py tests/unit/api/test_feedback.py tests/integration/test_events_api.py`
- `make agent-check`

## Notes / Links

- Spec: backlog-only task
- Relevant modules: `src/processing/pipeline_orchestrator.py`, `src/processing/event_clusterer.py`, `src/storage/models.py`, `src/api/routes/events.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
