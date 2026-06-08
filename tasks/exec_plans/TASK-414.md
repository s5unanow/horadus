# TASK-414: Fix Tier-2 trend keyword collisions and wrong-direction indicators

## Status

- Owner: Codex
- Started: 2026-06-08
- Current state: Done - local validation passed; ready for ledger close and finish
- Planning Gates: Required - P0 trend-mapping quality task touching probability-driving trend config semantics.

## Goal

Remove known deterministic trend-impact mapping defects where ambiguous or
wrong-direction indicator keywords can silently drop or reverse probability
deltas.

## Inputs

- Spec/backlog references: `TASK-414`, promoted from `INTAKE-0047`
- Runtime/code touchpoints: `config/trends/*.yaml`, `src/processing/trend_impact_mapping.py`
- Preconditions/dependencies: `TASK-412` go-live Tier 2 quality blocker is complete; `TASK-413` cleared the unrelated `pip` dependency-audit blocker.

## Outputs

- Expected behavior/artifacts: corrected trend indicator keyword placement and
  focused regression tests for affected mapping rows.
- Validation evidence: targeted mapping tests, taxonomy validation, eval audit,
  agent/local gates, and lifecycle completion.

## Non-Goals

- Redesign mapper scoring.
- Rebalance trend priors, decay, or indicator weights.
- Broaden keyword quality cleanup beyond the specific `INTAKE-0047` defects.

## Scope

- In scope: listed keyword removals, relocations, and scoped replacements plus
  regression coverage.
- Out of scope: empirical corpus replay, new trend linter, external prior
  calibration, and Middle East/Hormuz coverage.

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: patch only the listed mis-bucketed or
  ambiguous keywords and preserve coverage through existing or narrowly scoped
  replacement phrases.
- Rejected simpler alternative: leave as documented debt, because the defects
  affect deterministic probability-delta mapping.
- First integration proof: targeted unit coverage for mapping behavior; Docker
  integration is required by the context pack and will be run.
- Hotspot Outcome: keep-flat-with-rationale - no allowlisted oversized Python
  hotspot is expected to be materially changed.
- Waivers: docs updates are N/A unless operator-facing trend semantics change
  beyond config keyword placement.

## Plan

1. Preflight, branch, and context collection.
2. Patch trend config keywords.
3. Add focused mapping regression tests.
4. Run targeted validation and full local gate.
5. Close ledgers and ship through Horadus finish/lifecycle.

## Decisions

- 2026-06-08: Use config-only fixes plus regression tests before considering
  mapper scoring changes, because the intake lists concrete taxonomy defects.
- 2026-06-08: Replayed the code/config/test patch from the abandoned local
  `TASK-413` scratch branch after `TASK-413` was reassigned to the dependency
  audit blocker and merged.
- 2026-06-08: No docs update required because behavior change is limited to
  internal trend keyword mapping config and pinned tests.
- 2026-06-08: Addressed PR review on export-tax easing by replacing the generic
  de-escalatory `export tax` keyword with scoped tightening phrases and adding
  explicit tax-reduction phrases/tests for market-access easing.
- 2026-06-08: Moved new keyword-collision regression tests into a dedicated test
  module to avoid growing the existing broad mapping test file.

## Risks / Foot-guns

- Removing a keyword could reduce intended recall -> keep the phrase in the
  correct indicator when the intake says coverage should survive.
- Adding replacement phrases could overfit to a single headline -> use scoped
  semantic phrases rather than proper-noun event fragments.
- Full live LLM benchmark could incur cost -> rely on offline taxonomy/eval
  gates unless prompt/model behavior changes.

## Validation Commands

- `uv run --no-sync pytest tests/unit/processing/test_trend_impact_mapping.py -v -m unit` (passed 2026-06-08)
- `uv run --no-sync horadus eval validate-taxonomy --trend-config-dir config/trends --tier1-trend-mode subset` (passed 2026-06-08)
- `uv run --no-sync horadus eval audit --fail-on-warnings` (passed 2026-06-08)
- `python scripts/check_code_shape.py` (passed 2026-06-08)
- `make agent-check` (passed 2026-06-08)
- `make test-integration-docker` (passed 2026-06-08)
- `uv run --no-sync horadus tasks local-gate --full` (passed 2026-06-08)

## Notes / Links

- Intake: `INTAKE-0047`
- Relevant modules: `src/processing/trend_impact_mapping.py`, `config/trends/*.yaml`
