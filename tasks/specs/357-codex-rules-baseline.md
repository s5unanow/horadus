# TASK-357 Spec: Codex Rules Baseline for Autopilot Workflow

**Planning Gates**: Not Required — narrow local-tooling/config baseline addition

## Problem Statement

Codex app automations inherit sandbox restrictions unless the needed commands
are allowed by Codex rules. The repo currently versions only a placeholder
Claude allowlist surface, which does not help Codex app automations run the
Horadus workflow. The repo needs a Codex-specific baseline allowlist for the
automation commands required by the sprint autopilot.

## Inputs

- `agents/automation/horadus-sprint-autopilot.md`
- Codex rules docs (`codex/rules/*.rules` format)
- Existing local policy docs under `.claude/`

## Outputs

- Repo-owned Codex rules baseline
- Brief setup/readme guidance for the Codex rules baseline
- Regression test coverage for the expected command prefixes

## Non-Goals

- Changing the autopilot schedule or prompt beyond command coverage implications
- Managing user-specific tokens or secrets
- Expanding the allowlist beyond the workflow commands needed for autopilot

## Acceptance Criteria

- Add a repo-owned Codex `.rules` file with allow rules for the workflow prefixes needed by autopilot
- Include `uv run --no-sync horadus`, `git fetch`, `git pull --ff-only`, `git push`, `gh pr`, and `gh api`
- Document where the rules file lives and that operators still need to install or activate it in Codex app
- Add regression coverage that asserts the expected prefixes are present
