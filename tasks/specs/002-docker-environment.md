# TASK-002: Docker Environment

## Overview

Set up Docker Compose configuration for local development with PostgreSQL (including pgvector and TimescaleDB extensions) and Redis.

## Context

We need a consistent local development environment. Using Docker ensures everyone has the same database setup with the required extensions.

## Requirements

### Services

1. **PostgreSQL** (port 5432)
   - Version: 16
   - Extensions: pgvector, TimescaleDB
   - Persistent volume for data
   - Health check

2. **Redis** (port 6379)
   - Version: 7
   - Persistent volume for data
   - Health check

### Network

- All services on a shared network `geoint-network`
- Services accessible by name (e.g., `postgres`, `redis`)

## Implementation

### docker-compose.yml

```yaml
version: '3.8'

services:
  postgres:
    image: timescale/timescaledb:latest-pg16
    container_name: geoint-postgres
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: geoint
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./docker/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - geoint-network

  redis:
    image: redis:7-alpine
    container_name: geoint-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    command: redis-server --appendonly yes
    networks:
      - geoint-network

volumes:
  postgres_data:
  redis_data:

networks:
  geoint-network:
    driver: bridge
```

### docker/postgres/init.sql

This script runs when the container is first created:

```sql
-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Verify extensions
SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'timescaledb');
```

### Directory Structure

```
docker/
└── postgres/
    └── init.sql
docker-compose.yml
```

## Verification Steps

```bash
# Start services
docker-compose up -d

# Wait for healthy status
docker-compose ps

# Verify PostgreSQL extensions
docker exec geoint-postgres psql -U postgres -d geoint -c "SELECT extname FROM pg_extension;"
# Should show: plpgsql, vector, timescaledb

# Verify Redis
docker exec geoint-redis redis-cli ping
# Should return: PONG

# Test database connection
docker exec geoint-postgres psql -U postgres -d geoint -c "SELECT 1;"

# Check logs if issues
docker-compose logs postgres
docker-compose logs redis
```

## Common Issues

### TimescaleDB + pgvector Image

The `timescale/timescaledb:latest-pg16` image includes TimescaleDB but not pgvector. We have two options:

**Option A**: Use init.sql to install pgvector (simpler, shown above)
- Works if pgvector is available in apt repositories

**Option B**: Build custom image (more reliable)

```dockerfile
# docker/postgres/Dockerfile
FROM timescale/timescaledb:latest-pg16

RUN apt-get update && apt-get install -y \
    postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
```

Then in docker-compose.yml:
```yaml
postgres:
  build:
    context: ./docker/postgres
    dockerfile: Dockerfile
  # ... rest of config
```

### Port Conflicts

If ports 5432 or 6379 are already in use:
- Change the host port mapping (e.g., `"5433:5432"`)
- Update `.env` with the new port

### Data Persistence

Data is stored in Docker volumes. To reset:
```bash
docker-compose down -v  # -v removes volumes
docker-compose up -d
```

## Acceptance Checklist

- [ ] `docker-compose.yml` created
- [ ] `docker/postgres/init.sql` created
- [ ] `docker-compose up -d` starts both services
- [ ] PostgreSQL healthy: `docker-compose ps` shows healthy
- [ ] Redis healthy: `docker-compose ps` shows healthy
- [ ] pgvector extension available
- [ ] TimescaleDB extension available
- [ ] Data persists across restarts
