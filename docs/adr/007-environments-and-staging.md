# ADR-007: Environment Semantics and Staging as Production-Like

**Status**: Accepted  
**Date**: 2026-02-19  
**Deciders**: Architecture review

## Context

Horadus already exposes `ENVIRONMENT`, but runtime behavior previously treated
only `ENVIRONMENT=production` as strict while docs mentioned staging. That
created a foot-gun: `ENVIRONMENT=staging` could silently bypass security and
operational guardrails intended for deployed systems.

The project needs a clear, simple environment model that preserves local
developer speed and keeps pre-production behavior close to production.

## Decision

Constrain `ENVIRONMENT` to three explicit values:

- `development`
- `staging`
- `production`

Unknown values fail fast at startup.

Define a computed runtime concept: `is_production_like`.

- `True` for `staging` and `production`
- `False` for `development`

Use production-like behavior for:

- startup security guardrails (auth posture, secret quality, admin key)
- deployed runtime defaults (for example pooled DB connections)

Keep development ergonomics:

- `NullPool` DB behavior for easier local debugging
- permissive local defaults where appropriate (for example reload/auth toggles)

## Consequences

### Positive

- staging now mirrors production safety posture
- invalid environment values are caught immediately
- fewer deployment surprises between rehearsal and production

### Negative

- staging now requires explicit auth/secrets setup, adding initial setup effort

### Neutral

- production behavior remains unchanged; staging catches up to it

## Alternatives Considered

### Alternative 1: Keep current behavior (production-only strictness)

- Pros: zero migration cost for existing staging setups
- Cons: staging is not a trustworthy promotion gate
- Why rejected: preserves a known safety gap

### Alternative 2: Add separate guardrail toggles per feature

- Pros: highly configurable posture
- Cons: configuration sprawl and higher operator error risk
- Why rejected: unnecessary complexity for project scale

## References

- `src/core/config.py`
- `src/storage/database.py`
- `docs/ENVIRONMENT.md`
- `docs/DEPLOYMENT.md`
- `.env.staging.example`
