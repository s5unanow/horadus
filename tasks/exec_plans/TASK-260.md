# TASK-260: Add a Full Local CI-Parity Gate in Horadus CLI

## Status

- Owner: Codex
- Started: 2026-03-08
- Current state: Validation complete; ready to ship

## Goal (1-3 lines)

Expose the repo’s canonical post-task local gate through `horadus` so agents
can run one full pre-PR validation command without overloading the fast
iteration gate. The CLI surface must stay authoritative, and any `make`
wrapper must delegate rather than reimplement the gate.

## Scope

- In scope:
  - Add a `horadus` local-gate/task-gate command for the full pre-PR validation path
  - Reuse existing repo-owned commands/targets where appropriate instead of creating a parallel gate authority
  - Keep `make agent-check` as the fast iteration gate and make any full-gate wrapper a thin delegate
  - Update docs/context guidance to point to the canonical CLI command
  - Add unit coverage for command wiring, failure propagation, and drift-sensitive command lists
- Out of scope:
  - Docker auto-start behavior (`TASK-261`)
  - Lifecycle-state verification (`TASK-259`)
  - Coverage threshold hard-fail rollout (`TASK-257`) beyond using the current full gate requirements

## Plan (Keep Updated)

1. Preflight (branch, context, exec plan, gate-surface inventory)
2. Implement canonical CLI full local gate and thin wrapper delegation
3. Validate with focused tests plus local gate/doc checks
4. Ship via PR, checks, merge, and main sync

## Decisions (Timestamped)

- 2026-03-08: Treat `horadus` as the canonical full-gate authority and keep `make agent-check` explicitly separate as the fast inner-loop gate.
- 2026-03-08: Include `check_no_tracked_artifacts.sh` and the full `tests/unit/` coverage run in the canonical gate so the CLI sequence matches CI categories instead of the faster iteration subset.

## Risks / Foot-guns

- A new CLI gate can drift from Make/docs quickly -> centralize the command list in repo code and test it
- Reusing `make` naively can create recursive or parallel authorities -> make any full-gate wrapper call the CLI, not the other way around
- Full-gate output can overwhelm context -> preserve failure details for the failing sub-step only

## Validation Commands

- `uv run --no-sync pytest tests/unit/test_cli.py -v`
- `make docs-freshness`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: `tasks/BACKLOG.md` (`TASK-260`)
- Relevant modules: `src/horadus_cli/task_commands.py`, `Makefile`, `docs/AGENT_RUNBOOK.md`, `README.md`
