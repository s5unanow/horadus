# Environment Variables

**Last Verified**: 2026-02-16

This document lists environment variables used by the Horadus backend.

## Core Runtime (Required)

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | Async PostgreSQL URL for app runtime. | `postgresql+asyncpg://geoint:password@postgres:5432/geoint` |
| `CELERY_BROKER_URL` | Redis URL for Celery broker. | `redis://redis:6379/1` |
| `CELERY_RESULT_BACKEND` | Redis URL for Celery result backend. | `redis://redis:6379/2` |
| `OPENAI_API_KEY` | OpenAI key used for embeddings/classification/reporting. | `sk-...` |

## API and Security

| Variable | Default | Notes |
|----------|---------|-------|
| `API_HOST` | `0.0.0.0` | API bind host. |
| `API_PORT` | `8000` | API bind port. |
| `API_RELOAD` | `true` | Set `false` in production. |
| `ENVIRONMENT` | `development` | Use `production` in deployed environments. |
| `API_AUTH_ENABLED` | `false` | Enables API key auth middleware. |
| `API_KEYS` | empty | Comma-separated accepted API keys. |
| `API_ADMIN_KEY` | empty | Required for key-management endpoints. |
| `API_RATE_LIMIT_PER_MINUTE` | `120` | Per-key request budget. |
| `API_RATE_LIMIT_WINDOW_SECONDS` | `60` | Distributed rate-limit window size. |
| `API_RATE_LIMIT_STRATEGY` | `fixed_window` | Rate-limit algorithm (`fixed_window` or `sliding_window`). |
| `API_RATE_LIMIT_REDIS_PREFIX` | `horadus:api_rate_limit` | Redis key prefix for per-key rate-limit buckets. |
| `API_KEYS_PERSIST_PATH` | empty | Optional file path for persisted runtime API key metadata. |
| `CORS_ORIGINS` | local origins | Comma-separated origin list. |
| `SECRET_KEY` | `dev-secret-key-change-in-production` | Signing secret; set a high-entropy value in production. |

Rate-limit strategy guidance:
- `fixed_window` (default): lowest Redis/memory overhead and easiest operator reasoning, but allows boundary bursts near window rollover.
- `sliding_window`: smoother request pacing and stronger burst suppression across minute boundaries, with slightly higher Redis CPU/memory cost.
- Recommended production default remains `fixed_window` unless boundary-burst behavior materially impacts your workload.

## Model and Processing Controls

| Variable | Default | Notes |
|----------|---------|-------|
| `LLM_PRIMARY_PROVIDER` | `openai` | Provider label used for primary LLM routing/logging. |
| `LLM_PRIMARY_BASE_URL` | empty | Optional OpenAI-compatible base URL for primary calls. |
| `LLM_SECONDARY_PROVIDER` | empty | Optional secondary provider label for failover logging. |
| `LLM_SECONDARY_BASE_URL` | empty | Optional OpenAI-compatible base URL for secondary failover calls. |
| `LLM_SECONDARY_API_KEY` | empty | Optional API key override for secondary failover provider. |
| `LLM_TIER1_MODEL` | `gpt-4.1-nano` | Tier-1 relevance filtering model. |
| `LLM_TIER1_SECONDARY_MODEL` | empty | Optional Tier-1 failover model used on 429/5xx/timeout. |
| `LLM_TIER2_MODEL` | `gpt-4.1-mini` | Tier-2 extraction/classification model. |
| `LLM_TIER2_SECONDARY_MODEL` | empty | Optional Tier-2 failover model used on 429/5xx/timeout. |
| `LLM_REPORT_MODEL` | `gpt-4.1-mini` | Weekly/monthly report narrative model. |
| `LLM_REPORT_API_MODE` | `chat_completions` | Report narrative API mode (`chat_completions` or pilot `responses`). |
| `NARRATIVE_GROUNDING_MAX_UNSUPPORTED_CLAIMS` | `0` | Maximum unsupported deterministic narrative claims allowed before fallback. |
| `NARRATIVE_GROUNDING_NUMERIC_TOLERANCE` | `0.05` | Absolute tolerance used by numeric grounding checks against structured evidence payloads. |
| `LLM_RETROSPECTIVE_MODEL` | `gpt-4.1-mini` | Retrospective narrative model. |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding generation model. |
| `EMBEDDING_BATCH_SIZE` | `32` | Max texts per embedding request. |
| `EMBEDDING_CACHE_MAX_SIZE` | `2048` | Max in-memory embedding cache entries (LRU-evicted). |
| `VECTOR_REVALIDATION_CADENCE_DAYS` | `30` | Target days-between ANN strategy revalidation benchmark runs. |
| `VECTOR_REVALIDATION_DATASET_GROWTH_PCT` | `20` | Trigger revalidation when benchmark dataset/profile grows by this percent. |
| `LLM_TIER1_BATCH_SIZE` | `10` | Max items per tier-1 call. |
| `LLM_ROUTE_RETRY_ATTEMPTS` | `2` | Retry attempts per LLM route before failover/final failure. |
| `LLM_ROUTE_RETRY_BACKOFF_SECONDS` | `0.25` | Base retry delay in seconds (linear by attempt). |
| `LLM_SEMANTIC_CACHE_ENABLED` | `false` | Enables Redis-backed semantic response cache for Tier-1/Tier-2. |
| `LLM_SEMANTIC_CACHE_TTL_SECONDS` | `21600` | TTL for semantic cache entries (seconds). |
| `LLM_SEMANTIC_CACHE_MAX_ENTRIES` | `10000` | Best-effort max entries per stage before oldest eviction. |
| `LLM_SEMANTIC_CACHE_REDIS_PREFIX` | `horadus:llm_semantic_cache` | Redis key prefix for semantic cache data/indexes. |
| `PROCESSING_PIPELINE_BATCH_SIZE` | `200` | Pending items handled per pipeline run. |
| `PROCESSING_STALE_TIMEOUT_MINUTES` | `30` | Age threshold before stale `processing` items are reset to `pending`. |

## Cost and Safety Controls

| Variable | Default | Notes |
|----------|---------|-------|
| `TIER1_MAX_DAILY_CALLS` | `1000` | `0` means unlimited. |
| `TIER2_MAX_DAILY_CALLS` | `200` | `0` means unlimited. |
| `EMBEDDING_MAX_DAILY_CALLS` | `500` | `0` means unlimited. |
| `DAILY_COST_LIMIT_USD` | `5.0` | Hard stop threshold for total LLM cost. |
| `COST_ALERT_THRESHOLD_PCT` | `80` | Alert threshold as percent of daily budget. |
| `CALIBRATION_DRIFT_MIN_RESOLVED_OUTCOMES` | `20` | Minimum scored outcomes before drift alerts trigger. |
| `CALIBRATION_DRIFT_BRIER_WARN_THRESHOLD` | `0.20` | Warning threshold for mean Brier score drift. |
| `CALIBRATION_DRIFT_BRIER_CRITICAL_THRESHOLD` | `0.30` | Critical threshold for mean Brier score drift. |
| `CALIBRATION_DRIFT_BUCKET_ERROR_WARN_THRESHOLD` | `0.15` | Warning threshold for max bucket calibration error. |
| `CALIBRATION_DRIFT_BUCKET_ERROR_CRITICAL_THRESHOLD` | `0.25` | Critical threshold for max bucket calibration error. |
| `CALIBRATION_DRIFT_WEBHOOK_URL` | *(empty)* | Optional webhook URL for outbound calibration drift alerts. |
| `CALIBRATION_DRIFT_WEBHOOK_TIMEOUT_SECONDS` | `5.0` | HTTP timeout (seconds) for webhook delivery calls. |
| `CALIBRATION_DRIFT_WEBHOOK_MAX_RETRIES` | `3` | Retry attempts for transient webhook failures. |
| `CALIBRATION_DRIFT_WEBHOOK_BACKOFF_SECONDS` | `1.0` | Initial retry backoff delay in seconds (exponential). |
| `CALIBRATION_COVERAGE_MIN_RESOLVED_PER_TREND` | `5` | Minimum resolved outcomes per trend in dashboard window. |
| `CALIBRATION_COVERAGE_MIN_RESOLVED_RATIO` | `0.50` | Minimum resolved/total ratio before coverage alerts are raised. |

## Scheduling and Workers

| Variable | Default | Notes |
|----------|---------|-------|
| `ENABLE_RSS_INGESTION` | `true` | Enables periodic RSS collection. |
| `ENABLE_GDELT_INGESTION` | `true` | Enables periodic GDELT collection. |
| `ENABLE_TELEGRAM_INGESTION` | `false` | Enables Telegram ingestion path. |
| `ENABLE_PROCESSING_PIPELINE` | `true` | Enables processing task execution. |
| `WORKER_HEARTBEAT_REDIS_KEY` | `horadus:worker:last_activity` | Redis key where workers publish latest activity heartbeat payload. |
| `WORKER_HEARTBEAT_STALE_SECONDS` | `900` | Age threshold after which worker heartbeat is treated as stale in health checks. |
| `WORKER_HEARTBEAT_TTL_SECONDS` | `3600` | TTL for worker heartbeat key in Redis. |
| `RSS_COLLECTION_INTERVAL` | `360` | In minutes. |
| `GDELT_COLLECTION_INTERVAL` | `360` | In minutes. |
| `INGESTION_WINDOW_OVERLAP_SECONDS` | `300` | Overlap applied between ingestion windows to reduce gap risk on delayed runs/restarts. |
| `SOURCE_FRESHNESS_ALERT_MULTIPLIER` | `2.0` | Marks a source stale when `last_fetched_at` age exceeds `collector_interval × multiplier`. |
| `SOURCE_FRESHNESS_CHECK_INTERVAL_MINUTES` | `30` | Beat cadence for `workers.check_source_freshness` stale-source scan. |
| `SOURCE_FRESHNESS_MAX_CATCHUP_DISPATCHES` | `2` | Maximum bounded collector catch-up dispatches emitted per freshness check run. |
| `RSS_COLLECTOR_TOTAL_TIMEOUT_SECONDS` | `300` | Total timeout budget per RSS feed collection run. |
| `GDELT_COLLECTOR_TOTAL_TIMEOUT_SECONDS` | `300` | Total timeout budget per GDELT query collection run. |
| `COLLECTOR_TASK_MAX_RETRIES` | `3` | Bounded requeue attempts for transient collector outages. |
| `COLLECTOR_RETRY_BACKOFF_MAX_SECONDS` | `300` | Maximum backoff delay between collector task retries. |
| `TREND_SNAPSHOT_INTERVAL_MINUTES` | `60` | Snapshot cadence. |
| `PROCESS_PENDING_INTERVAL_MINUTES` | `15` | Cadence for periodic `workers.process_pending_items` beat schedule. |
| `PROCESSING_DISPATCH_MAX_IN_FLIGHT` | `1` | Ingestion-triggered dispatch throttles when in-flight processing tasks reach this count. |
| `PROCESSING_DISPATCH_LOCK_TTL_SECONDS` | `30` | Redis lock TTL used to deduplicate ingestion-triggered dispatch fan-out. |
| `PROCESSING_DISPATCH_MIN_BUDGET_HEADROOM_PCT` | `10` | Low-headroom threshold (%) where ingestion-triggered dispatch becomes less aggressive. |
| `PROCESSING_DISPATCH_LOW_HEADROOM_LIMIT` | `50` | Maximum ingestion-triggered dispatch `limit` while low-headroom throttling is active. |
| `PROCESSING_REAPER_INTERVAL_MINUTES` | `15` | Cadence for stale-processing recovery task. |
| `WEEKLY_REPORT_DAY_OF_WEEK` | `1` | UTC day (`0=Sun..6=Sat`). |
| `WEEKLY_REPORT_HOUR_UTC` | `7` | UTC hour. |
| `MONTHLY_REPORT_DAY_OF_MONTH` | `1` | UTC day of month (`1..28`). |
| `MONTHLY_REPORT_HOUR_UTC` | `8` | UTC hour. |

## 6-Hour Mode Profile

Recommended baseline for low-frequency operation (poll every 6 hours, daily review):

```dotenv
RSS_COLLECTION_INTERVAL=360
GDELT_COLLECTION_INTERVAL=360
PROCESS_PENDING_INTERVAL_MINUTES=15
PROCESSING_PIPELINE_BATCH_SIZE=200
```

Source window defaults for this profile:
- RSS loader default: `default_max_items_per_fetch=200` (per-source override via each feed's `max_items_per_fetch`)
- GDELT loader default: `default_lookback_hours=12` (per-query override via each query's `lookback_hours`)

Tuning checklist:
- `PROCESSING_PIPELINE_BATCH_SIZE`: increase when backlog accumulates after each 6-hour ingest
- `PROCESS_PENDING_INTERVAL_MINUTES`: keep lower than collection interval to drain bursts predictably
- Worker concurrency: ensure processing workers can clear one collection burst before next poll
- Per-source caps: tune RSS `max_items_per_fetch` and GDELT `max_records_per_page`/`max_pages` for noisy sources

Manual outage recovery / catch-up steps are documented in `docs/LOW_FREQUENCY_MODE.md`.
Freshness status is available via `GET /api/v1/sources/freshness` and
`uv run horadus eval source-freshness`.
Collector failure policy is transient-vs-terminal classified; transient all-source
outages requeue up to `COLLECTOR_TASK_MAX_RETRIES`.

## Backup Operations

| Variable | Default | Notes |
|----------|---------|-------|
| `BACKUP_RETENTION_DAYS` | `14` | Delete backup files older than this many days (`0` disables age pruning). |
| `BACKUP_RETENTION_COUNT` | `30` | Keep only the newest N backups (`0` disables count pruning). |
| `VERIFY_BACKUP` | `true` | Run gzip/size validation immediately after backup creation. |
| `MIN_BACKUP_BYTES` | `1024` | Minimum compressed backup size accepted by backup/verify scripts. |
| `MAX_BACKUP_AGE_HOURS` | `30` | Maximum allowed age for latest backup during verification checks. |

## Logging

| Variable | Default | Notes |
|----------|---------|-------|
| `LOG_LEVEL` | `INFO` | Typical values: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `LOG_FORMAT` | `json` | Use `json` in production and `console` for local debugging. |
| `SQL_ECHO` | `false` | SQLAlchemy SQL logging toggle; keep `false` in production. |

## Tracing (OpenTelemetry)

| Variable | Default | Notes |
|----------|---------|-------|
| `OTEL_ENABLED` | `false` | Enables OpenTelemetry tracing bootstrap/instrumentation when `true`. |
| `OTEL_SERVICE_NAME` | `horadus-backend` | `service.name` resource attribute shown in trace backend. |
| `OTEL_SERVICE_NAMESPACE` | `horadus` | `service.namespace` resource attribute. |
| `OTEL_TRACES_SAMPLER_RATIO` | `1.0` | Trace sampling ratio (`0.0..1.0`). |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | empty | OTLP/HTTP traces endpoint (for example `http://localhost:4318/v1/traces`). |
| `OTEL_EXPORTER_OTLP_HEADERS` | empty | Optional comma-separated `key=value` headers for OTLP exporter auth/tenant routing. |

See `docs/TRACING.md` for local collector/viewer quickstart and context-propagation validation steps.

## Database and Redis (Supplemental)

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL_SYNC` | derived | Sync URL used by Alembic. |
| `DATABASE_POOL_SIZE` | `10` | SQLAlchemy async pool size. |
| `DATABASE_MAX_OVERFLOW` | `20` | SQLAlchemy max overflow connections. |
| `DATABASE_POOL_TIMEOUT_SECONDS` | `30` | Seconds to wait for a pooled DB connection before timeout. |
| `MIGRATION_PARITY_CHECK_ENABLED` | `true` | Enables runtime migration parity checks in startup and `/health`. |
| `MIGRATION_PARITY_STRICT_STARTUP` | `false` | Fails API startup when migration parity check is unhealthy. |
| `MIGRATION_GATE_VALIDATE_AUTOGEN` | `true` | Release/integration migration-gate strictness. `true` runs `alembic check`; set `false` only for documented emergency bypass. |
| `REDIS_URL` | `redis://localhost:6379/0` | General Redis connection URL. |

## File-Based Secrets (`*_FILE`)

For containerized production, each sensitive variable also supports a file path variant.
When `<VAR>_FILE` is set, Horadus reads the file content and uses it as `<VAR>`.

Production guidance:

- Treat `.env` as non-secret configuration only.
- Keep secret values in mounted files and set only `*_FILE` variables.
- Use `docs/SECRETS_RUNBOOK.md` for host layout, permissions, rotation, and rollback.

Supported file-backed variables:

| Variable | File Variant |
|----------|--------------|
| `DATABASE_URL` | `DATABASE_URL_FILE` |
| `DATABASE_URL_SYNC` | `DATABASE_URL_SYNC_FILE` |
| `REDIS_URL` | `REDIS_URL_FILE` |
| `SECRET_KEY` | `SECRET_KEY_FILE` |
| `API_KEY` | `API_KEY_FILE` |
| `API_KEYS` | `API_KEYS_FILE` |
| `API_ADMIN_KEY` | `API_ADMIN_KEY_FILE` |
| `OPENAI_API_KEY` | `OPENAI_API_KEY_FILE` |
| `LLM_SECONDARY_API_KEY` | `LLM_SECONDARY_API_KEY_FILE` |
| `CELERY_BROKER_URL` | `CELERY_BROKER_URL_FILE` |
| `CELERY_RESULT_BACKEND` | `CELERY_RESULT_BACKEND_FILE` |

`API_KEYS_FILE` supports newline-separated and/or comma-separated values.

For managed cloud secret-store integrations (AWS/GCP/Azure/Vault), see
`docs/SECRETS_BACKENDS.md`.

## Local Reference

Use `.env.example` as the source template:

```bash
cp .env.example .env
```
