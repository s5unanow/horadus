# TASK-262: Enforce No Early Completion Claims in Agent Workflow Guidance

## Status

- Owner: Codex
- Started: 2026-03-08
- Current state: Validation complete; ready to ship

## Goal (1-3 lines)

Make the repo’s agent guidance explicit that local milestones are not
completion, and reserve “done/complete/finished” claims for mechanically
verified end states only.

## Scope

- In scope:
  - Tighten completion-claim guidance in agent-facing docs
  - Add backlog/header guidance for the same policy
  - Extend docs freshness to enforce the guidance
- Out of scope:
  - Changing the completion tooling itself
  - New workflow commands beyond documentation/consistency enforcement

## Plan (Keep Updated)

1. Preflight (branch, context, target docs)
2. Implement guidance and docs-freshness enforcement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-08: Enforce the guidance through docs-freshness rather than a
  standalone doc lint. (Keeps drift checks on the existing repo-owned gate.)
- 2026-03-08: Put the exact completion-policy sentences in shared repo workflow
  constants and validate them with whitespace-normalized matching. (Keeps the
  guidance consistent without making markdown line wrapping a false blocker.)

## Risks / Foot-guns

- Guidance can become inconsistent across surfaces -> update all core
  agent-facing docs in the same task
- Phrase matching can be brittle -> normalize whitespace and check a small set
  of canonical policy sentences

## Validation Commands

- `uv run --no-sync pytest tests/unit/core/test_docs_freshness.py -k 'completion' -v`
- `make docs-freshness`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none
- Relevant modules:
  - `AGENTS.md`
  - `README.md`
  - `docs/AGENT_RUNBOOK.md`
  - `tasks/BACKLOG.md`
  - `src/core/docs_freshness.py`
