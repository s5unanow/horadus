# TASK-409: Improve Tier 2 eval accuracy to 90 percent

## Status

- Owner: Codex
- Started: 2026-04-30
- Current state: In progress
- Planning Gates: Required

## Goal (1-3 lines)

Improve Tier 2 gold-set accuracy by fixing schema/runtime parsing gaps and
deterministic mapper misses surfaced by the 2026-04-28 benchmark artifacts,
while preserving cost-aware Tier-scoped benchmark iteration.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md`, `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints: `src/eval`, `src/processing`, `ai/eval`, `tests/unit/eval`
- Preconditions/dependencies: Tier 1 stabilization and Tier-scoped benchmark support are complete.

## Outputs

- Expected behavior/artifacts:
  - Tier 2 accepts valid partial dates without schema hard-failing otherwise useful extractions.
  - Geopolitical state actors represented as actor/location facts can map safely when trend semantics allow them.
  - Deterministic mapping covers reproduced gold-set trend/signal semantics or records explicit residual exceptions.
  - Tier 2 benchmark diagnostics separate extraction validity, schema/runtime parsing, and deterministic mapper accuracy.
- Validation evidence:
  - Focused unit tests for parsing/mapping/reporting regressions.
  - Targeted Tier 2 benchmark proof where API credentials and cost controls permit.
  - `make agent-check`, `uv run --no-sync pytest tests/unit/ -v -m unit`, integration proof, and full local gate before finish.

## Non-Goals

- Explicitly excluded work:
  - Rewriting the Tier 2 prompt from scratch.
  - Re-labeling the human-verified gold set without source-backed evidence.
  - Changing Tier 1 queueing behavior.

## Scope

- In scope:
  - Runtime-compatible Tier 2 structured-output normalization.
  - Deterministic trend-impact mapper improvements tied to reproduced failures.
  - Eval metric/reporting changes needed to distinguish failure classes.
  - Tests for the fixed failure classes and metric contract.
- Out of scope:
  - Broad trend taxonomy redesign.
  - New external data collection or network-backed tests.
  - Production DB migrations unless a runtime schema mismatch proves unavoidable.

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: fix the narrow parsing, mapping, and diagnostic contracts already reproduced by benchmark artifacts before considering prompt or taxonomy expansion.
- Rejected simpler alternative: recording all failures as residual eval noise would leave known deterministic gaps unguarded and make repeated Tier 2 iteration expensive.
- First integration proof: run the Tier 2-scoped benchmark or document the exact credential/cost blocker; run `make test-integration-docker` because the context pack requires integration proof.
- Hotspot Outcome: keep-flat-with-rationale — TASK-409 may touch allowlisted eval/processing hotspots; edits must either stay line-neutral where practical or extract new focused helpers so no allowlisted maximum increases.
- Waivers: None currently.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Inspect 2026-04-28 Tier 2 failure artifacts and current mapper/parser code.
3. Implement focused parsing, mapper, and diagnostic changes.
4. Validate with focused unit tests and benchmark/local gates.
5. Close ledgers, finish PR lifecycle, and verify strict lifecycle state.

## Decisions (Timestamped)

- 2026-04-30: Use an exec plan instead of a lightweight spec because the task is large and declares allowlisted eval/processing hotspots.
- 2026-05-01: Treat the active Tier 2 baseline model (`gpt-4.1-mini`) as the 90 percent accuracy delivery target. The default benchmark still runs the cheaper `alternative` comparison (`gpt-4.1-nano`), which remains below target and is not promoted by this task.

## Risks / Foot-guns

- Benchmark proof can incur real LLM cost -> use Tier 2 scope and existing artifacts first, then run live benchmark only after focused tests pass.
- Keyword mapping improvements can create false positives -> add negative/regression cases around broad overlap before widening mappings.
- Partial-date normalization can invent precision -> preserve explicit date precision metadata or conservative defaults rather than pretending unknown month/day were observed.

## Validation Commands

- `uv run --no-sync pytest tests/unit/processing/test_tier2_runtime.py tests/unit/processing/test_entity_registry.py tests/unit/processing/test_tier2_classifier.py tests/unit/processing/test_tier2_classifier_additional.py tests/unit/processing/test_tier2_prompt_contract.py tests/unit/processing/test_trend_impact_mapping.py -v -m unit` (passed 2026-05-01)
- `uv run --no-sync pytest tests/unit/eval/test_benchmark.py -v -m unit` (passed 2026-05-01)
- `python scripts/check_code_shape.py` (passed 2026-05-01)
- `uv run --no-sync horadus eval benchmark --tier-scope tier2` (passed 2026-05-01; artifact `ai/eval/results/benchmark-20260501T144138Z-37e0d55d.json`; baseline: trend 1.0, signal 0.98, direction 1.0, failures 0/50)
- `make agent-check` (passed 2026-05-01)
- `make test-integration-docker` (passed 2026-05-01)
- `uv run --no-sync horadus tasks local-gate --full` (passed 2026-05-01)

## Notes / Links

- Assessment refs:
  - `ai/eval/results/benchmark-20260428T114016Z-11ebb40f.json`
  - `ai/eval/results/benchmark-20260428T131300Z-e7df83dc.json`
- Relevant modules:
  - `src/eval/benchmark.py`
  - `src/processing/tier2_classifier.py`
  - `src/processing/trend_mapping.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
