# TASK-207: Use Stable Source Identity Keys for GDELT and Telegram Watermarks

## Status

- Owner: Codex
- Started: 2026-03-25
- Current state: In progress
- Planning Gates: Required — touches allowlisted oversized files (`src/ingestion/gdelt_client.py`, `src/storage/models.py`)

## Goal (1-3 lines)

Preserve GDELT and Telegram source state across harmless display-name renames by keying source lookup on stable provider identity instead of mutable labels. Keep source watermarks, fetch history, and error counters attached to the same logical source.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-207`), `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints: `src/ingestion/gdelt_client.py`, `src/ingestion/telegram_harvester.py`, `src/storage/models.py`, `alembic/versions/`, `tests/unit/ingestion/`, `tests/integration/`, `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`
- Preconditions/dependencies: keep the GDELT fix independently shippable; do not let Telegram launch-scope exclusions stall bounded source-identity hardening already supported by the existing harvester code path

## Outputs

- Expected behavior/artifacts:
  - stable source key persisted on `sources` for GDELT and Telegram
  - migration backfills existing rows so rename-safe lookup preserves current state
  - both collectors reuse stable-key lookup before mutable display-name fallback
- Validation evidence:
  - targeted unit/integration tests covering rename/no-reset behavior for both collectors
  - Python repo gates via `make agent-check`

## Non-Goals

- Explicitly excluded work:
  - changing Telegram launch-scope policy or enabling new Telegram scheduling paths
  - redesigning source CRUD/API contracts beyond exposing the persisted model field
  - changing RSS source identity behavior in this task

## Scope

- In scope:
  - add persisted stable provider key with uniqueness scoped by source type
  - derive GDELT identity from semantic query fingerprint and Telegram identity from normalized channel handle
  - preserve existing rows during migration and collector updates
- Out of scope:
  - automatic deduplication/merging of pre-existing conflicting duplicate rows
  - new operator-facing UI for source identity inspection

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - add `sources.provider_source_key` plus a partial unique index and backfill it during migration
  - keep stable-key derivation in a small shared ingestion helper to avoid growing hotspot files further
  - allow a legacy name fallback only when an old row still lacks the backfilled provider key
- Rejected simpler alternative:
  - config-only lookup without a persisted key would preserve some renames but would not enforce uniqueness or make source identity explicit in the data model/migration state
- First integration proof:
  - rename a configured GDELT query or Telegram channel display name and observe that the collector updates the existing `sources` row instead of creating a new one
- Waivers:
  - none

## Plan (Keep Updated)

1. Preflight (branch, tests, context) ✅
2. Implement schema + shared identity helper + collector lookup updates In progress
3. Validate targeted tests and repo gates Pending
4. Ship (PR, checks, merge, main sync) Pending

## Decisions (Timestamped)

- 2026-03-25: Use a persisted provider key instead of deriving identity only from mutable `config` lookups. (Keeps rename preservation explicit and enforceable in the schema.)
- 2026-03-25: Scope the GDELT fingerprint to semantic query selectors, not fetch/runtime metadata like lookback or page size. (Preserves state across harmless tuning changes while still splitting genuinely different queries.)
- 2026-03-25: Keep Telegram in scope for source-identity hardening because the existing harvester/runtime path already exists and the change is bounded to persistence semantics, not launch enablement. (Avoids deferring a safe correctness fix unnecessarily.)

## Risks / Foot-guns

- Existing duplicate rows could collide under the new stable key -> migration must detect collisions before creating the unique index and fail closed with a clear error.
- Hotspot files are already at the allowlisted size ceiling -> extract new identity logic into a dedicated helper module and keep inline edits minimal.
- A name fallback could accidentally preserve state across a semantic query change -> only reuse legacy rows when they still lack `provider_source_key` and their stored legacy identity matches the new computed key.

## Validation Commands

- `pytest tests/unit/ingestion/test_gdelt_client_additional.py tests/unit/ingestion/test_telegram_harvester.py tests/integration/test_gdelt_client.py tests/integration/test_telegram_harvester.py tests/unit/storage/test_model_metadata.py`
- `make agent-check`
- `uv run --no-sync horadus tasks finish TASK-207`

## Notes / Links

- Spec: backlog-only task
- Relevant modules: `src/ingestion/source_identity.py`, `src/ingestion/gdelt_client.py`, `src/ingestion/telegram_harvester.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
