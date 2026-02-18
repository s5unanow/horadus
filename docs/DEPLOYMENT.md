# Deployment Guide

**Last Verified**: 2026-02-18

This guide covers a single-host Docker Compose deployment using:

- `docker/api/Dockerfile`
- `docker/worker/Dockerfile`
- `docker/caddy/Caddyfile`
- `docker-compose.prod.yml`

## 1) Prepare environment and secret files

Copy the template and set production values:

```bash
cp .env.example .env
```

Required minimum settings:

- `ENVIRONMENT=production`
- `SECRET_KEY_FILE`
- `API_AUTH_ENABLED=true`
- `API_KEYS_FILE`
- `API_ADMIN_KEY_FILE`
- `OPENAI_API_KEY_FILE`
- `HORADUS_PUBLIC_DOMAIN` (for TLS certificate issuance/ingress host routing)
- `CADDY_ACME_EMAIL` (recommended for ACME expiration/renewal notices)

Production secret policy:

- Keep raw secret values out of `.env`.
- Mount read-only secret files into containers and wire via `*_FILE`.
- Follow `docs/SECRETS_RUNBOOK.md` for provisioning, rotation, and rollback.
- If you set `SECRET_KEY` directly (instead of `SECRET_KEY_FILE`), use at least 32 characters and avoid weak/default values.

For a full variable reference, see `docs/ENVIRONMENT.md`.
For release and rollback governance, see `docs/RELEASING.md`.
For calibration alert triage and review operations, see `docs/CALIBRATION_RUNBOOK.md`.
For managed backend options, see `docs/SECRETS_BACKENDS.md`.
For 6-hour low-frequency defaults and outage catch-up steps, see `docs/LOW_FREQUENCY_MODE.md`.

6-hour baseline deployment profile:

```dotenv
RSS_COLLECTION_INTERVAL=360
GDELT_COLLECTION_INTERVAL=360
PROCESS_PENDING_INTERVAL_MINUTES=15
PROCESSING_PIPELINE_BATCH_SIZE=200
```

Recommended production hardening:

- Set `SQL_ECHO=false`.
- Set `MIGRATION_PARITY_STRICT_STARTUP=true` once migration workflow is validated in your environment.
- Restrict `CORS_ORIGINS` to trusted frontend domains only.
- Provide `POSTGRES_PASSWORD` via runtime environment (not committed files) when running bundled `postgres`.
- Keep `API_RATE_LIMIT_STRATEGY=fixed_window` by default for low-overhead operation; switch to `sliding_window` only when boundary-burst smoothing is required.

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
docker compose -f docker-compose.prod.yml up -d ingress api worker beat postgres redis
```

## 5) Verify health and metrics

```bash
export HORADUS_BASE_URL="https://${HORADUS_PUBLIC_DOMAIN}"

curl -sSf "${HORADUS_BASE_URL}/health"
curl -sSf "${HORADUS_BASE_URL}/health/ready"
curl -sSf "${HORADUS_BASE_URL}/metrics" | head

# HTTP must not serve plaintext content externally (redirect to HTTPS is allowed).
curl -sSI "http://${HORADUS_PUBLIC_DOMAIN}/health" | sed -n '1,5p'

# Security headers must be present at the edge.
curl -sSI "${HORADUS_BASE_URL}/health" | grep -Ei "strict-transport-security|x-content-type-options|x-frame-options"

# API container should not publish host port 8000 directly.
docker compose -f docker-compose.prod.yml port api 8000 || echo "api:8000 not published (expected)"
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
docker compose -f docker-compose.prod.yml up -d ingress api worker beat
```

Rollback:

1. Checkout the previous Git commit/tag.
2. Rebuild images with that revision.
3. Restart `api`, `worker`, and `beat`.

## 8) TLS termination and ingress workflow

Horadus production defaults now include a dedicated Caddy ingress service:

- Public ports: `80` and `443` on `ingress`
- Internal upstream: `api:8000` on `horadus-network`
- HTTP behavior: automatic redirect to HTTPS
- Security headers at edge:
  - `Strict-Transport-Security`
  - `X-Content-Type-Options`
  - `X-Frame-Options`

Certificate provisioning and renewal:

1. Set `HORADUS_PUBLIC_DOMAIN` to the resolvable public hostname.
2. Set `CADDY_ACME_EMAIL` for ACME account registration.
3. Start `ingress`; Caddy automatically requests and renews certificates.
4. Check certificate lifecycle and renewal logs:
   ```bash
   docker compose -f docker-compose.prod.yml logs -f ingress
   ```

Failure fallback steps (ACME/cert issuance):

1. Validate DNS and public reachability on ports `80` and `443`.
2. Temporarily set `CADDY_ACME_CA=https://acme-staging-v02.api.letsencrypt.org/directory` and
   retry to verify challenge flow without rate-limit pressure.
3. If ACME remains unavailable, provision managed certificates externally and
   switch to explicit cert files in `docker/caddy/Caddyfile`:
   - mount cert/key into `./docker/caddy/certs/`
   - replace site TLS stanza with:
     ```caddyfile
     tls /certs/fullchain.pem /certs/privkey.pem
     ```
4. Keep API host-port exposure disabled while recovering certificate flow.

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
