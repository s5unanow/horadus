# TASK-358 Spec: Portable Automation Lock Helper

**Planning Gates**: Not Required — narrow workflow-tooling follow-up on the repo-owned sprint autopilot

## Problem Statement

The sprint autopilot currently relies on the host `flock` utility to guard its
external lock path. Some Codex automation environments do not provide `flock`,
which blocks the run before task selection even when the repo-owned rules
baseline is installed correctly. The repo should own a portable lock helper
inside the Horadus CLI so automation lock behavior is available anywhere the
repo CLI itself can run.

## Inputs

- `agents/automation/horadus-sprint-autopilot.md`
- `codex/rules/default.rules`
- `docs/AGENT_RUNBOOK.md`
- `tools/horadus/python/horadus_cli/`
- `tools/horadus/python/horadus_workflow/`

## Outputs

- New Horadus CLI automation-lock command surface
- Updated sprint autopilot instructions using the repo-owned lock helper
- Updated Codex rules baseline coverage for the new command path
- Regression tests for parser wiring and lock behavior

## Non-Goals

- Adding lock expiry or forced stale-lock takeover
- Reworking the autopilot task-selection or finish lifecycle
- General-purpose distributed locking outside the local automation path

## Caller Inventory

- `agents/automation/horadus-sprint-autopilot.md` currently owns the external lock requirement for the sprint autopilot
- `ops/automations/specs/horadus-sprint-autopilot.toml` points automation runs at that instruction file
- `tests/unit/scripts/test_repo_automation_specs.py` and `tests/unit/scripts/test_repo_codex_rules.py` lock the repo-owned automation and rules contracts

## Acceptance Criteria

- `horadus` exposes repo-owned commands to check, acquire, and release an automation lock by path
- Lock acquisition is portable and atomic without shelling out to host `flock`
- Acquire/check output makes held vs available vs broken-path states explicit for automation callers
- The sprint autopilot instructions and rules baseline use the new command surface
- Tests cover acquire/release success, already-held lock detection, and one unaffected task-command path
