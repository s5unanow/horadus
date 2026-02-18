# TASK-084 Production Security Default Guardrails Checklist

Date: 2026-02-18  
Branch: `codex/task-084-prod-security-default-guardrails`  
Task: `TASK-084` Production Security Default Guardrails `[REQUIRES_HUMAN]`

## Purpose

Tighten production startup safety checks so insecure runtime defaults are rejected
early while preserving ergonomic local development behavior.

## Manual Implementation Checklist

- [x] Add production-mode validation that rejects known insecure defaults (for example weak `SECRET_KEY`)
- [x] Add production-mode validation/policy for API auth enablement expectations
- [x] Keep local development defaults ergonomic without weakening production safeguards
- [x] Add tests for production config validation pass/fail paths
- [x] Update environment/deployment docs with explicit production-safe defaults

## Implementation Evidence

- `src/core/config.py`
  - Added production secret guardrails:
    - reject known weak values (`changeme`, `password`, etc.)
    - reject short secrets (`< 32` chars)
  - Existing production auth guardrails preserved:
    - require `API_AUTH_ENABLED=true`
    - require bootstrap key source (`API_KEY`/`API_KEYS` or `API_KEYS_PERSIST_PATH`)
    - require explicit `API_ADMIN_KEY`
- `tests/unit/core/test_config.py`
  - Added fail-path tests for short/weak production `SECRET_KEY`
  - Added pass-path test for persisted key-store bootstrap mode
- Docs updated:
  - `docs/ENVIRONMENT.md`
  - `docs/DEPLOYMENT.md`
  - `.env.example`

## Validation Commands

```bash
uv run --no-sync pytest tests/unit/core/test_config.py -q
uv run --no-sync pytest tests/unit/core -q
uv run --no-sync ruff check src/ tests/
uv run --no-sync mypy src/
```

## Final Task-Level Sign-Off

- Reviewer name: `s5una`
- Review date: `2026-02-18`
- Decision: `Approved` (`Approved` / `Blocked`)
- Blocking issues (if any): `None`
- Notes for sprint record: `Production security startup guardrails hardened for secret quality and auth policy; checks passed.`
