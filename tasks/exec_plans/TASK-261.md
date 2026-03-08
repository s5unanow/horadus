# TASK-261: Auto-Handle Docker Readiness for Workflow Gates

## Status

- Owner: Codex
- Started: 2026-03-08
- Current state: Validation complete; ready to ship

## Goal (1-3 lines)

Teach the canonical workflow commands to detect when Docker is required,
attempt safe local recovery where supported, and fail with a specific blocker
when Docker cannot be made ready.

## Scope

- In scope:
  - Add Docker-readiness detection for explicit workflow commands that require integration services
  - Attempt supported local Docker startup and wait for daemon readiness before failing
  - Keep the behavior explicit and scoped to canonical workflow commands only
  - Add tests for ready, auto-recovered, and still-blocked Docker cases
  - Update workflow docs to explain when auto-start is attempted and how failure is reported
- Out of scope:
  - Changing unrelated `horadus` subcommands to auto-start Docker
  - Replacing the integration gate or weakening its failure behavior
  - Workflow skill/docs drift enforcement beyond the Docker-readiness guidance itself

## Plan (Keep Updated)

1. Inventory where Docker-backed steps are triggered in canonical workflow commands
2. Implement a reusable Docker-readiness helper plus targeted command wiring
3. Add coverage for ready, recovered, and blocked paths
4. Validate with focused tests and the canonical local gate, then ship

## Decisions (Timestamped)

- 2026-03-08: Keep Docker recovery scoped to explicit workflow gates (`tasks local-gate --full` and completion-path integration checks) so unrelated CLI commands never start Docker implicitly.
- 2026-03-08: Treat a missing remote task branch in `tasks finish` as a Docker-relevant next step because the required recovery path is a `git push`, and the repo pre-push hook enforces the Docker-backed integration gate.

## Risks / Foot-guns

- Auto-start can become surprising if it leaks into unrelated commands -> gate the behavior behind explicit workflow paths only
- Platform-specific Docker startup behavior can be flaky -> prefer best-effort supported local startup plus clear blocker messages when unsupported
- Silent integration bypass would undercut the workflow guarantees -> preserve non-zero failure when Docker still cannot be made ready

## Validation Commands

- `uv run --no-sync pytest tests/unit/test_cli.py -v`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: `tasks/BACKLOG.md` (`TASK-261`)
- Relevant modules: `src/horadus_cli/task_commands.py`, `tests/unit/test_cli.py`
