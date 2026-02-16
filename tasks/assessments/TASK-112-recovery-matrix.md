# TASK-112 Recovery Matrix (TASK-086..TASK-107)

Date: 2026-02-16  
Branch: `codex/task-112-recover-task061`  
Source branch audited: `origin/codex/task-061-recency-decay`

## Legend

- **Recovered**: committed artifacts from `task-061` are now restored on `main` lineage in this branch.
- **Partial (reconstructed)**: critical missing files were reconstructed from local artifacts, but some acceptance-scope pieces remain.
- **Deferred**: required artifacts were never committed on `task-061` and were not fully reconstructed in TASK-112.

## Per-task status

| Task | Status | Notes |
|---|---|---|
| TASK-086 | Recovered | Retry-before-failover restored (`src/processing/llm_failover.py`, unit tests). |
| TASK-087 | Recovered | Budget/safety guardrails for report+retrospective paths restored (`src/core/report_generator.py`, `src/core/retrospective_analyzer.py`). |
| TASK-088 | Recovered | Legacy single-item path removal preserved in orchestrator/tests. |
| TASK-089 | Recovered | Strict structured output + fallback behavior restored in Tier-1/Tier-2 classifiers/tests. |
| TASK-090 | Recovered | Shared invocation adapter reconstructed (`src/processing/llm_invocation_adapter.py`) and failover wiring restored. |
| TASK-091 | Deferred | CLI flag plumbing exists, but benchmark runtime mode implementation remains incomplete (see TASK-113). |
| TASK-092 | Partial (reconstructed) | Tracing module/tests/runbook restored (`src/core/tracing.py`, `tests/unit/core/test_tracing.py`, `docs/TRACING.md`); dependency/bootstrap parity remains (see TASK-115). |
| TASK-093 | Deferred | Vector revalidation artifacts not fully recovered (runbook + summary persistence path deferred to TASK-113). |
| TASK-094 | Recovered | Pipeline cost-payload parity restored via orchestrator/worker payload and tests. |
| TASK-095 | Deferred | Docs freshness checker + CI/local gate artifacts missing from committed source and deferred to TASK-114. |
| TASK-096 | Recovered | Unified LLM policy/pricing/failover taxonomy restored (`llm_policy`, `llm_pricing`, `llm_failover`). |
| TASK-097 | Recovered | Sliding-window limiter strategy restored in API key manager and tests. |
| TASK-098 | Recovered | Cross-worker semantic cache restored (`semantic_cache`) with Tier-1/Tier-2 integration/tests. |
| TASK-099 | Recovered | Backpressure-aware processing dispatch logic restored in worker scheduling/tests. |
| TASK-100 | Partial (reconstructed) | Lineage columns/migrations/reporting command restored (`embedding_lineage`, migrations `0010`/`0012`); remaining runtime parity items deferred to TASK-115. |
| TASK-101 | Recovered | Multilingual policy behavior restored in orchestrator/classifier flow and tests. |
| TASK-102 | Partial (reconstructed) | Grounding evaluator + metadata columns/migrations restored (`narrative_grounding`, migration `0011`); remaining API parity deferred to TASK-115. |
| TASK-103 | Recovered | Six-hour operating profile defaults/docs restored (`.env.example`, config/docs updates). |
| TASK-104 | Recovered | Ingestion watermark/overlap handling restored in collectors and schema migration (`0012`). |
| TASK-105 | Recovered | Source freshness SLO checks, worker task, API/CLI surfaces, and tests restored. |
| TASK-106 | Recovered | Collector retry/timeout hardening restored in ingestion/worker/config/tests. |
| TASK-107 | Recovered (superseded) | Dependency governance objective already superseded by merged TASK-110 hard workflow policy. |

## Validation executed

Targeted changed-area unit test suite passed:

```bash
uv run --no-sync pytest \
  tests/unit/api/test_sources.py \
  tests/unit/core/test_api_key_manager.py \
  tests/unit/core/test_config.py \
  tests/unit/core/test_source_freshness.py \
  tests/unit/core/test_embedding_lineage.py \
  tests/unit/core/test_narrative_grounding.py \
  tests/unit/core/test_tracing.py \
  tests/unit/ingestion/test_gdelt_client.py \
  tests/unit/ingestion/test_rss_collector.py \
  tests/unit/processing/test_event_clusterer.py \
  tests/unit/processing/test_llm_failover.py \
  tests/unit/processing/test_llm_invocation_adapter.py \
  tests/unit/processing/test_llm_policy.py \
  tests/unit/processing/test_llm_pricing.py \
  tests/unit/processing/test_pipeline_orchestrator.py \
  tests/unit/processing/test_semantic_cache.py \
  tests/unit/processing/test_tier1_classifier.py \
  tests/unit/processing/test_tier2_classifier.py \
  tests/unit/storage/test_model_metadata.py \
  tests/unit/test_cli.py \
  tests/unit/workers/test_celery_setup.py -q
```

Result: `186 passed`.
