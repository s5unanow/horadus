# TASK-356 Spec: Autopilot Lock Path Follow-Up

**Planning Gates**: Not Required — narrow prompt/spec follow-up on an existing repo-owned automation

## Problem Statement

The sprint autopilot automation currently instructs the run to create a lock
under `~/.codex/locks/`, but the live Codex automation environment cannot
create that top-level directory. The lock needs to stay outside the repo while
moving to a Codex-owned path that already exists for the automation runtime.

## Inputs

- `agents/automation/horadus-sprint-autopilot.md`
- `ops/automations/specs/horadus-sprint-autopilot.toml`
- `tests/unit/scripts/test_repo_automation_specs.py`

## Outputs

- Updated prompt guidance that uses the automation-owned Codex path for locking
- Updated regression assertions for the lock-path guidance

## Non-Goals

- Changing the automation schedule
- Moving the lock into the git worktree
- Reworking the overall sprint autopilot flow beyond the lock path fix

## Acceptance Criteria

- Replace the `~/.codex/locks/` guidance with an automation-owned path under `~/.codex/automations/horadus-sprint-autopilot/`
- Keep the lock external to the repo
- Preserve the existing sync-main, resume-path, and one-task-per-run guidance
