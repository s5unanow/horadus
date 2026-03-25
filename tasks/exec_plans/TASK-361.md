# TASK-361: Unblock repo-wide dependency audit for the current upstream-unfixed `pygments` CVE

## Status

- Owner: Codex automation
- Started: 2026-03-25
- Current state: Planning
- Planning Gates: Required — shared workflow/security policy contract change across repo-owned audit surfaces

## Goal (1-3 lines)

Restore a passing repo-owned dependency audit after `pip-audit` began flagging
`CVE-2026-4539` on the locked `pygments==2.19.2` dependency set, while keeping
the remediation explicit, narrow, and shared between local and CI execution.

## Inputs

- Spec/backlog references: `tasks/CURRENT_SPRINT.md`, `tasks/BACKLOG.md` (`TASK-361`)
- Runtime/code touchpoints: `scripts/run_dependency_audit.sh`, `docs/AGENT_RUNBOOK.md`, `pyproject.toml`, `uv.lock`, `tests/unit/scripts/`, `tests/horadus_cli/`
- Preconditions/dependencies: `./scripts/run_dependency_audit.sh` currently reproduces `pygments 2.19.2  CVE-2026-4539` locally with no fixed version advertised

## Outputs

- Expected behavior/artifacts: repo-owned dependency-audit policy that handles the current `pygments` CVE deterministically in both CI and local gates
- Validation evidence: direct dependency-audit command proof plus targeted regression coverage around the remediation path

## Non-Goals

- Explicitly excluded work: broad dependency refreshes, unrelated secret-scan policy changes, or weakening the audit to ignore unspecific vulnerability classes

## Scope

- In scope: narrow repo-owned remediation/exception path for this specific audit blocker, matching docs, and regression tests
- Out of scope: generalized vulnerability waiver management unless the smallest safe implementation naturally requires a minimal reusable policy surface

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: prefer a versioned repo-owned policy surface consumed by the audit helper over one-off CI-only flags
- Rejected simpler alternative: silently skipping dependency audit failures or broadening the ignore scope beyond the current `pygments` finding
- First integration proof: `./scripts/run_dependency_audit.sh` passes locally with the repo-owned remediation in place
- Waivers: none

## Plan (Keep Updated)

1. Reproduce and trace the current `pygments` dependency-audit failure — completed
2. Add the minimal repo-owned remediation path and regression coverage — in progress
3. Validate local audit plus affected test suites
4. Ship blocker fix through the canonical task lifecycle

## Decisions (Timestamped)

- 2026-03-25: Treat this as a separate blocker task instead of folding it into `TASK-344`, because the finding affects the repo-wide PR lifecycle and would otherwise mix tasks in one PR.

## Risks / Foot-guns

- A broad ignore would silently weaken future audit coverage -> keep the remediation CVE-specific and test its rendered command/policy surface
- CI/local drift would recreate the same blocker later -> wire the same repo-owned behavior through the script path that both environments use
- Upstream may release a fixed `pygments` version later -> make the remediation easy to remove once a proper upgrade is available

## Validation Commands

- `./scripts/run_dependency_audit.sh`
- `uv run --no-sync pytest tests/unit/scripts/ tests/horadus_cli/ -v -m unit`
- `make typecheck`
- `make agent-check`
- `uv run --no-sync horadus tasks local-review --format json`
- `uv run --no-sync horadus tasks finish TASK-361`

## Notes / Links

- Spec: backlog entry in `tasks/BACKLOG.md`
- Blocking finding reproduced locally on 2026-03-25 via `./scripts/run_dependency_audit.sh`
