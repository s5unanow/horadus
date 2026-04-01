# TASK-189: Restrict `/health` and `/metrics` exposure outside development

## Status

- Owner: Codex
- Started: 2026-04-01
- Current state: Ready for canonical finish after human sign-off and task-close-state updates
- Planning Gates: Required — security-sensitive network exposure and auth policy change across runtime routes, docs, and tests

## Goal (1-3 lines)

Reduce unauthenticated reconnaissance risk by removing detailed health and
metrics endpoints from the public unauthenticated surface outside development,
while preserving a minimal liveness probe and reusing the existing privileged
operator boundary.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-189`),
  `artifacts/assessments/security/daily/2026-03-02.md`
- Runtime/code touchpoints: `src/api/middleware/auth.py`,
  `src/api/main.py`, `src/api/routes/health.py`, `src/api/routes/metrics.py`,
  `docs/DEPLOYMENT.md`, `tests/unit/api/`
- Preconditions/dependencies:
  - explicit in-thread human approval received before implementation
  - reuse the `TASK-200` privileged-route policy instead of inventing a second
    operational-endpoint auth model
  - retain one unauthenticated coarse liveness endpoint for probes

## Outputs

- Expected behavior/artifacts:
  - `/health/live` remains unauthenticated and returns only a coarse liveness
    payload
  - `/health`, `/health/ready`, and `/metrics` require the existing privileged
    operator boundary outside development
  - production-like health responses redact raw exception text and dependency
    internals while preserving coarse status information
  - deployment docs describe the new probe/operator access split
- Validation evidence:
  - focused unit coverage for auth exemptions plus dev vs production-like route
    behavior and payload shapes
  - repo-local gate evidence recorded before finish/merge

## Non-Goals

- Explicitly excluded work:
  - changing Prometheus metric contents
  - introducing private-network detection or a second access-control path
  - redesigning API-key/admin-secret storage semantics from `TASK-190`
  - changing unrelated API auth behavior outside the operational endpoints

## Scope

- In scope:
  - narrow auth exemption surface to the liveness route outside development
  - production-aware privileged-route dependency for health and metrics
  - payload redaction for externally reachable health responses in
    production-like environments
  - deployment and unit-test updates
- Out of scope:
  - new persistence, migrations, or infrastructure changes
  - private ingress/VPN enforcement beyond documenting the expected deployment
    posture

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - keep detailed dependency diagnostics in development only; for
    staging/production, preserve `/health/live` as the public probe and gate
    `/health`, `/health/ready`, and `/metrics` behind the existing
    privileged-route helper
- Rejected simpler alternative:
  - only adding auth to `/metrics` or leaving detailed `/health` payloads in
    production-like environments would still leak dependency and failure
    fingerprints
- First integration proof:
  - tests cover middleware exemption changes and both allowed/denied
    operational-route behavior under development vs staging settings
- Waivers:
  - Horadus `safe-start` cannot currently start a human-approved
    `[REQUIRES_HUMAN]` task; branch creation used raw `git switch -c ...` after
    verifying `origin/main...main` was `0 0`, and the forced fallback was
    recorded with `horadus tasks record-friction`

## Plan (Keep Updated)

1. Preflight (context, human approval, branch start fallback, exec plan)
2. Implement auth exemption tightening and production-aware privileged-route
   dependencies
3. Implement production-like health payload redaction and deployment doc updates
4. Validate with focused unit tests, `make agent-check`, integration proof, and
   canonical local gate
5. Ship (commit, push, PR, human sign-off, finish/lifecycle, main sync)

## Decisions (Timestamped)

- 2026-04-01: Use the existing admin-bound privileged-route helper for
  production-like `/health`, `/health/ready`, and `/metrics`. Reason: `TASK-200`
  already established that boundary and this task should not create a parallel
  auth model.
- 2026-04-01: Redact production-like health payloads to coarse component status
  only. Reason: admin auth alone does not satisfy the acceptance criterion that
  externally reachable health responses avoid raw exception strings and
  dependency internals.
- 2026-04-01: Treat the remaining `local-gate --full` dependency-audit failure
  as an external repo blocker, not additional `TASK-189` scope. Reason: the
  failing findings come from locked dependencies (`cryptography 46.0.5`,
  `pygments 2.19.2`) and this task does not touch dependency manifests or the
  audit policy.
- 2026-04-01: Bundle the minimal dependency-audit remediation into this branch
  after confirming it is limited to transitive dev-dependency lockfile updates
  plus stale allowlist cleanup. Reason: this was the smallest path to restore
  the canonical local gate without widening the runtime change set materially.
- 2026-04-01: Human operator explicitly authorized end-to-end completion and
  merge in-thread. Reason: `TASK-189` is marked `[REQUIRES_HUMAN]` and the
  task cannot enter canonical finish without recorded human sign-off.

## Risks / Foot-guns

- Prefix-matching auth exemptions could accidentally keep `/health/ready`
  public -> tighten exemption generation and regression-test the exact prefixes
- Route protection without payload redaction would still leak failure detail to
  authenticated external callers -> sanitize production-like health payloads and
  exception handling
- Over-redacting development responses would hurt local debugging -> keep full
  detail in development and assert that behavior in tests
- Doc drift could leave operators probing the wrong endpoint after deploy ->
  update deployment verification guidance in the same branch

## Validation Commands

- `uv run --no-sync pytest tests/unit/api/test_auth.py tests/unit/api/test_main_app.py tests/unit/api/test_health.py tests/unit/api/test_metrics.py -v -m unit`
- `make agent-check`
- `make test-integration-docker`
- `uv run --no-sync horadus tasks local-gate --full`

Current blocker evidence:

- `uv run --no-sync horadus tasks local-gate --full`
  - now passes after the bundled dependency remediation

## Notes / Links

- Spec: backlog-only task (`tasks/BACKLOG.md`)
- Relevant modules:
  - `src/api/middleware/auth.py`
  - `src/api/main.py`
  - `src/api/routes/health.py`
  - `src/api/routes/metrics.py`
  - `docs/DEPLOYMENT.md`
  - `tests/unit/api/`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
