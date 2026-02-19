# TASK-161: Formalize environment semantics (dev/staging/prod) and defaults

## Summary

Horadus already uses `ENVIRONMENT` (and production guardrails) but the semantics
are not fully specified end-to-end:

- `ENVIRONMENT` description mentions `staging`, but code currently treats only
  `ENVIRONMENT=production` as “production” (`is_production`).
- This creates a foot-gun where `ENVIRONMENT=staging` unintentionally bypasses
  production-like guardrails and safety defaults.

This task formalizes `ENVIRONMENT` values and defines a clear “production-like”
concept used for guardrails and runtime defaults.

## Goals

- Make environment semantics explicit and validated.
- Treat `staging` as production-like (guardrails apply, safe defaults apply).
- Keep local development ergonomic (debug-friendly DB settings, reload, etc.).
- Document the intended behavior and provide concrete run instructions and a
  staging example.
- Capture the decision in an ADR (why staging exists for this project).

## Non-goals

- Introducing a full multi-environment deployment system (Terraform/Helm/etc.).
- Adding “agent” as a deployment environment (handled in TASK-162 as a runtime
  profile, separate from `ENVIRONMENT`).

## Proposed Design

### Environment values

Constrain `ENVIRONMENT` to:

- `development`
- `staging`
- `production`

Invalid values should fail fast with an actionable error message.

### Production-like concept

Add a computed property like `settings.is_production_like`:

- `True` for `staging` and `production`
- `False` for `development`

Use it for:

- Production security guardrails and startup validation
- Runtime defaults that should match “deployed” posture (DB pooling, logging
  defaults if applicable)

### DB engine behavior

Current behavior:

- `development` uses `NullPool` (debug-friendly)
- everything else uses pooling

Ensure that `staging` is treated as pooled (production-like).

### Docs / Examples

- Update `docs/ENVIRONMENT.md` to explicitly define `development`, `staging`,
  `production`, and “production-like”.
- Add an ADR: `docs/adr/007-environments-and-staging.md` describing:
  - boundaries for each environment
  - what must be identical between staging/prod (guardrails, auth posture)
  - why the repo includes staging (learning + safer promotion gates)
- Add a minimal `.env.staging.example` (or equivalent documentation snippet)
  that shows a realistic staging configuration (auth on, explicit secret key,
  file-based secrets encouraged).
- Ensure `docs/DEPLOYMENT.md` references staging as a recommended pre-prod check
  path (migrations + auth + rate limits + budgets).

## Acceptance Criteria (Detailed)

- `ENVIRONMENT` rejects unknown values with a clear error.
- `staging` is production-like for guardrails (no bypass).
- DB engine uses pooled connections for staging.
- Docs describe dev/staging/prod boundaries and how to run each.
- ADR records why staging exists and what it is for.
- Unit tests cover:
  - validation of allowed values
  - staging triggering production-like guardrails
  - development not requiring production-only strict settings

## Test Plan

- Add/extend unit tests under `tests/` that instantiate `Settings` with
  environment overrides (no network calls).
- Add/extend a DB engine config test that checks `NullPool` is used only in
  development.
