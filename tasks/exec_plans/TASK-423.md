# TASK-423: Decide and fix decay-clock reset on evidence writes

## Status

- Owner: Codex
- Started: 2026-07-26
- Current state: In progress
- Planning Gates: Required — probability math, schema migration, and two
  allowlisted production hotspots are in scope.

## Goal (1-3 lines)

Separate the decay clock from the general trend modification timestamp so
evidence and restatement writes cannot discard decay accrued since the last
scheduled tick. Preserve the documented exponential-decay contract and
runtime/projection parity.

## Inputs

- Spec/backlog references: `TASK-423` in `tasks/BACKLOG.md`, promoted from
  `INTAKE-0065`
- Runtime/code touchpoints: `src/core/trend_engine.py`,
  `src/core/trend_state.py`, `src/storage/models.py`, Alembic, probability
  tests, and architecture/data-model docs
- Preconditions/dependencies: current active state-version contract and
  chronological restatement projection behavior

## Outputs

- Expected behavior/artifacts: a persisted decay-only timestamp, safe
  backfill, state-activation reset semantics, and decay writes that advance
  the decay clock independently of ordinary trend updates
- Validation evidence: probability-math unit tests, model/migration tests,
  Docker integration proof, type checking, local review, and the full local
  gate

## Non-Goals

- Explicitly excluded work: changing evidence weights, half-lives, probability
  formulas, trend priors, or the evidence scoring-version contract

## Scope

- In scope: `Trend.last_decayed_at`, migration/backfill, decay reads/writes,
  state activation, tests, and operator/design documentation
- Out of scope: unrelated mock-tolerance cleanup from `INTAKE-0066` and
  catalog-wide half-life calibration

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: add `trends.last_decayed_at`, backfill
  it from `updated_at`, use it exclusively as the elapsed-decay origin, and
  reset it whenever a new trend state is activated. Evidence/restatement
  writes may continue updating `updated_at` without erasing pending decay.
- Rejected simpler alternative: merely documenting decay-since-last-write
  would preserve the known systematic under-decay and remain inconsistent
  with chronological projection rebuilds. Applying decay opportunistically
  before evidence writes would add timestamp-order and concurrency coupling
  while still overloading `updated_at`.
- First integration proof: exercise scheduled decay against a real Postgres
  trend whose `updated_at` was advanced by an intervening mutation while
  `last_decayed_at` remained at the earlier decay boundary.
- Hotspot Outcome: reduce — extract serialized decay/delta mutation into the
  single-owner `trend_delta_state.py` module, move `SourceType` out of the
  legacy aggregate model module, and remove stale function-size/complexity
  exceptions without increasing either allowlisted file maximum.
- Waivers:
  - No scoring math-version bump because this restores the documented v1
    exponential-decay schedule; it does not change the evidence delta formula
    or persisted factorization inputs.
  - Automated local review was unavailable after the canonical fallback chain
    (Claude OAuth expired, Codex timed out at 180 seconds, Gemini rejected the
    client tier). Manual adversarial review covered mutation lock ordering,
    timestamp monotonicity, runtime/projection parity, migration ordering, and
    every `apply_log_odds_delta` caller.

## Plan (Keep Updated)

1. [x] Preflight: validate the promoted task, planning gates, branch, callers,
   and current runtime/projection behavior.
2. [x] Implement the decay-only timestamp, migration/backfill, activation
   reset, and runtime reads/writes.
3. [x] Add focused unit/model/migration/integration coverage and update docs.
4. [ ] Run targeted validation, type checking, integration proof, local review,
   full local gate, and canonical finish/lifecycle verification.

## Decisions (Timestamped)

- 2026-07-26: Use a dedicated persisted decay clock rather than redefining
  `updated_at`; the latter is a general mutation/audit timestamp and is written
  by evidence, restatement, and activation paths.
- 2026-07-26: Backfill existing rows from `updated_at`; earlier lost elapsed
  time cannot be reconstructed safely from current state, so the migration
  must not invent historical decay.
- 2026-07-26: Serialize trend mutations before inserting evidence/restatement
  child rows. The first Postgres concurrency proof exposed a lock-order
  deadlock when two child inserts acquired foreign-key locks before either
  transaction acquired the trend row lock.
- 2026-07-26: The strict code-health ratchet rejected structural growth in
  modified hotspots and tests. Extract the new mutation owner and place new
  regression suites in focused files so every modified Python file is flat or
  improved against `main`.

## Risks / Foot-guns

- State activation could inherit an old decay boundary -> set
  `last_decayed_at` to the activation timestamp with the new starting state.
- A nullable migration window could reach runtime -> backfill before enforcing
  `NOT NULL` and provide matching application/server defaults.
- Runtime and active state-version values could diverge -> retain the existing
  serialized row-lock update and continue updating both log-odds copies.
- An evidence write could still alter the clock indirectly -> regression-test
  that general `updated_at` changes do not affect `apply_decay` elapsed time.

## Validation Commands

- `uv run --no-sync pytest tests/unit/core/test_trend_engine.py tests/unit/core/test_trend_state.py tests/unit/storage/test_model_metadata.py -q`
- `make typecheck`
- `uv run --no-sync pytest tests/unit/ -v -m unit`
- `make test-integration-docker`
- `uv run --no-sync horadus tasks local-review --format json`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: `tasks/BACKLOG.md` (`TASK-423`)
- Relevant modules: `src/core/trend_engine.py`,
  `src/core/trend_restatement.py`, `src/core/trend_state.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
- Validation: focused unit set `129 passed`; Docker integration
  `23 passed` with migration/autogenerate parity; `make agent-check` passed
  including `2768 passed, 121 deselected`.
