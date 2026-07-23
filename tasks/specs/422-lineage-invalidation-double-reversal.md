---
task_id: TASK-422
retrieval:
  kind: task-spec
  status: active
  canonical: true
  supersedes: []
  superseded_by: null
---

# TASK-422: Guard lineage-repair evidence invalidation against double-reversal

## Problem Statement

Split and merge repairs load active trend evidence without a row lock, mark each
row invalid in memory, and unconditionally apply a compensating restatement.
Two repairs or a repair racing Tier-2 reconciliation can therefore both observe
the same active row and reverse its original log-odds delta twice.

## Inputs

- `INTAKE-0068` and the `TASK-422` backlog entry
- `src/processing/event_lineage.py`
- The existing guarded invalidation pattern in
  `src/processing/trend_impact_reconciliation.py`
- Evidence/restatement contracts in `docs/ARCHITECTURE.md` and
  `docs/DATA_MODEL.md`

## Outputs

- Lineage repair claims evidence invalidation atomically with a conditional
  `UPDATE ... WHERE is_invalidated IS FALSE RETURNING`.
- Only a successfully claimed evidence row receives a compensating restatement.
- Unit and PostgreSQL concurrency regressions pin the skip and single-winner
  behavior.
- Architecture and data-model docs describe claim-before-compensate semantics.

## Non-Goals

- Changing Tier-2 reconciliation, restatement math, or decay
- Adding locks to the active-evidence read query
- Redesigning split/merge replay or privileged-write API behavior

**Planning Gates**: `Required` — this task changes a concurrency-sensitive
belief-state repair path and requires PostgreSQL integration proof.

## Phase -1 / Pre-Implementation Gates

- `Simplicity Gate`: Duplicate the proven conditional claim in a lineage-owned
  companion module; do not introduce a shared abstraction for two private
  callers.
- `Anti-Abstraction Gate`: A shared helper is rejected because it would
  unnecessarily change the already-correct reconciliation path.
- `Integration-First Gate`:
  - Validation target: two database transactions attempt to claim the same
    evidence invalidation.
  - Exercises: PostgreSQL conditional update plus commit ordering; exactly one
    transaction succeeds.
- `Code Shape Gate`: Keep `event_lineage.py` structurally flat by placing the
  claim primitive and new regressions in focused, lineage-owned modules.
- Hotspot Outcome: keep-flat-with-rationale — neither production file is
  allowlisted; the reconciliation module remains untouched and the lineage
  module receives only the claim call.
- `Determinism Gate`: Triggered — one evidence id must produce at most one
  successful invalidation claim and one compensation.
- `LLM Budget/Safety Gate`: Not applicable — no LLM behavior changes.
- `Observability Gate`: Existing lineage details continue to report only the
  evidence ids actually invalidated.

## Acceptance Criteria

- [ ] Lineage repair uses an atomic conditional claim and compensates only
  successfully claimed evidence rows.
- [ ] A lost invalidation claim does not mutate the in-memory evidence row,
  append a restatement, or report the evidence id as invalidated.
- [ ] PostgreSQL concurrency coverage proves exactly one of two claims succeeds.
- [ ] Tier-2 reconciliation code and behavior remain unchanged.
- [ ] Documentation and canonical full local gate pass.

## Validation

- Focused lineage unit tests
- PostgreSQL concurrency integration test
- `make typecheck`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`
