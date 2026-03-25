# TASK-354: Centralize repo-owned secret-scan policy and exclude rules

## Status

- Owner: Codex automation
- Started: 2026-03-25
- Current state: Validated, ready to ship
- Planning Gates: Required — shared workflow/security policy contract change

## Goal (1-3 lines)

Move secret-scan excludes and shared scan semantics to one authoritative
repo-owned source so the pre-commit hook, local/CI scan helper, and workflow
tests stay aligned by construction.

## Inputs

- Spec/backlog references: `tasks/CURRENT_SPRINT.md`, `tasks/BACKLOG.md` (`TASK-354`)
- Runtime/code touchpoints: `.pre-commit-config.yaml`, `scripts/check_secret_baseline.py`, `scripts/run_secret_scan.sh`, `docs/AGENT_RUNBOOK.md`, `tests/unit/scripts/`, `tests/horadus_cli/v2/test_task_workflow.py`
- Preconditions/dependencies: current exclude policy is duplicated between `.pre-commit-config.yaml` and `scripts/check_secret_baseline.py`

## Outputs

- Expected behavior/artifacts: one repo-owned secret-scan policy surface consumed by both the pre-commit hook and the repo-owned tracked-file scan helper
- Validation evidence: targeted tests that fail on policy drift, plus the normal task workflow gates

## Non-Goals

- Explicitly excluded work: changing the effective exclude scope without justification, replacing `detect-secrets`, or broadening security-policy ownership beyond secret-scan behavior

## Scope

- In scope: extract the canonical secret-scan policy, update both consumers, add drift regression coverage, and document the ownership point
- Out of scope: dependency-audit policy, baseline file regeneration, or unrelated workflow-gate reshaping

## Caller Inventory

- `.pre-commit-config.yaml`: repo-owned `secret-scan` hook runs `./scripts/run_secret_scan.sh` during local hook execution
- `scripts/check_secret_baseline.py`: tracked-file scanner applies the same exclude policy while diffing scan results against `.secrets.baseline`
- `scripts/run_secret_scan.sh`: stable entrypoint used by local gate, CI, and `make secret-scan`
- `tools/horadus/python/horadus_workflow/task_workflow_gate_steps.py`: local full-gate references `./scripts/run_secret_scan.sh`
- `.github/workflows/ci.yml` and `Makefile`: server-side/local workflow entrypoints call `./scripts/run_secret_scan.sh`
- `tests/unit/scripts/test_check_secret_baseline*.py` and `tests/horadus_cli/v2/test_task_workflow.py`: regression surfaces that should detect future drift

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: store the shared exclude regex and hook arguments in one repo-owned JSON policy artifact that both Python and workflow config tests can read
- Rejected simpler alternative: keep duplicated regex strings in Python and YAML and rely on review/tests to catch mismatches after the fact
- First integration proof: `make test-integration-docker` passed after the shared policy artifact and repo-owned hook wiring landed
- Waivers: none

## Plan (Keep Updated)

1. Inspect current duplicated secret-scan policy, consumers, and tests — completed
2. Add the authoritative policy artifact and update Python/hook consumers — completed
3. Add drift-focused regression tests and docs updates — completed
4. Run targeted tests and stronger gates — completed
5. Commit, run branch-diff local review, and ship through `horadus tasks finish TASK-354` — in progress

## Decisions (Timestamped)

- 2026-03-25: Use a repo-owned data artifact for the shared secret-scan policy so YAML, Python, and workflow tests can all consume the same source without duplicating regex literals.
- 2026-03-25: Replace the third-party pre-commit `detect-secrets` hook entry with a repo-owned `secret-scan` hook that calls `./scripts/run_secret_scan.sh`, so local hook execution and CI/local-gate scanning use the same code path.

## Risks / Foot-guns

- YAML consumer drift if the hook still hardcodes regexes -> derive workflow assertions from the same artifact-backed rendering path
- Overbroad excludes could silently weaken scanning -> preserve the current effective excluded surfaces unless task evidence justifies a change
- Hidden caller drift in workflow surfaces -> keep `./scripts/run_secret_scan.sh` as the stable entrypoint and cover unaffected callers in tests

## Validation Commands

- `uv run --no-sync pytest tests/unit/scripts/test_check_secret_baseline.py tests/unit/scripts/test_check_secret_baseline_additional.py tests/horadus_cli/v2/test_task_workflow.py -v -m unit`
- `./scripts/run_secret_scan.sh`
- `make test-integration-docker`
- `make agent-check`
- `uv run --no-sync horadus tasks local-review --format json`
- `uv run --no-sync horadus tasks local-gate --full`
- `uv run --no-sync horadus tasks finish TASK-354`

## Notes / Links

- Spec: backlog entry in `tasks/BACKLOG.md`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
