# TASK-238: Prioritize Tier-2 Budget with Value-of-Information Scheduling

## Status

- Owner: Codex
- Started: 2026-03-26
- Current state: In progress (implementation + validation complete; shipping in progress)
- Planning Gates: Required — estimate exceeds 2 hours and the task spans processing, storage-adjacent runtime behavior, tests, and docs

## Goal (1-3 lines)

Add a deterministic Tier-2 prioritization layer so budget-constrained processing
spends scarce Tier-2 capacity on the items most likely to reduce uncertainty or
materially change tracked forecasts, while preserving safe FIFO fallback.

## Inputs

- Spec/backlog references: `tasks/CURRENT_SPRINT.md`, `tasks/BACKLOG.md` (`TASK-238`)
- Runtime/code touchpoints: `src/processing/pipeline_orchestrator.py`, new Tier-2 scheduling helper(s), `src/processing/cost_tracker.py`, `src/core/observability.py`, `tests/unit/processing/`, `docs/ARCHITECTURE.md`
- Preconditions/dependencies: guarded task start from synced `main`; keep deterministic log-odds math unchanged and treat LLM extraction as unchanged input to the scheduler

## Outputs

- Expected behavior/artifacts:
  - deterministic Tier-2 candidate scoring from bounded runtime signals
  - pressure-aware reordering with bounded fairness reserve and starvation safety
  - explainable scheduling factors surfaced in logs and/or metrics
  - FIFO fallback when scheduling inputs are unavailable or pressure is absent
- Validation evidence:
  - targeted scheduler/pipeline unit coverage
  - `make agent-check`
  - `make test-integration-docker`
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Explicitly excluded work:
  - changing Tier-1 or Tier-2 prompt behavior
  - changing trend-delta math or evidence application semantics
  - adding a new operator API surface for schedule inspection unless the existing log/metric path proves insufficient

## Scope

- In scope:
  - compute a deterministic Tier-2 priority score from available runtime signals
  - detect budget pressure from current Tier-2 budget headroom / call capacity
  - reorder Tier-2 candidate execution only when pressure exists
  - reserve bounded fairness slots for late-arriving or low-volume high-impact candidates
  - document the new scheduling behavior
- Out of scope:
  - persistent queue/schema changes unless implementation proves they are required
  - changing collector dispatch policy beyond using existing budget signals

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - keep the policy in deterministic Python, extract the scoring/interleaving logic into a focused helper module, and limit pipeline changes to candidate staging/order selection
- Rejected simpler alternative:
  - keep pure FIFO and only throttle dispatch harder; that does not choose which Tier-2 candidates consume the remaining budget
- First integration proof:
  - `make test-integration-docker`
- Waivers:
  - `horadus tasks local-review --format json` was not usable pre-commit because the command only reviews committed branch diffs and reported `No branch diff exists` on the working tree state.

## Plan (Keep Updated)

1. Preflight (branch, tests, context) — completed
2. Implement — completed
3. Validate — completed
4. Ship (PR, checks, merge, main sync) — in progress

## Decisions (Timestamped)

- 2026-03-26: Treat this task as planning-gated and keep a living exec plan because it materially changes the oversized pipeline orchestrator and spans multiple runtime surfaces.
- 2026-03-26: Prefer a new scheduler helper module over growing `src/processing/pipeline_orchestrator.py`; reason: the orchestrator is already above the default code-shape budget and should only own orchestration glue.
- 2026-03-26: Split Tier-2 staging/finalization and VOI ordering into dedicated helpers after the first pass tripped repo code-shape gates; reason: preserve the new behavior without increasing the hotspot allowlist.

## Risks / Foot-guns

- Reordering too aggressively could starve older or low-volume items -> add bounded fairness interleaving plus queue-age tie-breakers.
- Pressure detection could misfire when budget inputs are incomplete -> fail back to original FIFO order unless pressure can be established deterministically.
- Explainability could regress into opaque score soup -> log normalized factors and the selected pressure/fairness path explicitly.

## Validation Commands

- `uv run --no-sync pytest tests/unit/processing/test_tier2_voi_scheduler.py -v -m unit`
- `uv run --no-sync pytest tests/unit/processing/test_pipeline_orchestrator.py -v -m unit`
- `make agent-check`
- `make test-integration-docker`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: backlog-only task
- Relevant modules: `src/processing/pipeline_orchestrator.py`, `src/processing/cost_tracker.py`, `src/core/observability.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
