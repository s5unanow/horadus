# Repo-Owned Codex Baselines

This directory versions Codex app configuration that should stay reviewable
alongside the repo workflow.

## Rules

- Baseline allowlist: `codex/rules/default.rules`
- Purpose: allow the Horadus sprint autopilot to run the canonical workflow
  commands outside the default automation sandbox when the operator chooses to
  activate the baseline.
- Coverage: the repo-owned Horadus CLI entrypoint plus the git and GitHub CLI
  subcommands that the current preflight, safe-start, and finish lifecycle
  shells out to.

## Operator Setup

Codex does not activate repo-owned rules automatically just because they exist
in git. Operators must install or copy the baseline into an active Codex rules
layer and restart Codex.

Recommended flow:

1. Review `codex/rules/default.rules`.
2. Copy the approved baseline into your active Codex rules layer, such as
   `~/.codex/rules/default.rules`, or another team-config-backed `codex/rules/`
   location that Codex loads at startup.
3. Restart Codex so the new rules are loaded.

Keep the repo file as the canonical reviewed baseline; treat user-local rules as
applied state.
