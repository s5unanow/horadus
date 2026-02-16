# Container Secrets Runbook

This runbook defines provisioning, rotation, and rollback for Horadus
container secrets using mounted files and `*_FILE` settings.

Production policy:

- Do not store raw secret values in production `.env`.
- Store secret values in host files mounted read-only into containers.
- Use only `*_FILE` environment variables for secret wiring.

For full variable mapping, see `docs/ENVIRONMENT.md`.

## 1) Provisioning

### 1.1 Host directory layout

Recommended structure:

```text
/srv/horadus/secrets/
  releases/
    20260215T090000Z/
      database_url
      database_url_sync
      redis_url
      celery_broker_url
      celery_result_backend
      secret_key
      api_keys
      api_admin_key
      openai_api_key
      llm_secondary_api_key
  current -> /srv/horadus/secrets/releases/20260215T090000Z
```

Keep each rotation in a timestamped `releases/<stamp>/` directory and move the
`current` symlink during rollout/rollback.

### 1.2 File names and variable mapping

| File | Variable |
|------|----------|
| `database_url` | `DATABASE_URL_FILE` |
| `database_url_sync` | `DATABASE_URL_SYNC_FILE` |
| `redis_url` | `REDIS_URL_FILE` |
| `celery_broker_url` | `CELERY_BROKER_URL_FILE` |
| `celery_result_backend` | `CELERY_RESULT_BACKEND_FILE` |
| `secret_key` | `SECRET_KEY_FILE` |
| `api_keys` | `API_KEYS_FILE` |
| `api_admin_key` | `API_ADMIN_KEY_FILE` |
| `openai_api_key` | `OPENAI_API_KEY_FILE` |
| `llm_secondary_api_key` | `LLM_SECONDARY_API_KEY_FILE` |

`api_keys` may contain newline-separated and/or comma-separated values.

### 1.3 Permissions and ownership checklist

1. Create the release directory with restricted access:

```bash
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SECRET_ROOT="/srv/horadus/secrets"
SECRET_RELEASE="$SECRET_ROOT/releases/$STAMP"
sudo install -d -m 0750 "$SECRET_ROOT/releases" "$SECRET_RELEASE"
```

2. Create secret files and write values:

```bash
sudo install -m 0640 /dev/null "$SECRET_RELEASE/openai_api_key"
sudo install -m 0640 /dev/null "$SECRET_RELEASE/api_admin_key"
sudo install -m 0640 /dev/null "$SECRET_RELEASE/api_keys"
```

3. Ensure files are readable by the runtime container user (`app`):

```bash
APP_UID="$(docker run --rm horadus-api:latest id -u app)"
APP_GID="$(docker run --rm horadus-api:latest id -g app)"
sudo chown -R "${APP_UID}:${APP_GID}" "$SECRET_RELEASE"
sudo chmod 0750 "$SECRET_RELEASE"
sudo chmod 0640 "$SECRET_RELEASE"/*
```

### 1.4 Docker Compose mount pattern (`api`, `worker`, `beat`)

Use the same read-only bind mount for all runtime services:

```yaml
services:
  api:
    volumes:
      - ${HORADUS_SECRETS_DIR:-/srv/horadus/secrets/current}:/run/secrets/horadus:ro
    environment:
      DATABASE_URL_FILE: /run/secrets/horadus/database_url
      DATABASE_URL_SYNC_FILE: /run/secrets/horadus/database_url_sync
      REDIS_URL_FILE: /run/secrets/horadus/redis_url
      CELERY_BROKER_URL_FILE: /run/secrets/horadus/celery_broker_url
      CELERY_RESULT_BACKEND_FILE: /run/secrets/horadus/celery_result_backend
      SECRET_KEY_FILE: /run/secrets/horadus/secret_key
      API_KEYS_FILE: /run/secrets/horadus/api_keys
      API_ADMIN_KEY_FILE: /run/secrets/horadus/api_admin_key
      OPENAI_API_KEY_FILE: /run/secrets/horadus/openai_api_key
      LLM_SECONDARY_API_KEY_FILE: /run/secrets/horadus/llm_secondary_api_key
```

Apply the same `volumes` and `*_FILE` values to `worker` and `beat`.

### 1.5 Pre-flight validation

Before restart, validate that settings can load file-backed secrets:

```bash
docker compose -f docker-compose.prod.yml run --rm --no-deps api \
  python -c "from src.core.config import Settings; Settings(); print('secrets-ok')"
```

## 2) Rotation Runbook

1. Prepare new release files in `releases/<new-stamp>/`.
2. Run pre-flight validation against the new files.
3. Point `current` to the new release atomically:

```bash
sudo ln -sfn "$SECRET_RELEASE" /srv/horadus/secrets/current
```

4. Recreate runtime services to pick up the new files:

```bash
docker compose -f docker-compose.prod.yml up -d --no-deps --force-recreate api worker beat
```

5. Post-rotation checks:
   - `curl -sSf http://localhost:8000/health`
   - `docker compose -f docker-compose.prod.yml ps`
   - Run smoke checks relevant to current release scope.

## 3) Rollback Runbook

If rotation fails:

1. Repoint `current` to the previous known-good release:

```bash
sudo ln -sfn /srv/horadus/secrets/releases/<previous-stamp> /srv/horadus/secrets/current
```

2. Recreate runtime services:

```bash
docker compose -f docker-compose.prod.yml up -d --no-deps --force-recreate api worker beat
```

3. Validate rollback:
   - `curl -sSf http://localhost:8000/health`
   - Confirm expected service status via `docker compose -f docker-compose.prod.yml ps`
   - Confirm no new auth/LLM credential failures in service logs.

## 4) Hygiene Checklist

- Restrict secret directory access to operators only.
- Keep one previous release directory for fast rollback.
- Remove superseded secret releases after stability window.
- Never commit secret values or secret files to Git.
