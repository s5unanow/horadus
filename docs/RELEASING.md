# Release Process Runbook

**Last Verified**: 2026-02-19

This runbook defines the standard release workflow for Horadus.

Goals:
- Keep releases reproducible and low-risk.
- Ensure quality gates run before shipping.
- Make rollback predictable when issues appear.

## Promotion Workflow (Dev -> Staging -> Prod)

Use the same commit SHA through each promotion step.

1. **Dev**
   - implement on task branch and merge to `main` with required CI green.
   - keep `ENVIRONMENT=development` and fast local iteration defaults.
2. **Staging**
   - deploy merged `main` commit to isolated staging infra/data first.
   - use production-like posture (`ENVIRONMENT=staging`, auth enabled, explicit
     secrets, migration parity checks).
   - run release gates and staging smoke checks before promotion.
3. **Prod**
   - deploy the same commit already validated in staging.
   - run production post-deploy checks and monitor early runtime signals.

Staging/prod must match on:
- auth posture (`API_AUTH_ENABLED`, API/admin key handling, rate limits)
- secret handling policy (`*_FILE`-first in deployed environments)
- migration workflow (`db-migration-gate` strict by default)

Staging/prod must differ on:
- isolated DB/Redis/data (no shared state)
- hostnames/TLS endpoints and compose project naming
- external exposure policy (staging may be more restricted)

## Canonical Gate Command

Use one command path for release gating:

```bash
make release-gate RELEASE_GATE_DATABASE_URL="<target-db-url>"
```

What it runs (fail-closed, in order):
- `make check`
- `make test`
- `make docs-freshness`
- `make db-migration-gate MIGRATION_GATE_DATABASE_URL="<target-db-url>"`

Optional prompt/model gate:

```bash
make release-gate RELEASE_GATE_DATABASE_URL="<target-db-url>" RELEASE_GATE_INCLUDE_EVAL=true
```

This additionally runs `make audit-eval`.

## Mandatory Task Delivery Workflow (Hard Rule)

For any engineering change (including docs/process changes):

1. Start from updated `main`:
```bash
git switch main
git pull --ff-only
```
2. Run task-start preflight (clean/synced `main`, no open task PR):
```bash
make task-preflight
```
3. Create/confirm a `TASK-XXX` and open a dedicated branch from `main`:
```bash
make task-start TASK=XXX NAME=short-name
```
4. Keep branch scope to one task only; open one PR for that task.
5. Include canonical PR metadata field in body:
```text
Primary-Task: TASK-XXX
```
6. Merge only when all required checks are green.
7. Delete merged branch.
8. Return to `main`, sync, and verify merge commit exists locally:
```bash
git switch main
git pull --ff-only
git log --oneline -n 1
```

If unrelated work is discovered during implementation:
- Create a new follow-up task immediately.
- Do **not** switch branches by default.
- Continue current task unless the new work is blocker/urgent.
- Never mix two tasks in one commit/PR.

## Repository Guardrails (Required)

- `main` is protected with PR-required merge flow.
- Required checks must pass before merge.
- Admins are also enforced by branch protection.
- Direct push to `main` is blocked by protection settings.
- Linear history is required; merge commits are disabled at repo level (squash/rebase path).
- One task = one branch = one PR is non-negotiable.

Automation:
- Local hook guard install:
```bash
make hooks
```
- Manual branch guard check:
```bash
make branch-guard
```
- Mandatory task-start sequencing guard:
```bash
make task-preflight
make task-start TASK=XXX NAME=short-name
```
- Apply/refresh GitHub `main` protection defaults:
```bash
make protect-main
```

## Release Scope and Cadence

- Use semantic version tags: `vMAJOR.MINOR.PATCH`.
- Prefer small, focused releases over large bundled drops.
- Every release requires short release notes.

## Roles

- **Release driver**: prepares candidate release, runs gates, coordinates rollout.
- **Reviewer**: validates release notes, gate outputs, and rollout readiness.
- **Operator**: executes production rollout and post-deploy checks.

For personal/single-operator usage, one person may perform all roles, but still follow all steps.

## Pre-Release Checklist

Run from repository root on the release candidate commit:

1. Sync branch and ensure clean working tree:
```bash
git checkout main
git pull --ff-only
git status --short
```

2. Quality gates:
```bash
make release-gate RELEASE_GATE_DATABASE_URL="<target-db-url>"
```

`make db-migration-gate` inside `make release-gate` is strict by default and
runs `alembic check`. Use `MIGRATION_GATE_VALIDATE_AUTOGEN=false` only as a
temporary emergency bypass with explicit documentation in release notes.

3. Evaluation policy gates (prompt/model changes only):
```bash
make audit-eval
```
- If prompt/model changes are included, also run benchmark per `docs/PROMPT_EVAL_POLICY.md`.
- Do not promote prompt/model changes if required evaluation gates fail.

4. Release notes draft:
- Summarize user-visible behavior changes.
- Include operational changes (env vars, migrations, rollout caveats).
- Include risk/rollback notes.

## CI Gate Behavior and Remediation

CI gates are fail-closed for integration and security checks. If a gate fails:

1. **Do not merge** until the failure is resolved or explicitly scoped by config/policy.
2. Reproduce locally with equivalent commands:
```bash
uv run --no-sync alembic upgrade head
DATABASE_URL="<target-db-url>" ./scripts/check_migration_drift.sh
uv run --no-sync pytest tests/integration/ -v -m integration
uv run --no-sync bandit -c pyproject.toml -r src/
uv run --no-sync python scripts/check_docs_freshness.py
```
3. Fix the underlying issue, then rerun quality gates.
4. If a finding is an accepted exception, document rationale in config/docs and keep CI explicit.

### Docs freshness gate remediation

When `scripts/check_docs_freshness.py` fails:

1. Update stale `Last Verified` / `Last Updated` markers and conflicting docs statements.
2. If drift is intentional and temporary, add a scoped override entry in
   `docs/DOCS_FRESHNESS_OVERRIDES.json` with:
   - `rule_id`
   - exact `path`
   - explicit `reason`
   - short-lived `expires_on` date
3. Rerun:
```bash
uv run --no-sync python scripts/check_docs_freshness.py
```
4. Remove overrides once the underlying docs drift is resolved.

## Versioning and Tagging

1. Pick next semantic version:
- `PATCH`: bug fixes/docs/ops tweaks.
- `MINOR`: backward-compatible features.
- `MAJOR`: incompatible changes.

2. Create annotated tag on the release commit:
```bash
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

3. Preserve release notes:
- Add to GitHub release description (or project changelog if maintained).
- Keep notes concise and operationally actionable.

## Rollout Procedure

Use deployment commands from `docs/DEPLOYMENT.md`:

```bash
docker compose -f docker-compose.prod.yml build api worker
docker compose -f docker-compose.prod.yml --profile ops run --rm migrate
docker compose -f docker-compose.prod.yml up -d api worker beat
```

## Post-Deploy Verification

Immediately verify:

1. API health:
```bash
curl -sSf http://localhost:8000/health
```

2. Metrics endpoint:
```bash
curl -sSf http://localhost:8000/metrics | head
```

3. Worker/beat service state:
```bash
docker compose -f docker-compose.prod.yml ps
```

4. Optional smoke checks:
- `uv run --no-sync horadus trends status`
- `make export-dashboard`

## Rollback Criteria

Rollback if any of the following persist after brief triage:
- Health/metrics failures after rollout.
- Migrations break critical API/worker paths.
- Error rate spikes or processing stalls.
- Budget guardrails/failover behavior regresses materially.
- Critical security/reliability findings discovered post-release.

## Rollback Procedure

1. Identify last known good tag/commit.
2. Checkout good revision:
```bash
git checkout <good-tag-or-commit>
```
3. Rebuild and redeploy API/worker/beat:
```bash
docker compose -f docker-compose.prod.yml build api worker
docker compose -f docker-compose.prod.yml up -d api worker beat
```
4. Re-run post-deploy verification.
5. Document incident summary and corrective follow-up tasks.

Staging vs production rollback expectations:
- **Staging**: rollback can prioritize speed and diagnosis; data reset is acceptable
  when isolated and documented.
- **Production**: rollback must preserve data integrity and audit trail; use
  only previously validated release revisions and record operator actions.

## Documentation Freshness

- Update this runbook whenever release gates, rollout commands, or rollback policy changes.
- Update related docs in the same PR:
  - `README.md`
  - `docs/DEPLOYMENT.md`
  - `docs/PROMPT_EVAL_POLICY.md` (if eval gates change)
