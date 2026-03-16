# TASK-200: Add authorization boundaries for privileged API mutations

## Status

- Owner: Codex
- Started: 2026-03-16
- Current state: In progress
- Planning Gates: Required — security-sensitive API policy owner touching multiple route modules and tests

## Goal (1-3 lines)

Centralize privileged-route authorization so authenticated non-admin API keys
cannot perform control or mutation actions that should be reserved for admin
operators. Reuse one explicit policy across runtime routes instead of route-local
special cases.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` → `TASK-200`
- Runtime/code touchpoints: `src/api/middleware/auth.py`, `src/api/routes/auth.py`, `src/api/routes/sources.py`, `src/api/routes/trends.py`, `src/api/routes/feedback.py`, `tests/unit/api/`, `docs/API.md`, `docs/DEPLOYMENT.md`
- Preconditions/dependencies: current runtime already authenticates `X-API-Key`; existing admin header (`X-Admin-API-Key`) is already used for key-management routes and is the smallest safe privilege boundary to generalize

## Outputs

- Expected behavior/artifacts:
  - shared privileged-route guard with consistent `403` failures and denied-action audit logs
  - privileged guard applied to source CRUD, trend create/sync/update/delete/outcome, feedback mutation routes, and auth key-management routes
  - updated API/deployment docs describing the privilege boundary
- Validation evidence:
  - unit coverage for allowed privileged requests and denied valid non-admin requests
  - local gate output for touched tests/docs/checks

## Non-Goals

- Explicitly excluded work:
  - redesigning API keys into stored role-bearing principals
  - changing admin-secret storage/file-permission policy from `TASK-190`
  - restricting read-only routes or health/metrics exposure beyond this task's route set

## Scope

- In scope:
  - one shared helper for privileged authorization and structured audit logging
  - consistent route wiring for privileged mutation/control endpoints in listed API modules
  - docs and tests for least-privilege behavior
- Out of scope:
  - new database schema
  - unrelated route families not owned by this task backlog entry

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - reuse the existing `X-Admin-API-Key` as the privileged credential and centralize enforcement in shared code so regular `X-API-Key` auth remains the baseline and privileged routes add one fail-closed admin gate
- Rejected simpler alternative:
  - leaving admin checks route-local or duplicating header checks in each module would preserve the current drift and fail the "policy owner" requirement
- First integration proof:
  - auth key-management routes and new privileged mutation routes all exercise the same helper in unit tests
- Waivers:
  - none

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement shared privileged authorization helper and route wiring
3. Validate with focused unit tests, then repo gates
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-16: Use the existing admin header as the canonical privileged-route boundary for this task. Reason: it is already documented, already deployed for key management, and is the lowest-risk way to close the least-privilege gap without inventing a new runtime key model.
- 2026-03-16: Treat mutation/control endpoints in `sources`, `trends`, and `feedback` as privileged, while leaving read-only and non-persistent simulation routes on baseline API-key auth. Reason: this matches the backlog acceptance criteria and avoids over-restricting read paths.

## Risks / Foot-guns

- Missing one mutating endpoint would leave an inconsistent privilege surface -> enumerate every route in touched modules and protect all state-changing handlers
- Shared helper refactor could regress key-management behavior -> keep existing auth route tests and add unaffected-caller regression coverage
- Docs drift could leave operators using the wrong header combination -> update API and deployment docs in the same change

## Validation Commands

- `uv run --no-sync horadus tasks safe-start TASK-200 --name privileged-api-auth`
- `uv run pytest tests/unit/api/test_auth.py tests/unit/api/test_sources.py tests/unit/api/test_trends.py tests/unit/api/test_feedback.py`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: backlog-only task (`tasks/BACKLOG.md`)
- Relevant modules: `src/api/middleware/auth.py`, `src/api/routes/auth.py`, `src/api/routes/sources.py`, `src/api/routes/trends.py`, `src/api/routes/feedback.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
