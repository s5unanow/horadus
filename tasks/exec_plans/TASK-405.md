# TASK-405: Support separate OpenAI project keys by LLM tier

## Status

- Owner: Codex
- Started: 2026-04-29
- Current state: Ready to ship
- Planning Gates: Required

## Goal (1-3 lines)

Allow Tier 1 and Tier 2 OpenAI calls to use separate project API keys for cost
attribution, while preserving the existing `OPENAI_API_KEY` fallback behavior.

## Inputs

- Spec/backlog references: `TASK-405`, `INTAKE-0034`
- Runtime/code touchpoints: `src/core/config.py`, Tier 1/Tier 2 classifiers, eval
  benchmark wiring, Tier 2 canary/degraded-mode worker wiring, docs/env examples.
- Preconditions/dependencies: task branch created with `safe-start`; no network calls
  in tests.

## Outputs

- Expected behavior/artifacts: tier-specific `LLM_TIER1_API_KEY` and
  `LLM_TIER2_API_KEY` settings, matching `*_FILE` secret support, tier-aware
  runtime/eval client construction, docs and env examples.
- Validation evidence: focused unit tests for config secret loading, Tier 1/Tier 2
  client key selection, benchmark key selection, plus canonical repo gates.

## Non-Goals

- Explicitly excluded work: changing model routing, pricing math, OpenAI Costs API
  ingestion, or non-OpenAI provider account attribution.

## Scope

- In scope: primary Tier 1/Tier 2 API key resolution and secondary-route fallback to
  the tier primary key when no dedicated secondary key is configured.
- Out of scope: embedding, report, and retrospective API key separation.

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: add settings fields plus a shared
  tier-key resolver and update current Tier 1/Tier 2 runtime/eval call sites.
- Rejected simpler alternative: duplicating `settings.LLM_TIER*_API_KEY or
  settings.OPENAI_API_KEY` in each call site, because it invites drift in eval and
  degraded-mode paths.
- First integration proof: targeted unit tests; no external OpenAI network calls.
- Hotspot Outcome: keep-flat-with-rationale — `src/core/config.py` and
  `src/eval/benchmark.py` need narrow field/call-site edits; shared logic lives in a
  new focused module to avoid growing either hotspot with business logic.
- Waivers: integration Docker proof N/A; this changes client configuration wiring
  and unit-testable eval/runtime paths, not Docker/integration services.

## Plan (Keep Updated)

1. Preflight (branch, tests, context) — done
2. Implement — done
3. Validate — done
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-04-29: Use `LLM_TIER1_API_KEY` / `LLM_TIER2_API_KEY` names because the
  settings belong to LLM tier routing and fall back to the existing
  `OPENAI_API_KEY`.

## Risks / Foot-guns

- Eval benchmark could accidentally reuse one client/key for both tiers ->
  regression tests assert the constructed clients receive different keys.
- Secret-file precedence could drift from existing `_FILE` behavior -> config tests
  cover direct and file-backed tier settings.

## Validation Commands

- `uv run --no-sync pytest tests/unit/core/test_config.py tests/unit/processing/test_tier1_classifier_additional.py tests/unit/processing/test_tier2_classifier_additional.py tests/unit/eval/test_benchmark.py tests/unit/processing/test_tier2_canary.py`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

Evidence:

- 2026-04-29: `uv run --no-sync pytest tests/unit/core/test_config.py tests/unit/processing/test_tier1_classifier_additional.py tests/unit/processing/test_tier2_classifier_additional.py tests/unit/eval/test_benchmark.py tests/unit/eval/test_benchmark_additional.py tests/unit/processing/test_tier2_canary.py` passed (117 tests).
- 2026-04-29: `make agent-check` passed.
- 2026-04-29: `uv run --no-sync horadus tasks local-gate --full` passed all 17 steps, including integration Docker and package build.

## Notes / Links

- Spec: backlog entry for `TASK-405`
- Relevant modules: `src/core/config.py`, `src/core/llm_api_keys.py`,
  `src/processing/tier1_classifier.py`, `src/processing/tier2_classifier.py`,
  `src/eval/benchmark.py`, `src/processing/tier2_canary.py`,
  `src/workers/_task_processing.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
