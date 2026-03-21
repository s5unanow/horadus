# TASK-339: Version Runtime Provenance for LLM-Derived Artifacts and Scoring Math

## Status

- Owner: Codex
- Started: 2026-03-21
- Current state: In progress
- Planning Gates: Required — migration + multi-surface LLM/scoring contract change

## Goal (1-3 lines)

Add one repo-owned provenance contract for persisted Tier-2 extraction state,
semantic-cache keying/debug basis, trend scoring math versioning, replay
derivation, and generated report manifests so operators can explain drift
between runs without reading code.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` -> `TASK-339`
  - `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints:
  - `src/processing/tier1_classifier.py`
  - `src/processing/tier2_classifier.py`
  - `src/processing/semantic_cache.py`
  - `src/processing/pipeline_orchestrator.py`
  - `src/workers/_task_maintenance.py`
  - `src/core/trend_engine.py`
  - `src/core/trend_restatement.py`
  - `src/core/report_generator.py`
  - `src/api/routes/events.py`
  - `src/api/routes/trends.py`
  - `src/api/routes/reports.py`
  - `src/storage/models.py`
  - `src/storage/restatement_models.py`
  - `alembic/`
- Preconditions/dependencies:
  - Reuse current prompt hashing / request-override normalization patterns where possible.
  - Keep shared oversized modules flat by extracting new helper modules rather than growing hotspots.

## Outputs

- Expected behavior/artifacts:
  - Persist current extraction provenance on events.
  - Persist scoring math version metadata on evidence and restatements.
  - Persist report-generation manifests with pinned input/model/prompt basis.
  - Replay queue and replayed Tier-2 writes carry explicit derivation linkage.
  - Semantic cache keys/debug basis change when prompt/schema/override basis changes.
- Validation evidence:
  - Unit tests for provenance helpers, cache keying, Tier-2 persistence, report manifests, and scoring metadata.
  - Relevant API/unit tests updated for new read surfaces.

## Non-Goals

- Explicitly excluded work:
  - Full live-state version pinning / rebase workflow from `TASK-337`
  - New operator UI or separate cache-inspection API surface
  - Reworking report storage into append-only history in this task

## Scope

- In scope:
  - Compact shared provenance helper module
  - Event extraction provenance persistence and read exposure
  - Replay derivation persistence for held/replayed Tier-2 work
  - Semantic-cache provenance basis alignment
  - Scoring math version + parameter-set persistence/exposure
  - Report generation manifest persistence/exposure
  - Docs for runtime provenance/scoring contract
- Out of scope:
  - Trend activation/version-switch lifecycle
  - Definition-history redesign
  - Non-Tier1/2/Report LLM artifact families

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Add narrow JSONB/string columns on existing persisted artifacts and expose them on existing debug/detail routes.
  - Use one helper module to canonicalize prompt/schema/request-override provenance and scoring-contract metadata.
- Rejected simpler alternative:
  - Logging-only provenance was rejected because it does not satisfy replay/audit comparisons on persisted artifacts.
- First integration proof:
  - Tier-2 event classification persists provenance that matches the semantic-cache basis and changes on prompt/schema/override changes.
- Waivers:
  - Report rows remain update-in-place; manifest will pin the currently stored artifact rather than introducing append-only report versioning here.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement shared runtime-provenance helpers and schema/model changes
3. Wire Tier-1/Tier-2/cache/report/replay/scoring surfaces to the new contract
4. Validate with targeted tests + repo gates
5. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-21: Implement on `TASK-339` first because the repo already has partial prompt/request provenance helpers, making end-to-end delivery feasible without coupling to `TASK-337`.
- 2026-03-21: Keep provenance operator-facing through existing event/trend/report detail APIs instead of adding a dedicated debug endpoint in this task.

## Risks / Foot-guns

- Cache-key contract drift between classifiers and cache helper -> centralize provenance-basis construction in one helper and test signature changes.
- Growing allowlisted hotspot modules further -> extract helper modules and keep route/model edits minimal.
- Replay provenance silently overwritten -> persist original degraded invocation basis in replay queue details and include explicit replay-derivation linkage on replayed event provenance.
- Report manifest bloat -> store bounded ids/counts plus canonical hashes rather than dumping full joined objects.

## Validation Commands

- `pytest tests/unit/processing/test_semantic_cache.py tests/unit/processing/test_tier1_classifier.py tests/unit/processing/test_tier2_classifier.py tests/unit/core/test_trend_engine.py tests/unit/api/test_events.py tests/unit/api/test_reports.py tests/unit/storage/test_model_metadata.py`
- `pytest tests/unit/core/test_report_generator.py tests/unit/core/test_trend_restatement.py tests/unit/workers/test_tasks_additional.py`
- `python scripts/check_code_shape.py`
- `make agent-check`

## Notes / Links

- Spec: `tasks/BACKLOG.md`
- Relevant modules:
  - `src/eval/artifact_provenance.py`
  - `src/processing/llm_policy.py`
  - `src/core/trend_engine.py`
  - `src/core/report_generator.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
