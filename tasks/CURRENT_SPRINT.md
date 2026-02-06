# Current Sprint

**Sprint Goal**: Complete Phase 0 - Get basic infrastructure running  
**Sprint Number**: 1  
**Sprint Dates**: 2026-02-02 to 2026-02-16

---

## Active Tasks

### TASK-006: RSS Collector
**Status**: IN_PROGRESS  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/006-rss-collector.md`

Build RSS feed collector with full-text extraction.

**Completed**:
- [x] Load feed configs from `config/sources/rss_feeds.yaml`
- [x] Fetch and parse RSS feeds using `feedparser`
- [x] Extract full article text using Trafilatura (fallback to summary/title)
- [x] Deduplicate by normalized URL and content hash (7-day window)
- [x] Store new entries in `raw_items` with `processing_status='pending'`
- [x] Handle feed/article failures gracefully with source error tracking
- [x] Per-domain rate limiting (1 req/sec)
- [x] Unit tests with mocked feeds/network/database

**Remaining**:
- [ ] Integration verification with live feed source

---

## Completed This Sprint

### TASK-001: Python Project Setup
**Status**: DONE ✓  
**Priority**: P0 (Critical)  
**Spec**: `tasks/specs/001-python-project-setup.md`

Set up Python project with pyproject.toml, dependencies, and dev tools.

**Completed**:
- [x] pyproject.toml with all dependencies
- [x] Dev dependencies (pytest, ruff, mypy)
- [x] .env.example with all required variables
- [x] Basic src/ package structure importable

---

### TASK-002: Docker Environment
**Status**: DONE ✓  
**Priority**: P0 (Critical)  
**Spec**: `tasks/specs/002-docker-environment.md`

Set up Docker Compose for local development.

**Acceptance Criteria**:
- [x] docker-compose.yml with postgres + redis
- [x] PostgreSQL has pgvector and timescaledb extensions (verified in running container)
- [x] Volumes for data persistence
- [x] Health checks configured
- [x] Services start with `make docker-up` (or `docker compose up -d`)

---

### TASK-003: Database Schema & Migrations
**Status**: DONE ✓  
**Priority**: P0 (Critical)  
**Spec**: `tasks/specs/003-database-schema.md`

Create initial database schema using Alembic migrations.

**Completed**:
- [x] src/storage/models.py with all entities
- [x] Alembic configured and initialized
- [x] alembic.ini created
- [x] Initial migration generated from models (manual initial schema)
- [x] pgvector extension enabled in migration
- [x] TimescaleDB hypertable for trend_snapshots
- [x] `alembic upgrade head` works

---

### TASK-004: FastAPI Skeleton
**Status**: DONE ✓  
**Priority**: P0 (Critical)  
**Spec**: `tasks/specs/004-fastapi-skeleton.md`

Create basic FastAPI application structure.

**Acceptance Criteria**:
- [x] FastAPI app in src/api/main.py
- [x] Health endpoint at GET /health
- [x] Database connection pool (asyncpg)
- [x] Database session dependency
- [x] CORS middleware
- [x] Error handling middleware
- [x] Settings from environment variables
- [x] App starts with `uvicorn src.api.main:app`

---

## Sprint Notes

- Start with TASK-001 (project setup) - everything else depends on it
- TASK-002 (Docker) can be done in parallel
- TASK-003 (migrations) needs Docker running first
- TASK-004 (FastAPI) needs migrations applied first

### Definition of Done for Sprint 1

- [x] `make docker-up` starts postgres and redis
- [x] `alembic upgrade head` creates all tables
- [x] `uvicorn src.api.main:app` starts server
- [x] GET /health returns `{"status": "healthy"}`
- [x] All tests pass: `make test`
