# Deployment Guide

This guide covers a single-host Docker Compose deployment using:

- `docker/api/Dockerfile`
- `docker/worker/Dockerfile`
- `docker-compose.prod.yml`

## 1) Prepare environment file

Copy the template and set production values:

```bash
cp .env.example .env
```

Required minimum values:

- `OPENAI_API_KEY`
- `API_AUTH_ENABLED=true`
- `API_KEYS` (one or more keys)
- `API_ADMIN_KEY`
- `POSTGRES_PASSWORD` (in your shell or `.env`)

For a full variable reference, see `docs/ENVIRONMENT.md`.

Recommended production hardening:

- Prefer `*_FILE` variables backed by secret mounts (instead of plaintext `.env` secrets).
- Set `SQL_ECHO=false`.
- Restrict `CORS_ORIGINS` to trusted frontend domains only.

## 2) Build production images

```bash
docker compose -f docker-compose.prod.yml build
```

## 3) Run database migration job

```bash
docker compose -f docker-compose.prod.yml --profile ops run --rm migrate
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

## 6) Operate and update

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

## 7) TLS termination

Run TLS at an edge reverse proxy (Caddy, Nginx, Traefik) and keep Horadus internal.

- Terminate HTTPS at the proxy.
- Forward traffic to `api:8000` on the private Docker network.
- Disable public direct exposure of the API container where possible.
- Enforce modern TLS settings and HTTP security headers at the proxy layer.

## 8) Backups and restore

Create PostgreSQL backups:

```bash
make backup-db
```

Restore from a backup:

```bash
make restore-db DUMP=backups/<dump-file>.sql.gz
```

Recommended practice:

- Schedule `make backup-db` via cron/systemd.
- Replicate backups to off-host object storage.
- Test restore drills regularly.

## Operational Notes

- `api` serves FastAPI (`/health`, `/metrics`, `/docs`).
- `worker` runs Celery worker queues: `default`, `ingestion`, `processing`.
- `beat` schedules periodic ingestion, snapshots, decay, and report jobs.
- Postgres and Redis use named volumes (`postgres_data`, `redis_data`) for persistence.
