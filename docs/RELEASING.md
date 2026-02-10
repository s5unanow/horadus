# Release Process Runbook

This runbook defines the standard release workflow for Horadus.

Goals:
- Keep releases reproducible and low-risk.
- Ensure quality gates run before shipping.
- Make rollback predictable when issues appear.

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
make check
make test
```

3. Database migration sanity:
```bash
make db-upgrade
```

4. Evaluation policy gates (prompt/model changes only):
```bash
make audit-eval
```
- If prompt/model changes are included, also run benchmark per `docs/PROMPT_EVAL_POLICY.md`.
- Do not promote prompt/model changes if required evaluation gates fail.

5. Release notes draft:
- Summarize user-visible behavior changes.
- Include operational changes (env vars, migrations, rollout caveats).
- Include risk/rollback notes.

## CI Gate Behavior and Remediation

CI gates are fail-closed for integration and security checks. If a gate fails:

1. **Do not merge** until the failure is resolved or explicitly scoped by config/policy.
2. Reproduce locally with equivalent commands:
```bash
uv run --no-sync alembic upgrade head
uv run --no-sync pytest tests/integration/ -v -m integration
uv run --no-sync bandit -c pyproject.toml -r src/
```
3. Fix the underlying issue, then rerun quality gates.
4. If a finding is an accepted exception, document rationale in config/docs and keep CI explicit.

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

## Documentation Freshness

- Update this runbook whenever release gates, rollout commands, or rollback policy changes.
- Update related docs in the same PR:
  - `README.md`
  - `docs/DEPLOYMENT.md`
  - `docs/PROMPT_EVAL_POLICY.md` (if eval gates change)
