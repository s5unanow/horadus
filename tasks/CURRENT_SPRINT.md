# Current Sprint

**Sprint Goal**: Complete Phase 0 - Get basic infrastructure running  
**Sprint Number**: 1  
**Sprint Dates**: 2026-02-02 to 2026-02-16

---

## Active Tasks

### TASK-002: Docker Environment
**Status**: IN_PROGRESS  
**Priority**: P0 (Critical)  
**Spec**: `tasks/specs/002-docker-environment.md`

Set up Docker Compose for local development.

**Acceptance Criteria**:
- [x] docker-compose.yml with postgres + redis
- [ ] PostgreSQL has pgvector and timescaledb extensions (verify in running container)
- [x] Volumes for data persistence
- [x] Health checks configured
- [ ] Services start with `make docker-up` (or `docker compose up -d`)

**Files to Create/Modify**:
- `docker-compose.yml` (create)
- `docker/postgres/Dockerfile` (create if custom image needed)

---

### TASK-003: Database Schema & Migrations
**Status**: IN_PROGRESS  
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

**Remaining**:
- [ ] `alembic upgrade head` works

**Files to Create/Modify**:
- `alembic.ini` (create)
- `alembic/env.py` (create)
- `alembic/versions/0001_initial_schema.py` (create)

---

### TASK-004: FastAPI Skeleton
**Status**: IN_PROGRESS  
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
- [ ] App starts with `uvicorn src.api.main:app`

**Files to Create/Modify**:
- `src/api/main.py` (create)
- `src/api/deps.py` (create)
- `src/api/routes/__init__.py` (create)
- `src/api/routes/health.py` (create)
- `src/core/config.py` (create)
- `src/storage/database.py` (create)

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

## Sprint Notes

- Start with TASK-001 (project setup) - everything else depends on it
- TASK-002 (Docker) can be done in parallel
- TASK-003 (migrations) needs Docker running first
- TASK-004 (FastAPI) needs migrations applied first

### Definition of Done for Sprint 1

- [ ] `make docker-up` starts postgres and redis
- [ ] `alembic upgrade head` creates all tables
- [ ] `uvicorn src.api.main:app` starts server
- [ ] GET /health returns `{"status": "healthy"}`
- [ ] All tests pass: `make test`
