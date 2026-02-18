# TASK-085 Require Explicit Admin Key Checklist

Date: 2026-02-18  
Branch: `codex/task-085-explicit-admin-key-requirement`  
Task: `TASK-085` Require Explicit Admin Key for Key Management `[REQUIRES_HUMAN]`

## Purpose

Confirm key-management endpoints require explicit admin credentials with no
authenticated-user fallback, and ensure tests/docs cover authorized,
unauthorized, and misconfigured scenarios.

## Initial Baseline Assessment

- Runtime enforcement appears present in `src/api/routes/auth.py`:
  - missing configured admin key -> `403` ("Admin API key is not configured")
  - missing/invalid admin header -> `403` ("Admin API key required")
- Existing tests in `tests/unit/api/test_auth.py` already cover:
  - authorized admin path
  - denied admin access path
  - misconfigured admin key path
- Auth/deployment docs already mention explicit admin-key requirement:
  - `docs/API.md`
  - `docs/ENVIRONMENT.md`
  - `docs/DEPLOYMENT.md`

## Manual Implementation Checklist

- [x] Remove fallback that grants admin access from any authenticated API key when `API_ADMIN_KEY` is unset
- [x] Require explicit admin credential configuration for key-management operations
- [x] Return clear 403/configuration errors when admin key is missing or invalid
- [x] Add/adjust endpoint tests for authorized, unauthorized, and misconfigured admin scenarios
- [x] Update auth/deployment docs with explicit admin-key requirements

## Candidate Gap To Confirm During Human Review

- [x] Add explicit test assertion for invalid `X-Admin-API-Key` value path (distinct from missing-header denial)

## Validation Evidence

- Runtime/admin enforcement:
  - `src/api/routes/auth.py`
- Tests:
  - `tests/unit/api/test_auth.py` (includes explicit invalid-header denial path)
- Docs:
  - `docs/API.md`
  - `docs/ENVIRONMENT.md`
  - `docs/DEPLOYMENT.md`

Validation commands run:

```bash
uv run --no-sync pytest tests/unit/api/test_auth.py -q
uv run --no-sync ruff check src/ tests/
uv run --no-sync mypy src/
```

## Final Task-Level Sign-Off

- Reviewer name: `TBD`
- Review date: `TBD`
- Decision: `Pending` (`Approved` / `Blocked`)
- Blocking issues (if any): `TBD`
- Notes for sprint record: `TBD`
