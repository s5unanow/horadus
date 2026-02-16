# Deployment Guide

**Last Verified**: 2026-02-16

This guide covers a single-host Docker Compose deployment using:

- `docker/api/Dockerfile`
- `docker/worker/Dockerfile`
- `docker-compose.prod.yml`

## 1) Prepare environment and secret files

Copy the template and set production values:

```bash
cp .env.example .env
```

Required minimum settings:

- `API_AUTH_ENABLED=true`
- `API_KEYS_FILE`
- `API_ADMIN_KEY_FILE`
- `OPENAI_API_KEY_FILE`

Production secret policy:

- Keep raw secret values out of `.env`.
- Mount read-only secret files into containers and wire via `*_FILE`.
- Follow `docs/SECRETS_RUNBOOK.md` for provisioning, rotation, and rollback.

For a full variable reference, see `docs/ENVIRONMENT.md`.
For release and rollback governance, see `docs/RELEASING.md`.
For calibration alert triage and review operations, see `docs/CALIBRATION_RUNBOOK.md`.
For managed backend options, see `docs/SECRETS_BACKENDS.md`.

Recommended production hardening:

- Set `SQL_ECHO=false`.
- Set `MIGRATION_PARITY_STRICT_STARTUP=true` once migration workflow is validated in your environment.
- Restrict `CORS_ORIGINS` to trusted frontend domains only.
- Provide `POSTGRES_PASSWORD` via runtime environment (not committed files) when running bundled `postgres`.

## 2) Build production images

```bash
docker compose -f docker-compose.prod.yml build
```

## 3) Run database migration job

```bash
docker compose -f docker-compose.prod.yml --profile ops run --rm migrate
```

Validate migration parity against Alembic head:

```bash
make db-migration-gate MIGRATION_GATE_DATABASE_URL="<production-db-url>"
```

Strict autogenerate parity (`alembic check`) is enabled by default. Emergency bypass
is explicit-only:

```bash
make db-migration-gate MIGRATION_GATE_DATABASE_URL="<production-db-url>" MIGRATION_GATE_VALIDATE_AUTOGEN=false
```

## 4) Start services

```bash
docker compose -f docker-compose.prod.yml up -d api worker beat postgres redis
```

## 5) Verify health and metrics

```bash
curl -sSf http://localhost:8000/health
curl -sSf http://localhost:8000/metrics | head
```

## 6) Export and host dashboard artifacts

Generate static calibration dashboard files:

```bash
make export-dashboard
```

This writes timestamped artifacts plus stable hosting aliases:

- `artifacts/dashboard/calibration-dashboard-latest.json`
- `artifacts/dashboard/calibration-dashboard-latest.html`
- `artifacts/dashboard/index.html`

Recommended hosting path:

- Serve `artifacts/dashboard/` from your reverse proxy/static host.
- Keep `index.html` as the canonical dashboard URL.
- Restrict dashboard exposure to trusted networks if it contains sensitive analysis.

## 7) Operate and update

Deploy a new revision:

```bash
git pull
docker compose -f docker-compose.prod.yml build api worker
docker compose -f docker-compose.prod.yml --profile ops run --rm migrate
docker compose -f docker-compose.prod.yml up -d api worker beat
```

Rollback:

1. Checkout the previous Git commit/tag.
2. Rebuild images with that revision.
3. Restart `api`, `worker`, and `beat`.

## 8) TLS termination

Run TLS at an edge reverse proxy (Caddy, Nginx, Traefik) and keep Horadus internal.

- Terminate HTTPS at the proxy.
- Forward traffic to `api:8000` on the private Docker network.
- Disable public direct exposure of the API container where possible.
- Enforce modern TLS settings and HTTP security headers at the proxy layer.

## 9) Backups and restore

Create PostgreSQL backups:

```bash
make backup-db
```

Verify latest backup freshness and integrity:

```bash
make verify-backups
```

Restore from a backup:

```bash
make restore-db DUMP=backups/<dump-file>.sql.gz
```

Recommended practice:

- Schedule `make backup-db` via cron/systemd.
- Schedule `make verify-backups` shortly after backup jobs.
- Tune retention with `BACKUP_RETENTION_DAYS` and `BACKUP_RETENTION_COUNT`.
- Replicate backups to off-host object storage.
- Test restore drills regularly.

## Operational Notes

- `api` serves FastAPI (`/health`, `/metrics`, `/docs`).
- `worker` runs Celery worker queues: `default`, `ingestion`, `processing`.
- `beat` schedules periodic ingestion, snapshots, decay, and report jobs.
- Postgres and Redis use named volumes (`postgres_data`, `redis_data`) for persistence.
