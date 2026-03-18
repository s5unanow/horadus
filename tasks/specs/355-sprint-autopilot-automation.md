# TASK-355 Spec: Horadus Sprint Autopilot Automation

**Planning Gates**: Not Required — narrow repo-owned automation addition using existing sync surfaces

## Problem Statement

The repo already versions desired-state Codex automations, but it does not yet
have a repo-owned automation for autonomous sprint task implementation. The new
automation must be safe for periodic execution in the shared workspace, which
requires explicit mutual exclusion and repo-idle checks before any task work
begins.

## Inputs

- `AGENTS.md`
- `tasks/CURRENT_SPRINT.md`
- `ops/automations/README.md`
- `agents/automation/README.md`

## Outputs

- `agents/automation/horadus-sprint-autopilot.md`
- `ops/automations/specs/horadus-sprint-autopilot.toml`
- `ops/automations/ids.txt`

## Non-Goals

- Applying the automation into local `$CODEX_HOME/automations/`
- Implementing new automation sync tooling behavior
- Adding a one-off probe automation

## Acceptance Criteria

- Add canonical autopilot instructions under `agents/automation/`
- Add a matching desired-state automation spec under `ops/automations/specs/`
- Keep the spec prompt minimal and make it open the tracked instruction file
- Encode the external-lock, idle-repo, preflight/safe-start, and one-task-per-run requirements in the instruction file
- Keep the schedule at every 2 hours and the execution environment consistent with the shared Horadus workspace
