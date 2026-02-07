# Current Sprint

**Sprint Goal**: Complete Phase 1 and begin Phase 2 processing baseline  
**Sprint Number**: 1  
**Sprint Dates**: 2026-02-02 to 2026-02-16

---

## Active Tasks

### TASK-015: Processing Pipeline
**Status**: IN_PROGRESS  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/015-processing-pipeline.md`

Wire together the end-to-end processing pipeline.

**Planned**:
- [ ] Trigger Celery task when new `raw_items` arrive
- [ ] Orchestrate flow: dedup → embed → cluster → tier1 → tier2
- [ ] Persist pipeline status transitions on items/events
- [ ] Add retry/error handling for recoverable failures
- [ ] Add pipeline metrics (processed, filtered, escalated)
- [ ] Add integration test for end-to-end flow

---

## Completed This Sprint

### TASK-014: LLM Classifier - Tier 2
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/014-llm-classifier-tier2.md`

Build detailed structured event extraction and per-trend impact classification.

**Completed**:
- [x] Tier 2 classifier service using `gpt-4o-mini`
- [x] Structured extraction of who/what/where/when and claims
- [x] Per-trend impact classification (direction, severity, confidence)
- [x] Taxonomy category assignment and canonical summary generation
- [x] Strict schema validation and unknown-trend safeguards
- [x] Cost/usage metrics per run and unit tests

---

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

### TASK-005: Source Management
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/005-source-management.md`

Add CRUD management for ingestion sources.

**Completed**:
- [x] GET `/api/v1/sources` lists sources (with type + active filters)
- [x] POST `/api/v1/sources` creates source with validation
- [x] GET `/api/v1/sources/{id}` returns source by UUID
- [x] PATCH `/api/v1/sources/{id}` updates partial fields
- [x] DELETE `/api/v1/sources/{id}` deactivates source
- [x] Unit tests for endpoint handlers

---

### TASK-006: RSS Collector
**Status**: DONE ✓  
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
- [x] Integration test verification without external network (`httpx.MockTransport`)

---

### TASK-007: GDELT Client
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/007-gdelt-client.md`

Build GDELT API client for broad news coverage.

**Completed**:
- [x] Query GDELT DOC 2.0 API (`mode=ArtList`) with bounded retry/backoff
- [x] Filter by relevant themes/actors/countries/languages
- [x] Map GDELT records to `raw_items` schema
- [x] Handle time-window pagination + deduplication
- [x] Persist collected items with pending status
- [x] Unit tests for query/filter/storage flow
- [x] Integration test verification without external network (`httpx.MockTransport`)

---

### TASK-008: Celery Setup
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/008-celery-setup.md`

Configure Celery for async task processing.

**Completed**:
- [x] Celery app configured with Redis broker/backend (`src/workers/celery_app.py`)
- [x] Beat schedule configured for periodic RSS + GDELT ingestion
- [x] RSS and GDELT ingestion tasks implemented (`src/workers/tasks.py`)
- [x] Retry/backoff policy configured on ingestion tasks
- [x] Dead-letter handling added via Celery failure signal + Redis list
- [x] Worker health task (`workers.ping`) added
- [x] Unit tests covering schedule/task/dead-letter behavior

---

### TASK-009: Telegram Harvester
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/specs/009-telegram-harvester.md`

Build Telegram channel collector using Telethon.

**Completed**:
- [x] Telethon client setup with persistent session naming
- [x] Channel config loading from `config/sources/telegram_channels.yaml`
- [x] Message ingestion and mapping into `raw_items` schema
- [x] Historical backfill capability for bounded day windows
- [x] Near real-time polling mode (`stream_channel`)
- [x] Media fallback extraction (captions/file metadata)
- [x] Deduplication by external id/url/content hash
- [x] Unit tests with mocked Telegram client/messages
- [x] Integration test verification without external network

---

### TASK-010: Embedding Service
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/010-embedding-service.md`

Create embedding generation service for processed items/events.

**Completed**:
- [x] OpenAI embedding wrapper with strict response validation
- [x] Batch embedding requests with configurable batch size
- [x] In-memory caching for repeated text embeddings
- [x] pgvector persistence for `raw_items.embedding`
- [x] Unit tests for batching, caching, validation, and persistence

---

### TASK-011: Deduplication Service
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/011-deduplication-service.md`

Build deduplication using URL, hash, and embedding similarity.

**Completed**:
- [x] Reusable deduplication service with URL normalization
- [x] Exact duplicate checks for external id, URL, and content hash
- [x] Optional embedding similarity check (cosine threshold, default 0.92)
- [x] Configurable similarity threshold and dedup result metadata
- [x] Unit tests for matching order and edge cases

---

### TASK-012: Event Clusterer
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/012-event-clusterer.md`

Cluster related `RawItem` records into `Event` records.

**Completed**:
- [x] Event clusterer service with 48h similarity search window
- [x] Create-or-merge flow for clustering raw items into events
- [x] Event metadata updates on merge (`source_count`, `unique_source_count`)
- [x] Canonical summary refresh and primary source tracking by credibility
- [x] Unit tests covering create, merge, and primary-source selection

---

### TASK-013: LLM Classifier - Tier 1
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/013-llm-classifier-tier1.md`

Build the fast relevance filter stage for processing.

**Completed**:
- [x] Tier 1 classifier service using `gpt-4.1-nano`
- [x] Relevance scoring `0..10` per configured trend with strict Pydantic validation
- [x] Batch request handling with configurable batch size
- [x] Cost/usage metrics per run (tokens + estimated USD)
- [x] Status routing (`noise` vs Tier 2 queue-ready `processing`) and unit tests

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
