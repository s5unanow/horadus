# TASK-191: Cross-stage SLO/error-budget release gate

## Status

- Owner: Codex
- Started: 2026-03-02
- Current state: Done

## Goal (1-3 lines)

Add a deterministic runtime gate that evaluates cross-stage SLO/error-budget
signals and fails closed for staging/production-like release decisions.

## Scope

- In scope:
  - Runtime-gate evaluator module + CLI script
  - `make release-gate-runtime` target
  - Unit tests with synthetic metrics payloads
  - Runbook/deployment docs for tuning/interpretation
- Out of scope:
  - Live metrics collector implementation
  - Historical analytics backend

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-02: Implemented gate as input-driven JSON evaluator (`artifacts/agent/runtime_slo_metrics.json`) to keep checks deterministic and CI-friendly.
- 2026-03-02: Strict mode auto-enables in staging/production; development remains warn-only unless `--strict` is provided.

## Risks / Foot-guns

- Missing/invalid runtime metrics payload in strict mode causes hard failure.
- Thresholds that are too strict can create false blocks; tune via script flags.

## Validation Commands

- `uv run --no-sync pytest tests/unit/core/test_release_gate_runtime.py -v -m unit`
- `uv run --no-sync python scripts/release_gate_runtime.py --environment development`

## Notes / Links

- Spec: `tasks/BACKLOG.md` (`TASK-191`)
- Relevant modules: `src/core/release_gate_runtime.py`, `scripts/release_gate_runtime.py`, `Makefile`, `docs/RELEASING.md`
