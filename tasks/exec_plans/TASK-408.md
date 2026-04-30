# TASK-408: Add Tier 1-only eval benchmark scope

## Status

- Owner: Codex
- Started: 2026-04-30
- Current state: Done
- Planning Gates: Required

## Goal (1-3 lines)

Add a `tier1` benchmark scope so operators can run Tier 1 gold-set diagnostics
without Tier 2 model calls, while preserving existing `full` and `tier2`
behavior.

## Inputs

- Spec/backlog references: `TASK-408` backlog entry promoted from `INTAKE-0037`
- Runtime/code touchpoints: `src/eval/benchmark.py`, eval CLI registration,
  benchmark tests, Horadus CLI/runbook/skill docs
- Preconditions/dependencies: no network calls in tests; benchmark behavior must
  be provable with fakes

## Outputs

- Expected behavior/artifacts: `horadus eval benchmark --tier-scope tier1`
  runs Tier 1 only, skips Tier 2, and records scope metadata in result artifacts
- Validation evidence: focused benchmark tests, CLI/parser tests, skill
  freshness/docs checks, `agent-check`, `local-gate --full`

## Non-Goals

- Explicitly excluded work: improving Tier 1 or Tier 2 model accuracy, changing
  gold-set labels, or adding new benchmark replay modes

## Scope

- In scope: extend existing tier-scope option, benchmark selection/execution
  logic, result metadata, docs, and skill freshness contract
- Out of scope: broad benchmark refactors beyond what is needed to keep the
  hotspot flat and tested

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: extend the existing `tier_scope`
  enum/path introduced for `tier2` rather than creating a new command.
- Rejected simpler alternative: documenting a manual `--max-items` workaround,
  because it would not prevent Tier 2 calls or encode scope metadata.
- First integration proof: run focused benchmark behavior tests proving `tier1`,
  `tier2`, and `full` call the intended classifier paths before local-gate.
- Hotspot Outcome: keep-flat-with-rationale - `src/eval/benchmark.py` is
  allowlisted; this task extends the existing scope branch with small helpers
  and tests instead of broad restructuring.
- Waivers: none expected.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Add `tier1` scope to CLI/config selection and benchmark result metadata
3. Update docs and skill freshness required tokens
4. Validate with focused tests, local review, local gate, finish, lifecycle

## Decisions (Timestamped)

- 2026-04-30: Use the existing tier-scope option as the operator surface
  because `tier2` already established the pattern.

## Risks / Foot-guns

- Accidentally running Tier 2 in `tier1` mode -> add fake classifier tests that
  fail on Tier 2 calls.
- Breaking `full` artifact compatibility -> preserve existing result schema and
  add scope value rather than renaming fields.

## Validation Commands

- `uv run --no-sync pytest tests/unit/eval/test_benchmark.py tests/unit/eval/test_benchmark_tier_scope.py -v -m unit` - passed
- `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit` - passed, 856 selected
- `make agent-check` - passed
- `make test-integration-docker` - passed
- `uv run --no-sync horadus tasks local-gate --full` - passed
- `uv run --no-sync horadus tasks local-review --format json --allow-provider-fallback` - passed via `gemini`, no findings

## Notes / Links

- Spec: backlog entry only
- Relevant modules: `src/eval/benchmark.py`, `tools/horadus/python/horadus_cli`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
