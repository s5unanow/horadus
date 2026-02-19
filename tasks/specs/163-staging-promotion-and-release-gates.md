# TASK-163: Staging promotion workflow + release gates (dev → staging → prod)

## Summary

Staging exists in this project primarily for learning/practice and for reducing
operator risk when promoting changes to production. This task defines a clear,
repeatable promotion workflow and standardizes “release gates” into one command
path.

The repo already has a release runbook (`docs/RELEASING.md`) and multiple gate
commands; the goal here is to make staging promotion explicit, align
documentation, and provide a single operator-facing command that executes the
expected gates.

## Goals

- Document dev → staging → prod promotion with clear boundaries.
- Make staging feel production-like where it matters (guardrails, auth posture,
  migrations) while keeping it clearly isolated (separate DB/Redis/data).
- Provide a single “release gate” command (`make release-gate`) that runs the
  documented pre-release checks.

## Non-goals

- Creating a full CI/CD pipeline or hosted staging infrastructure.
- Introducing a new deployment stack (Kubernetes/Helm/etc.).
- Adding “agent” as an environment (handled by TASK-162 as a runtime profile).

## Proposed Design

### Promotion semantics

Define a simple promotion contract:

- **Dev**: fastest iteration; may use relaxed defaults; local-only.
- **Staging**: production-like settings and guardrails; isolated infrastructure;
  used to rehearse rollout steps and run smoke checks.
- **Prod**: actual deployment environment; strictest operational posture.

Explicitly document what must be identical between staging and prod:

- `ENVIRONMENT` is production-like (`staging`/`production`)
- auth posture (keys + rate limits) and secret handling expectations
- migration handling workflow

### Operator command: release gate

Add `make release-gate` that runs:

- `make check`
- `make test`
- `make docs-freshness`
- migration gate command(s) against an explicit target DB URL
- optional eval audit gates (when prompt/model changes are included)

The command must be deterministic and safe by default (fail-closed).

### Docs alignment

Update:

- `docs/RELEASING.md`: add explicit “Promotion via staging” section.
- `docs/DEPLOYMENT.md`: add staging rollout instructions and how staging differs
  from production (ports, secrets, DB name, compose project name, etc.).
- `docs/ENVIRONMENT.md`: cross-link to staging and release promotion guidance.
- `README.md`: ensure links remain correct and staging entry points are easy to
  find.

## Acceptance Criteria (Detailed)

- `docs/RELEASING.md` includes a clear dev → staging → prod workflow that is
  runnable by a single operator.
- `make release-gate` exists and is referenced from `docs/RELEASING.md`.
- Staging rollout and verification steps are documented and mirror production
  where practical.
- Docs cross-link cleanly and pass docs freshness checks.

## Test Plan

- If `make release-gate` is added, ensure it is covered by at least a basic
  Makefile target sanity check (if such tests exist) or by documentation
  verification via `scripts/check_docs_freshness.py`.
- No tests should introduce external network calls.
