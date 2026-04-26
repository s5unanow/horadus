# TASK-398: Fix Eval Benchmark Noop Session Contract

## Status

- Owner: Codex
- Started: 2026-04-26
- Current state: Done
- Planning Gates: Required

## Goal (1-3 lines)

Restore the golden-set live benchmark so the offline Tier-2 path satisfies the
current `Tier2Classifier` session contract without changing runtime behavior.

## Inputs

- Spec/backlog references: `TASK-398` in `tasks/BACKLOG.md`
- Runtime/code touchpoints: `src/eval/benchmark.py`,
  `src/processing/tier2_classifier.py`, focused tests
- Preconditions/dependencies: `make benchmark-eval` currently fails with
  `_NoopSession` missing `execute`; taxonomy validation and audit are clean.

## Outputs

- Expected behavior/artifacts: benchmark writes a JSON artifact under
  `ai/eval/results/` instead of failing on the offline session stub.
- Validation evidence: focused regression tests, deterministic eval validation,
  integration proof, canonical local gates, and live benchmark proof.

## Non-Goals

- Explicitly excluded work: prompt/model tuning, gold-set relabeling, and
  changing runtime Tier-2 database behavior.

## Scope

- In scope: eval-only session/context handling and tests that pin the benchmark
  contract.
- Out of scope: production persistence refactors and baseline promotion.

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: keep the fix in the eval harness unless
  runtime code needs a narrow injection point for existing event context.
- Rejected simpler alternative: ignoring the Tier-2 event context load would
  hide future classifier/session drift instead of proving the offline contract.
- First integration proof: `make test-integration-docker` passed on 2026-04-26.
- Hotspot Outcome: reduce — keep edits small and offset any new benchmark helper
  code so `src/eval/benchmark.py` does not grow beyond its ratchet.
- Waivers: docs update N/A; this changes internal eval/runtime bridge behavior
  covered by tests and existing runbook commands, without changing documented
  operator syntax.

## Plan (Keep Updated)

1. Preflight (branch, tests, context) — done
2. Implement eval harness contract fix — done
3. Validate focused tests and eval commands — done
4. Ship (PR, checks, merge, main sync) — pending

## Decisions (Timestamped)

- 2026-04-26: Treat the benchmark failure as an eval-harness contract bug
  because gold-set taxonomy validation and audit passed before implementation.
- 2026-04-26: Redirect runtime bridge action stdout to stderr so provider
  warnings cannot corrupt the JSON envelope consumed by CLI wrapper commands.

## Risks / Foot-guns

- Live benchmark can spend provider tokens -> use the existing `max-items 50`
  target and do not add extra exploratory LLM sweeps.
- Touching an allowlisted hotspot can regress code-shape ratchets -> keep
  `src/eval/benchmark.py` flat or smaller.

## Validation Commands

- `uv run --no-sync pytest tests/unit/eval/test_benchmark.py -q`
- `uv run --no-sync pytest tests/unit/eval/test_benchmark_noop_session_contract.py -q`
- `uv run --no-sync pytest tests/horadus_cli/v2/test_ops_commands.py -q`
- `uv run --no-sync horadus eval validate-taxonomy --gold-set ai/eval/gold_set.jsonl --trend-config-dir config/trends --output-dir ai/eval/results --max-items 200 --tier1-trend-mode subset --signal-type-mode warn --unknown-trend-mode warn`
- `uv run --no-sync horadus eval audit --gold-set ai/eval/gold_set.jsonl --output-dir ai/eval/results --max-items 0 --fail-on-warnings`
- `make benchmark-eval`
- `make agent-check`
- `make test-integration-docker`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none
- Relevant modules: `src/eval/benchmark.py`, `src/processing/tier2_classifier.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
