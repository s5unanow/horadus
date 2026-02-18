# TASK-077 Cost-First Pipeline Ordering Checklist

Date: 2026-02-18  
Branch: `codex/task-077-cost-first-pipeline-ordering`  
Task: `TASK-077` Cost-First Pipeline Ordering `[REQUIRES_HUMAN]`

## Purpose

Capture the required human-executed refactor and sign-off to ensure Tier-1
relevance filtering runs before embedding/clustering for new pending raw items.

## Runtime Verification (After Manual Refactor)

Runtime now executes Tier-1 before embedding/clustering for new pending items:
- `src/processing/pipeline_orchestrator.py:287` `_prepare_item_for_tier1` performs prechecks only (dedup/content/language)
- `src/processing/pipeline_orchestrator.py:418` `_classify_tier1_prepared_items` runs batch Tier-1 classification
- `src/processing/pipeline_orchestrator.py:497` Tier-1 noise exits before embedding/cluster
- `src/processing/pipeline_orchestrator.py:516` embedding now occurs only on Tier-1 pass
- `src/processing/pipeline_orchestrator.py:527` clustering now occurs only on Tier-1 pass

## Human Execution Scope

`TASK-077` is `[REQUIRES_HUMAN]`. Manual implementation and approval were completed.

## Manual Implementation Checklist

- [x] Refactor prepare/classify flow so Tier-1 runs before embedding+clustering for new pending items.
- [x] Preserve duplicate suppression behavior and idempotency guarantees.
- [x] Ensure Tier-1 noise path does not call embedding API and does not cluster.
- [x] Preserve usage/counter accounting (`scanned`, `processed`, `noise`, `classified`, `embedding_api_calls`, cost fields).
- [x] Keep Tier-1 batch behavior and per-item fallback behavior deterministic.
- [x] Keep unsupported-language skip/defer behavior unchanged.

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
| Tier-1 runs before embedding/clustering | `src/processing/pipeline_orchestrator.py` reordered (`_prepare_item_for_tier1` + `_process_after_tier1`) | Complete |
| Duplicate suppression remains deterministic/idempotent | Unit suite pass (`tests/unit/processing`) with duplicate/noise/idempotent coverage | Complete |
| Tier-1 noise avoids embedding/clustering | Unit tests assert no embedding/cluster calls for Tier-1 noise paths | Complete |
| Metrics/cost accounting preserved | Unit tests and `PipelineRunResult` assertions remain green after reorder | Complete |
| Tests updated for new order | Updated orchestrator unit tests pass; integration run blocked by local DB auth mismatch | Complete (unit), Blocked (integration env) |

## Validation Commands (After Manual Implementation)

```bash
uv run --no-sync pytest tests/unit/processing/test_pipeline_orchestrator.py -q
uv run --no-sync pytest tests/unit/processing -q
uv run --no-sync pytest tests/unit/ -q
uv run --no-sync ruff check src/processing/pipeline_orchestrator.py tests/unit/processing/test_pipeline_orchestrator.py
uv run --no-sync mypy src/processing/pipeline_orchestrator.py
```

## Final Task-Level Sign-Off

- Reviewer name: `s5una`
- Review date: `2026-02-18`
- Decision: `Approved` (`Approved` / `Blocked`)
- Blocking issues (if any): `Integration test execution blocked locally by Postgres auth mismatch (asyncpg InvalidPasswordError)`
- Notes for sprint record: `Cost-first ordering implemented; Tier-1 now gates embedding/clustering; unit/lint/type checks passed.`
