# TASK-199: Harden trend config sync against write-on-read and arbitrary path access

## Status

- Owner: Codex
- Started: 2026-03-16
- Current state: In progress
- Planning Gates: Required — security-sensitive API hardening that touches an allowlisted oversized route module

## Goal (1-3 lines)

Remove state-changing behavior from the trends read route and constrain config
sync to explicit privileged access plus a repo-owned config root. The sync path
must fail closed on arbitrary paths, traversal, and filesystem escape cases.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` → `TASK-199`
- Runtime/code touchpoints: `src/api/routes/trends.py`, `src/api/routes/trend_route_auth.py`, `src/core/trend_config.py`, `tests/unit/api/test_trends.py`, `docs/API.md`
- Preconditions/dependencies: reuse the shared privileged-route model introduced by `TASK-200`; preserve current trend config YAML semantics outside the sync-entry hardening

## Outputs

- Expected behavior/artifacts:
  - `GET /api/v1/trends` no longer performs config-sync writes when clients pass `sync_from_config`
  - config sync rejects arbitrary directories and resolves only within the repo-owned trend config root
  - sync execution stays behind the canonical privileged-route authorization path
  - docs and tests describe the tightened sync contract
- Validation evidence:
  - targeted unit coverage for rejected GET sync attempts, rejected path traversal/symlink escape cases, and privileged sync authorization
  - fast repo gate plus full local gate after implementation

## Non-Goals

- Explicitly excluded work:
  - redesigning the trend YAML schema or loader format
  - changing unrelated trend CRUD semantics beyond the sync entrypoints
  - adding new per-key roles beyond the existing admin-header privileged boundary

## Scope

- In scope:
  - route-level removal or rejection of `sync_from_config` write behavior on `GET /api/v1/trends`
  - deterministic path validation for sync requests against an allowlisted repo-owned root
  - regression tests and API docs for the hardened behavior
- Out of scope:
  - migrations or database model changes
  - broader config-loader refactors unless needed to isolate the path guard cleanly

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - keep config sync as an explicit privileged mutation endpoint and validate requested paths through a shared helper that resolves against the canonical trend-config root before any YAML reads occur
- Rejected simpler alternative:
  - keeping write-on-read with stronger auth would still violate safe REST semantics and leave an avoidable mutation trigger on a read route
- First integration proof:
  - unit tests should show `GET /api/v1/trends` remains read-only while privileged sync still works for files inside the repo-owned config directory
- Waivers:
  - none

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement GET-route hardening and config-root path validation
3. Validate with focused trend API tests and repo gates
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-16: Reuse the `TASK-200` privileged-route helper for config sync instead of adding route-local auth checks. Reason: this keeps one canonical admin boundary for privileged mutations.
- 2026-03-16: Treat the repo-owned trend config directory as the only valid sync root and reject any resolved path outside it, including traversal and symlink escape. Reason: the API should never grant arbitrary server-local file access.

## Risks / Foot-guns

- Path validation that only checks strings could miss symlink escapes -> resolve real paths and compare against the canonical root before reading
- Removing the GET-side effect could silently break callers depending on it -> reject the parameter explicitly or ignore it with clear tests/docs so the new contract is visible
- Touching `src/api/routes/trends.py` could grow the allowlisted hotspot -> extract the new path-guard logic into a smaller owned helper if needed and avoid inflating the route module

## Validation Commands

- `uv run --no-sync horadus tasks safe-start TASK-199 --name trend-config-sync-hardening`
- `uv run --no-sync horadus tasks context-pack TASK-199`
- `uv run pytest tests/unit/api/test_trends.py`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: backlog-only task (`tasks/BACKLOG.md`)
- Relevant modules: `src/api/routes/trends.py`, `src/api/routes/trend_route_auth.py`, `src/core/trend_config.py`, `tests/unit/api/test_trends.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
