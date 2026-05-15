# TASK-412: Improve Tier 2 signal quality before go-live

## Status

- Owner: Codex
- Started: 2026-05-15
- Current state: Blocked - live Tier 2 benchmark blocked by provider quota
- Planning Gates: Required - L task touching Tier 2 extraction/mapping quality.

## Goal

Improve Tier 2 trend/signal/direction quality on the human-verified eval set
without changing Tier 1 scope or materially increasing benchmark cost.

## Inputs

- Spec/backlog references: `TASK-412`, promoted from `INTAKE-0038`
- Runtime/code touchpoints: Tier 2 prompt, trend config loader, trend YAML keywords
- Preconditions/dependencies: prior baseline artifact `benchmark-20260502T080827Z-fa98b4e7.json`

## Outputs

- Expected behavior/artifacts: Better Tier 2 primary category selection and deterministic mapping for reproduced mismatch rows.
- Validation evidence: focused unit tests, saved-output replay, eval audit/taxonomy validation, agent/local gates; live benchmark proof blocked by provider quota.

## Non-Goals

- Change Tier 1 benchmark scope or thresholds.
- Introduce network calls in tests.
- Re-label gold rows except where already completed by prior tasks.

## Scope

- In scope: prompt guidance, config-loaded trend context, deterministic keyword coverage, focused regressions.
- Out of scope: model/provider changes and broad taxonomy redesign.

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: improve taxonomy context and explicit trigger vocabulary before changing core scoring.
- Rejected simpler alternative: prompt-only tuning, because prior raw outputs show deterministic mapping still needs exact trigger coverage.
- First integration proof: targeted Tier 2 mapping tests before full gates.
- Hotspot Outcome: keep-flat-with-rationale - no allowlisted hotspot is touched.
- Waivers: integration proof is N/A unless runtime code changes require Docker-backed services; this task is offline eval/prompt/config focused.

## Plan

1. Preflight (branch, tests, context)
2. Implement prompt/config/loader improvements
3. Validate with focused tests and eval gates
4. Ship through Horadus finish/lifecycle

## Decisions

- 2026-05-15: Preserve YAML actors/regions in config-loaded trends so benchmark/canary Tier 2 payloads match runtime taxonomy context.
- 2026-05-15: Prefer targeted keyword additions over changing mapper scoring unless tests show scoring remains wrong.
- 2026-05-15: Full live Tier 2 benchmark proof attempted with baseline config and human-verified rows; blocked by OpenAI `insufficient_quota`, so same-branch proof uses saved-output replay plus offline eval gates until quota is restored.
- 2026-05-15: `make agent-check` and `uv run --no-sync horadus tasks local-gate --full` both passed.

## Risks / Foot-guns

- Overfitting keywords to gold rows -> use generic trigger phrases present in real trend semantics.
- Prompt changes increasing cost -> keep prompt additions short and avoid adding output fields.
- Live benchmark quota exhaustion -> report as blocker if delivery reaches PR lifecycle before quota is restored.

## Validation Commands

- `uv run --no-sync pytest tests/unit/core/test_trend_config_loader.py tests/unit/processing/test_trend_impact_mapping.py -v -m unit`
- `uv run --no-sync horadus eval audit --fail-on-warnings`
- `uv run --no-sync horadus eval validate-taxonomy --trend-config-dir config/trends --tier1-trend-mode subset`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`
- Blocked: `uv run --no-sync horadus eval benchmark --tier-scope tier2 --config baseline --require-human-verified --trend-config-dir config/trends --max-items 200 --format json`

## Notes / Links

- Baseline artifact: `ai/eval/results/benchmark-20260502T080827Z-fa98b4e7.json`
- Policy: `docs/PROMPT_EVAL_POLICY.md`
