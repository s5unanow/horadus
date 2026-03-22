# TASK-341: Harden Mutable API Write Contracts with Revision Tokens, Idempotency, and Durable Audit Records

## Status

- Owner: Codex
- Started: 2026-03-22
- Current state: In progress
- Planning Gates: Required - migration scope, privileged API write-contract changes, and material edits to allowlisted Python files

## Goal (1-3 lines)

Add one consistent privileged-write contract for the API so replayed writes are
deterministically rejected, stale updates fail closed on revision-sensitive
resources, and durable audit rows explain who tried to change what and what happened.

## Inputs

- Spec/backlog references: `tasks/CURRENT_SPRINT.md`, `tasks/BACKLOG.md#task-341`
- Runtime/code touchpoints: `src/api/routes/trends.py`, `src/api/routes/feedback.py`, `src/api/routes/auth.py`, `src/api/middleware/auth.py`, `src/api/routes/events.py`, `src/api/routes/trend_api_models.py`, `src/api/routes/feedback_models.py`, `src/storage/models.py`, `src/storage/restatement_models.py`, `alembic/versions/`, `docs/API.md`, `tests/unit/api/`, `tests/integration/`
- Preconditions/dependencies: clean synced `main`, passed `horadus tasks preflight`, task branch created with `safe-start`, existing auth + restatement lineage remain canonical

## Outputs

- Expected behavior/artifacts:
  - shared privileged-write helper that enforces `X-Idempotency-Key` for targeted privileged mutations and `If-Match` for revision-sensitive ones
  - durable write-audit persistence that captures actor metadata, target, request intent, outcome, revision basis, and linkage ids where applicable
  - revision tokens surfaced on read/write responses for trend, event, and taxonomy-gap resources that participate in stale-write protection
  - docs/API contract matrix describing which endpoints require idempotency only vs idempotency plus revision tokens
  - migration for the audit/idempotency persistence surface
- Validation evidence:
  - targeted unit/integration coverage for duplicate submission rejection, stale-write rejection, and audit-row creation across at least one trend write and one feedback write path
  - `make agent-check`
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Explicitly excluded work:
  - redesigning source-management writes or unrelated non-privileged endpoints
  - returning cached prior success payloads for duplicate idempotency keys
  - replacing existing structured auth logs as the observability surface
  - broad event API redesign beyond exposing revision tokens needed for the write contract

## Scope

- In scope:
  - define one documented privileged-write header contract
  - enforce deterministic duplicate rejection and stale-write rejection on the task-owned trend/feedback/auth surfaces
  - persist durable audit rows with linkage to created feedback/restatement/trend-version artifacts when present
  - extract helper logic so `trends.py` and `feedback.py` do not absorb another large subsystem
- Out of scope:
  - applying the contract to every mutable route in the repository in this task
  - cross-service distributed idempotency semantics outside the Horadus API database
  - changing the underlying trend-restatement or API-key manager business rules except where needed to capture audit metadata

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - use a single self-contained durable audit/idempotency table plus helper module so duplicate detection and audit persistence share the same canonical record instead of adding parallel stores
- Rejected simpler alternative:
  - relying on transient logs or in-memory request tracking would not survive retries/restarts and would fail the durable audit and deterministic replay acceptance criteria
- First integration proof:
  - a privileged trend update with a reused idempotency key is rejected deterministically, and an event feedback write with a stale revision token fails closed while still leaving an audit row
- Waivers:
  - none

## Plan (Keep Updated)

1. Preflight (branch, context, exec plan)
2. Implement shared write-contract persistence/helper and revision-token helpers
3. Wire trends, feedback, auth, and minimal read-surface responses to the contract
4. Validate targeted tests + `make agent-check` + local gate
5. Ship (ledger updates, `horadus tasks finish TASK-341`)

## Decisions (Timestamped)

- 2026-03-22: Use one durable audit/idempotency table instead of separate idempotency and audit stores so replay detection and operator audit stay mechanically linked.
- 2026-03-22: Keep duplicate behavior as deterministic rejection rather than replaying prior success bodies because the acceptance criteria require rejection, not response caching.
- 2026-03-22: Surface revision tokens as explicit response fields instead of hidden server-only hashes so clients have a straightforward read-then-write contract.

## Risks / Foot-guns

- Route-level boilerplate can sprawl across already-large files -> extract guard/helper logic into dedicated modules and keep route changes thin
- Success audit rows could drift from linked ids if linkage is inferred inconsistently -> centralize result-link payload construction in the shared helper call sites
- Revision tokens can silently fail to rotate on some mutations -> derive them from the mutable state that actually changes and add regression tests on the protected write paths
- Duplicate-key handling can misclassify mismatched payloads -> fingerprint canonical request intent and reject conflicting key reuse separately from pure replay

## Validation Commands

- `pytest tests/unit/api/test_trends.py tests/unit/api/test_feedback.py tests/unit/api/test_auth.py tests/unit/api/test_events.py`
- `pytest tests/integration/test_feedback_invalidation.py tests/integration/test_events_api.py`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: backlog-only task
- Relevant modules: `src/api/routes/trends.py`, `src/api/routes/feedback.py`, `src/api/routes/auth.py`, `src/api/routes/events.py`, `src/storage/restatement_models.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
