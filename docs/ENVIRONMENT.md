# Environment Variables

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
| `API_RATE_LIMIT_REDIS_PREFIX` | `horadus:api_rate_limit` | Redis key prefix for per-key rate-limit buckets. |
| `API_KEYS_PERSIST_PATH` | empty | Optional file path for persisted runtime API key metadata. |
| `CORS_ORIGINS` | local origins | Comma-separated origin list. |
| `SECRET_KEY` | `dev-secret-key-change-in-production` | Signing secret; set a high-entropy value in production. |

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
| `LLM_RETROSPECTIVE_MODEL` | `gpt-4.1-mini` | Retrospective narrative model. |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding generation model. |
| `EMBEDDING_BATCH_SIZE` | `32` | Max texts per embedding request. |
| `EMBEDDING_CACHE_MAX_SIZE` | `2048` | Max in-memory embedding cache entries (LRU-evicted). |
| `LLM_TIER1_BATCH_SIZE` | `10` | Max items per tier-1 call. |
| `PROCESSING_PIPELINE_BATCH_SIZE` | `50` | Pending items handled per pipeline run. |
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
| `RSS_COLLECTION_INTERVAL` | `30` | In minutes. |
| `GDELT_COLLECTION_INTERVAL` | `60` | In minutes. |
| `TREND_SNAPSHOT_INTERVAL_MINUTES` | `60` | Snapshot cadence. |
| `PROCESSING_REAPER_INTERVAL_MINUTES` | `15` | Cadence for stale-processing recovery task. |
| `WEEKLY_REPORT_DAY_OF_WEEK` | `1` | UTC day (`0=Sun..6=Sat`). |
| `WEEKLY_REPORT_HOUR_UTC` | `7` | UTC hour. |
| `MONTHLY_REPORT_DAY_OF_MONTH` | `1` | UTC day of month (`1..28`). |
| `MONTHLY_REPORT_HOUR_UTC` | `8` | UTC hour. |

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

## Database and Redis (Supplemental)

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL_SYNC` | derived | Sync URL used by Alembic. |
| `DATABASE_POOL_SIZE` | `10` | SQLAlchemy async pool size. |
| `DATABASE_MAX_OVERFLOW` | `20` | SQLAlchemy max overflow connections. |
| `DATABASE_POOL_TIMEOUT_SECONDS` | `30` | Seconds to wait for a pooled DB connection before timeout. |
| `REDIS_URL` | `redis://localhost:6379/0` | General Redis connection URL. |

## File-Based Secrets (`*_FILE`)

For containerized production, each sensitive variable also supports a file path variant.
When `<VAR>_FILE` is set, Horadus reads the file content and uses it as `<VAR>`.

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
