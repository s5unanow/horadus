# TASK-407: Refresh Horadus CLI skill and add freshness gate

## Status

- Owner: Codex
- Started: 2026-04-30
- Current state: Validated; finishing
- Planning Gates: Required

## Goal (1-3 lines)

Refresh the repo-owned Horadus CLI skill so agents see current command
surfaces, then add a docs-freshness guard that catches future skill/runbook CLI
drift automatically.

## Inputs

- Spec/backlog references: `INTAKE-0036`; `tasks/BACKLOG.md` `TASK-407`
- Runtime/code touchpoints: `ops/skills/horadus-cli/`,
  docs-freshness workflow checks, workflow tests, `docs/AGENT_RUNBOOK.md`
- Preconditions/dependencies: Preserve `AGENTS.md` as canonical workflow
  policy owner; keep skills concise and point to references for details.

## Outputs

- Expected behavior/artifacts: refreshed `horadus-cli` skill guidance for
  current task/eval/root command surfaces and a regression-tested freshness
  check that fails when required CLI command tokens are absent from the skill.
- Validation evidence: focused workflow tests, docs-freshness check,
  `make agent-check`, and the canonical local gate.

## Non-Goals

- Explicitly excluded work: redesigning CLI registration, adding new Horadus
  commands, broad skill architecture changes, or duplicating all runbook prose
  in skill front matter.

## Scope

- In scope: `ops/skills/horadus-cli/SKILL.md`,
  `ops/skills/horadus-cli/references/commands.md`, docs-freshness implementation,
  and focused tests.
- Out of scope: unrelated skills, plugin metadata, and non-Horadus CLI docs.

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: keep `SKILL.md` thin, refresh detailed
  command notes in the skill reference, and add a token-level docs-freshness
  contract for command/option names that must stay visible in the skill.
- Rejected simpler alternative: manual-only skill review, because TASK-406
  showed that strict gates can pass while the skill silently drifts.
- First integration proof: run focused docs-freshness workflow tests before the
  full local gate.
- Hotspot Outcome: keep-flat-with-rationale - no allowlisted production hotspot
  is materially changed by this task.
- Waivers: none.

## Plan (Keep Updated)

1. Preflight (branch, tests, context) - done
2. Inspect current docs-freshness skill/runbook checks - done
3. Refresh Horadus CLI skill and command reference - done
4. Add docs-freshness guard and regression tests - done
5. Validate and ship (PR, checks, merge, main sync) - in progress

## Decisions (Timestamped)

- 2026-04-30: Treat planning gates as required because this changes shared
  workflow docs/freshness behavior and repo-owned agent skill guidance.
- 2026-04-30: Keep the freshness gate token-based across the combined skill
  surface (`SKILL.md` plus `references/commands.md`) so the top-level skill
  stays concise while required command names and options remain guarded.

## Risks / Foot-guns

- Over-duplicating AGENTS policy in skills -> keep skill guidance thin and
  command-focused.
- Brittle prose matching -> check required command/option tokens rather than
  exact paragraphs.
- Breaking unrelated docs-freshness callers -> include a regression for an
  unaffected docs-freshness path.

## Validation Commands

- PASS: `uv run --no-sync pytest tests/workflow/test_docs_freshness.py tests/workflow/test_docs_freshness_workflow_boundaries.py -q`
- PASS: `uv run --no-sync pytest tests/workflow/test_repo_workflow.py tests/workflow/test_docs_freshness.py tests/workflow/test_docs_freshness_workflow_boundaries.py -q`
- PASS: `uv run --no-sync python scripts/check_docs_freshness.py`
- PASS: `make typecheck`
- PASS: `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit`
- PASS: `make agent-check`
- PASS: `make test-integration-docker`
- PASS: `uv run --no-sync horadus tasks local-gate --full`
- PASS: `uv run --no-sync horadus tasks local-review --format json --allow-provider-fallback`
  completed via `claude` on the amended branch diff; no findings reported.

## Notes / Links

- Skill: `ops/skills/horadus-cli/SKILL.md`
- Reference: `ops/skills/horadus-cli/references/commands.md`
