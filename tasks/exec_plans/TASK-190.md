# TASK-190: Harden admin-key compare + API key store file permissions

## Status

- Owner: Codex
- Started: 2026-04-01
- Current state: In progress after 2026-04-01 human approval of the
  fail-closed key-store hardening policy
- Planning Gates: Not Required — small security hardening task, but this exec
  plan is kept as the required checklist/context artifact for a
  `[REQUIRES_HUMAN]` task

## Goal (1-3 lines)

Eliminate timing-sensitive admin key comparison and make persisted runtime API
key metadata fail closed unless the underlying file and directory protections
are hardened successfully.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-190`),
  `tasks/CURRENT_SPRINT.md`, `artifacts/assessments/security/daily/2026-03-02.md`
- Runtime/code touchpoints: `src/api/routes/auth.py`,
  `src/core/api_key_manager.py`, `docs/DEPLOYMENT.md`,
  `docs/SECRETS_RUNBOOK.md`, `tests/unit/api/`, `tests/unit/core/`
- Preconditions/dependencies:
  - `horadus tasks preflight` passed on synced `main`
  - `horadus tasks safe-start` cannot currently start `[REQUIRES_HUMAN]`
    tasks, so branch creation uses documented raw `git` fallback plus recorded
    workflow friction
  - human operator approved the strict policy choice: fail when key-store
    hardening cannot be enforced or verified; do not continue with warning-only
    persistence

## Outputs

- Expected behavior/artifacts:
  - admin key checks use `secrets.compare_digest(...)`
  - persisted API key temp + final files require owner-only permissions where
    the platform exposes POSIX mode semantics
  - parent directory permissions are validated before persistence and
    non-private directories fail closed when enforcement/verification is
    possible
  - operator-facing docs explain how to provision the persisted key-store path
    separately from `_FILE` input secret mounts
- Validation evidence:
  - focused auth and API key manager unit tests covering compare primitive,
    restrictive-mode success, and fail-closed permission errors
  - `make agent-check`
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Explicitly excluded work:
  - changing the broader `_FILE` input secret policy or compose wiring in this
    task
  - moving persisted API key metadata into an external secret manager
  - adding a warning-only fallback path when permission hardening fails

## Scope

- In scope:
  - constant-time admin key comparison
  - persisted key-store file/directory permission enforcement and verification
  - unit tests for success and fail-closed paths
  - operator docs for `API_KEYS_PERSIST_PATH`
- Out of scope:
  - unrelated auth route changes
  - unrelated deployment workflow refactors

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: apply constant-time compare in the
  existing auth route and keep persistence hardening inside the existing
  `APIKeyManager` write path
- Accepted policy: if persisted key-store hardening cannot be enforced or
  verified on the current platform/filesystem, fail persistence instead of
  logging a warning and continuing
- Rejected simpler alternative: relying on host `umask` alone leaves the final
  security posture dependent on ambient system defaults
- First integration proof: focused unit coverage for persisted file/directory
  mode handling plus operator doc updates in the same branch
- Waivers:
  - Horadus `safe-start` cannot currently start a human-approved
    `[REQUIRES_HUMAN]` task; branch creation used raw
    `git switch -c codex/task-190-harden-api-key-store` after preflight and
    the forced fallback was recorded with `horadus tasks record-friction`

## Plan (Keep Updated)

1. Preflight (context, branch fallback, exec plan)
2. Implement auth compare + persisted key-store hardening helpers
3. Update tests for success and fail-closed permission paths
4. Update deployment/secret docs for `API_KEYS_PERSIST_PATH`
5. Validate with targeted tests, `make agent-check`, and canonical local gate
6. Ship (commit, push, PR, explicit human sign-off, finish/lifecycle, main sync)

## Decisions (Timestamped)

- 2026-04-01: Use fail-closed behavior when persisted key-store hardening
  cannot be enforced or verified. (reason: the human operator explicitly chose
  strict security posture over compatibility)
- 2026-04-01: Document `API_KEYS_PERSIST_PATH` separately from `_FILE` input
  secrets. (reason: the operator flow for persisted runtime metadata is not
  currently explicit enough in the docs)

## Risks / Foot-guns

- Treating all filesystems as POSIX-capable could break valid non-POSIX
  environments -> detect when mode verification is unsupported and fail with a
  clear message instead of silently pretending hardening succeeded
- Hardening only the final file but not the temp file still leaks during writes
  -> apply the same owner-only policy to temp + final paths
- Doc drift could leave operators thinking `_FILE` and persisted runtime key
  storage are the same thing -> add explicit separation in the deployment docs

## Validation Commands

- `uv run --no-sync pytest tests/unit/api/routes/test_auth.py -v`
- `uv run --no-sync pytest tests/unit/core/test_api_key_manager.py -v`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Relevant modules: `src/api/routes/auth.py`, `src/core/api_key_manager.py`
- Relevant docs: `docs/DEPLOYMENT.md`, `docs/SECRETS_RUNBOOK.md`,
  `docs/ENVIRONMENT.md`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
