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
| `API_KEYS_PERSIST_PATH` | empty | Optional file path for persisted runtime API key metadata. |
| `CORS_ORIGINS` | local origins | Comma-separated origin list. |
| `SECRET_KEY` | `dev-secret-key-change-in-production` | Signing secret; set a high-entropy value in production. |

## Model and Processing Controls

| Variable | Default | Notes |
|----------|---------|-------|
| `LLM_TIER1_MODEL` | `gpt-4.1-nano` | Tier-1 relevance filtering model. |
| `LLM_TIER2_MODEL` | `gpt-4o-mini` | Tier-2 extraction/classification model. |
| `LLM_REPORT_MODEL` | `gpt-4o-mini` | Weekly/monthly report narrative model. |
| `LLM_RETROSPECTIVE_MODEL` | `gpt-4o-mini` | Retrospective narrative model. |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding generation model. |
| `EMBEDDING_BATCH_SIZE` | `32` | Max texts per embedding request. |
| `LLM_TIER1_BATCH_SIZE` | `10` | Max items per tier-1 call. |
| `PROCESSING_PIPELINE_BATCH_SIZE` | `50` | Pending items handled per pipeline run. |

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

## Scheduling and Workers

| Variable | Default | Notes |
|----------|---------|-------|
| `ENABLE_RSS_INGESTION` | `true` | Enables periodic RSS collection. |
| `ENABLE_GDELT_INGESTION` | `true` | Enables periodic GDELT collection. |
| `ENABLE_TELEGRAM_INGESTION` | `false` | Enables Telegram ingestion path. |
| `ENABLE_PROCESSING_PIPELINE` | `true` | Enables processing task execution. |
| `RSS_COLLECTION_INTERVAL` | `30` | In minutes. |
| `GDELT_COLLECTION_INTERVAL` | `60` | In minutes. |
| `TREND_SNAPSHOT_INTERVAL_MINUTES` | `60` | Snapshot cadence. |
| `WEEKLY_REPORT_DAY_OF_WEEK` | `1` | UTC day (`0=Sun..6=Sat`). |
| `WEEKLY_REPORT_HOUR_UTC` | `7` | UTC hour. |
| `MONTHLY_REPORT_DAY_OF_MONTH` | `1` | UTC day of month (`1..28`). |
| `MONTHLY_REPORT_HOUR_UTC` | `8` | UTC hour. |

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
