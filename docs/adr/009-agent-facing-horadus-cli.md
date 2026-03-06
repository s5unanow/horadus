# ADR-009: Agent-Facing Horadus CLI

**Status**: Accepted  
**Date**: 2026-03-06  
**Deciders**: human-operator + Codex

## Context

Horadus already exposes a Python CLI entrypoint plus a growing set of
task-oriented shell helpers and `make` targets. That surface works for humans,
but it is fragmented for agents:

- repo/task workflows are split across shell scripts, `make`, and direct
  markdown parsing
- structured output is inconsistent, which makes automation brittle
- dry-run and validation semantics are not consistently exposed through one
  interface

The repo now relies on agent/operator workflows for task start, triage, and
automation-driven assessments. Those paths need a stable, machine-readable, and
non-interactive command surface.

## Decision

Adopt `horadus` as the canonical structured interface for agent/operator repo
workflows.

Implementation rules:

- Keep the public command name `horadus`.
- Refactor CLI internals into a package so command groups can grow without
  collapsing into one large module.
- Prefer stable verbs and subcommands over one-off scripts.
- Support `--format text|json` for agent-facing workflow commands.
- Support `--dry-run` for commands with side effects.
- Use explicit non-zero exit codes for validation/policy failures, not-found
  cases, and environment/tooling failures.
- Keep commands non-interactive by default.

Boundary rules:

- `make` remains a human convenience layer and may wrap `horadus`.
- Shell scripts may remain when they are thin wrappers around `git`, `gh`,
  Docker, or platform tooling, but they should defer to `horadus` when an
  equivalent structured command exists.

## Consequences

### Positive

- Agents get a JSON-first repo workflow surface for task/sprint/triage work.
- Human and agent flows share one command contract instead of parallel logic.
- Workflow docs can point to one canonical interface.
- Existing wrapper scripts can shrink without losing backwards compatibility.

### Negative

- CLI scope expands beyond runtime/reporting into repo operations.
- Output compatibility now matters more because agents will depend on it.
- The repo must maintain both structured CLI behavior and wrapper compatibility.

### Neutral

- Existing external-tool-heavy scripts (PR merge, branch protection, backup,
  Docker orchestration, restore flows) remain valid and are not forced into the
  CLI in one pass.
- This does not introduce MCP or a separate CLI product.

## Alternatives Considered

### Alternative 1: Keep adding scripts and `make` targets

- Pros: low immediate implementation cost
- Cons: continues fragmentation, weak structured output, repeated parsing logic
- Why rejected: the repo already crossed the point where agent workflows need a
  canonical interface

### Alternative 2: Create a separate top-level `horadus-cli/` package

- Pros: strict separation from application runtime commands
- Cons: more packaging churn, duplicated entrypoint concepts, unnecessary
  product split
- Why rejected: this repo needs one CLI surface, not a second CLI product

### Alternative 3: Build MCP-first instead of CLI-first

- Pros: richer tool semantics for some agents
- Cons: higher implementation complexity and weaker ergonomics for humans and
  shell automation
- Why rejected: the immediate problem is repo workflow consistency, which a CLI
  solves directly

## References

- `docs/AGENT_RUNBOOK.md`
- `tasks/exec_plans/TASK-216.md`
- `ops/skills/horadus-cli/`
