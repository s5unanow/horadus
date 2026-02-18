# TASK-077 Cost-First Pipeline Ordering Checklist

Date: 2026-02-18  
Branch: `codex/task-077-cost-first-pipeline-ordering`  
Task: `TASK-077` Cost-First Pipeline Ordering `[REQUIRES_HUMAN]`

## Purpose

Capture the required human-executed refactor and sign-off to ensure Tier-1
relevance filtering runs before embedding/clustering for new pending raw items.

## Runtime Baseline (Before Manual Refactor)

Current runtime still performs embedding and clustering before Tier-1:
- `src/processing/pipeline_orchestrator.py:355` embeds item content
- `src/processing/pipeline_orchestrator.py:370` clusters item to event
- `src/processing/pipeline_orchestrator.py:460` runs Tier-1 classification on prepared items
- `src/processing/pipeline_orchestrator.py:555` marks Tier-1 noise after embedding/clustering already happened

This means Tier-1 noise items can still incur embedding + clustering cost.

## Human Execution Scope

`TASK-077` is `[REQUIRES_HUMAN]`. Manual implementation and approval are required.
Agent work for this task is limited to checklist/runbook scaffolding.

## Manual Implementation Checklist

- [ ] Refactor prepare/classify flow so Tier-1 runs before embedding+clustering for new pending items.
- [ ] Preserve duplicate suppression behavior and idempotency guarantees.
- [ ] Ensure Tier-1 noise path does not call embedding API and does not cluster.
- [ ] Preserve usage/counter accounting (`scanned`, `processed`, `noise`, `classified`, `embedding_api_calls`, cost fields).
- [ ] Keep Tier-1 batch behavior and per-item fallback behavior deterministic.
- [ ] Keep unsupported-language skip/defer behavior unchanged.

## Suggested Code Touchpoints (Manual)

- `src/processing/pipeline_orchestrator.py`
  - split current `_prepare_item_for_tier1` responsibilities into:
    - pre-Tier1 eligibility/prechecks (dedup, content, language)
    - post-Tier1 heavy path (embed -> cluster -> suppression -> Tier-2)
  - keep run-result aggregation and usage counters semantically unchanged
- `tests/unit/processing/test_pipeline_orchestrator.py`
  - add/adjust tests that assert Tier-1 noise does not call embedding/clustering
  - add/adjust tests for mixed batches (Tier-1 pass + Tier-1 noise)
  - re-validate Tier-1 budget exceeded behavior in reordered flow
- `tests/integration/test_processing_pipeline.py`
  - add/adjust integration coverage that validates no embedding API usage for Tier-1 noise items
- `docs/ARCHITECTURE.md`
  - update processing flow diagram/order once runtime reorder is merged

## Acceptance Criteria Mapping

| Acceptance Criterion | Verification Evidence | Status |
|---|---|---|
| Tier-1 runs before embedding/clustering | Diff in `src/processing/pipeline_orchestrator.py` + tests | Pending |
| Duplicate suppression remains deterministic/idempotent | Existing + updated unit tests | Pending |
| Tier-1 noise avoids embedding/clustering | New/updated unit+integration assertions | Pending |
| Metrics/cost accounting preserved | Unit assertions on `PipelineRunResult` usage/counters | Pending |
| Tests updated for new order | Passing test outputs linked in PR | Pending |

## Validation Commands (After Manual Implementation)

```bash
pytest tests/unit/processing/test_pipeline_orchestrator.py -v
pytest tests/integration/test_processing_pipeline.py -v
pytest tests/ -v
```

## Final Task-Level Sign-Off

- Reviewer name: `TBD`
- Review date: `TBD`
- Decision: `Pending` (`Approved` / `Blocked`)
- Blocking issues (if any): `TBD`
- Notes for sprint record: `TBD`
