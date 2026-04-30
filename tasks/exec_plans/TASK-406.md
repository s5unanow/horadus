# TASK-406: Add Tier-scoped eval benchmark mode

## Status

- Owner: Codex
- Started: 2026-04-30
- Current state: Done
- Planning Gates: Required

## Goal (1-3 lines)

Add a Tier-scoped eval benchmark mode so Tier 2 diagnostics can run against
the full gold-set surface without paying for Tier 1 calls on every iteration.
Keep full-benchmark behavior unchanged by default.

## Inputs

- Spec/backlog references: `INTAKE-0035`; `tasks/BACKLOG.md` `TASK-406`
- Runtime/code touchpoints: `src/eval/benchmark.py`, Horadus eval CLI wiring,
  `src/processing/tier2_canary.py`, gold-set fixtures, benchmark result artifacts
- Preconditions/dependencies: Preserve full benchmark controls for human
  verification, max item count, config/model overrides, cost reporting, and
  provenance.

## Outputs

- Expected behavior/artifacts: CLI-accessible Tier 2-only benchmark mode that
  filters to Tier-2-labeled gold rows, skips Tier 1 model calls, runs Tier 2
  classification/mapper diagnostics, and emits benchmark-shaped results.
- Validation evidence: focused unit tests for selection/no-Tier-1 behavior and
  output shape, plus relevant eval CLI tests and the canonical local gate.

## Non-Goals

- Explicitly excluded work: improving Tier 2 prompt/mapper quality, changing
  gold-set labels, adding network-backed tests, or replacing the full benchmark.

## Scope

- In scope: benchmark tier selection, CLI/config wiring, result metadata,
  per-item failure preservation, usage/cost accounting, and regression tests.
- Out of scope: unrelated eval quality tuning, new production processing
  behavior, migrations, and broad gold-set rewrites.

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: add an explicit tier-scope control to
  the benchmark path with full benchmark as the default and a Tier 2-only branch
  that constructs Tier 2 inputs from human-verified gold rows.
- Rejected simpler alternative: relying on `src/processing/tier2_canary.py`
  because it covers only a small degraded-mode canary rather than full gold-set
  diagnostics and benchmark result provenance.
- First integration proof: focused benchmark unit/CLI tests passed on
  2026-04-30.
- Hotspot Outcome: reduce — extracted Tier-scope and benchmark-stage helpers
  into small support modules; `src/eval/benchmark.py` reduced to 936 lines.
- Waivers: none.

## Plan (Keep Updated)

1. Preflight (branch, tests, context) — done
2. Inspect benchmark, CLI, and Tier 2 canary contracts — done
3. Implement Tier-scoped benchmark mode with hotspot containment — done
4. Add focused regression tests — done
5. Validate and ship (PR, checks, merge, main sync) — in progress

## Decisions (Timestamped)

- 2026-04-30: Treat this as Planning Gates required because it touches LLM/eval
  pipeline cost controls and an allowlisted benchmark hotspot.
- 2026-04-30: Use `--tier-scope full|tier2` with `full` as the stable default;
  Tier 2 scope filters after human-verification and before `max_items`, then
  records Tier 1 as skipped rather than fabricating Tier 1 metrics.
- 2026-04-30: Operator-facing CLI docs were applicable and updated in
  `README.md`, `docs/PROMPT_EVAL_POLICY.md`, and `docs/AGENT_RUNBOOK.md`.

## Risks / Foot-guns

- Accidental Tier 1 calls in Tier 2-only mode -> add a regression test with a
  failing Tier 1 stub.
- Divergent result schema -> keep Tier 2-only output benchmark-shaped and assert
  key metadata/per-item fields.
- Hotspot growth -> extract helpers instead of adding another large block to
  `src/eval/benchmark.py`.

## Validation Commands

- `uv run --no-sync pytest tests/unit/eval tests/horadus_cli -q`
- `uv run --no-sync pytest tests/unit/eval/test_benchmark.py tests/unit/eval/test_benchmark_additional.py tests/horadus_cli/v2/test_app.py tests/horadus_cli/v2/test_ops_commands.py -q` — passed 2026-04-30
- `uv run --no-sync horadus eval benchmark --help` — passed 2026-04-30
- `uv run --no-sync ruff check src/eval/benchmark.py src/eval/benchmark_scope.py src/eval/benchmark_stages.py tools/horadus/python/horadus_cli/_ops_registration.py tools/horadus/python/horadus_app_cli_runtime.py tests/unit/eval/test_benchmark.py tests/unit/eval/test_benchmark_additional.py tests/horadus_cli/v2/test_app.py tests/horadus_cli/v2/test_ops_commands.py` — passed 2026-04-30
- `uv run --no-sync ruff format --check src/eval/benchmark.py src/eval/benchmark_scope.py src/eval/benchmark_stages.py tools/horadus/python/horadus_cli/_ops_registration.py tools/horadus/python/horadus_app_cli_runtime.py tests/unit/eval/test_benchmark.py tests/unit/eval/test_benchmark_additional.py tests/horadus_cli/v2/test_app.py tests/horadus_cli/v2/test_ops_commands.py` — passed 2026-04-30
- `uv run --no-sync mypy src/eval/benchmark.py src/eval/benchmark_scope.py src/eval/benchmark_stages.py tools/horadus/python/horadus_cli/_ops_registration.py tools/horadus/python/horadus_app_cli_runtime.py` — passed 2026-04-30
- `python scripts/check_code_shape.py` — passed 2026-04-30
- `make agent-check` — passed 2026-04-30
- `make test-integration-docker` — passed 2026-04-30
- `uv run --no-sync horadus tasks local-gate --full` — passed 2026-04-30

## Notes / Links

- Relevant modules: `src/eval/benchmark.py`, `src/processing/tier2_canary.py`
- Reference artifact: `ai/eval/results/benchmark-20260429T195059Z-e58db3fd.json`
