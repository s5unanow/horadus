## Status

- Owner: Codex
- Started: 2026-03-07
- Current state: Done

## Goal (1-3 lines)

Add first-class reasoning-effort controls to the shared LLM route/invocation path
so Tier-1/Tier-2 runtime and benchmark flows can configure GPT-5 reasoning
cleanly, omit unsupported params safely, and record the effective setting.

## Scope

- In scope:
  - Route/config plumbing for reasoning-effort on runtime and benchmark paths
  - Safe omission for unsupported route params in the shared invocation adapter
  - Invocation/usage/artifact metadata for effective reasoning
  - Tests and docs for the new behavior
- Out of scope:
  - Responses API structured-output parity for Tier-1/Tier-2
  - Model-switch rollout decisions beyond exposing the controls

## Plan (Keep Updated)

1. Preflight (branch, tests, context) ✅
2. Implement route/config/adapter reasoning controls and metadata propagation ✅
3. Validate with targeted unit tests and repo checks ✅
4. Ship (PR, checks, merge, main sync) in progress

## Decisions (Timestamped)

- 2026-03-07: Keep the change centered on the shared `LLMChatRoute` contract so benchmark and runtime use the same mechanism. (avoids another benchmark-only override path)
- 2026-03-07: Treat unsupported reasoning/temperature params as adapter-level omissions rather than route-construction errors. (keeps GPT-5-safe behavior local to invocation)

## Risks / Foot-guns

- GPT-5 chat-completions temperature behavior differs from current Tier-1/Tier-2 defaults -> omit unsupported temperature params in the adapter and cover with tests.
- Route metadata can drift between invocation result, usage structs, and benchmark artifacts -> update all three surfaces in one patch and assert in tests.

## Validation Commands

- `uv run --no-sync pytest tests/unit/processing/test_llm_invocation_adapter.py tests/unit/processing/test_llm_policy.py tests/unit/processing/test_llm_failover.py tests/unit/core/test_config.py tests/unit/eval/test_benchmark.py -v`
- `uv run --no-sync ruff check src/core/config.py src/eval/benchmark.py src/processing/llm_failover.py src/processing/llm_invocation_adapter.py src/processing/llm_policy.py src/processing/tier1_classifier.py src/processing/tier2_classifier.py tests/unit/core/test_config.py tests/unit/eval/test_benchmark.py tests/unit/processing/test_llm_failover.py tests/unit/processing/test_llm_invocation_adapter.py tests/unit/processing/test_llm_policy.py`
- `uv run --no-sync ruff format --check src/core/config.py src/eval/benchmark.py src/processing/llm_failover.py src/processing/llm_invocation_adapter.py src/processing/llm_policy.py src/processing/tier1_classifier.py src/processing/tier2_classifier.py tests/unit/core/test_config.py tests/unit/eval/test_benchmark.py tests/unit/processing/test_llm_failover.py tests/unit/processing/test_llm_invocation_adapter.py tests/unit/processing/test_llm_policy.py`
- `uv run --no-sync python scripts/check_docs_freshness.py`
- `make agent-check`

## Notes / Links

- Spec: `tasks/BACKLOG.md` (`TASK-249`)
- Relevant modules: `src/processing/llm_invocation_adapter.py`, `src/processing/llm_policy.py`, `src/processing/llm_failover.py`, `src/core/config.py`, `src/eval/benchmark.py`
- Validation summary:
  - `uv run --no-sync pytest tests/unit/processing/test_tier1_classifier.py tests/unit/processing/test_tier2_classifier.py tests/unit/processing/test_llm_invocation_adapter.py tests/unit/processing/test_llm_policy.py tests/unit/processing/test_llm_failover.py tests/unit/core/test_config.py tests/unit/eval/test_benchmark.py -v`
  - `uv run --no-sync ruff check ...`
  - `uv run --no-sync ruff format --check ...`
  - `uv run --no-sync python scripts/check_docs_freshness.py`
  - `make agent-check`
