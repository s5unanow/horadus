# Current Sprint

**Sprint Goal**: Complete Phase 4 reporting and begin Phase 5 polish  
**Sprint Number**: 1  
**Sprint Dates**: 2026-02-02 to 2026-02-16

---

## Active Tasks

- No active tasks right now.

---

## Completed This Sprint

### TASK-035 Follow-up: Operational Dashboard Export & Hosting Path
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `PROJECT_STATUS.md` (Next Up)

Add static export and hosting flow for calibration dashboard visibility.

**Completed**:
- [x] Added dashboard export service for JSON/HTML static artifacts (`src/core/dashboard_export.py`)
- [x] Added CLI command `horadus dashboard export` with output path and trend-row limit options
- [x] Added `make export-dashboard` operational command
- [x] Added deployment guidance for serving `artifacts/dashboard/index.html`
- [x] Added unit tests for dashboard export payload/file output and CLI parser wiring

---

### TASK-035 Follow-up: Calibration Drift Alerts & Notifications
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `PROJECT_STATUS.md` (Next Up)

Add actionable drift alerting to calibration dashboard outputs.

**Completed**:
- [x] Added configurable drift thresholds for mean Brier and max bucket calibration error
- [x] Added minimum sample guardrail before drift alerting is activated
- [x] Added drift alert payloads to `GET /api/v1/reports/calibration`
- [x] Added structured alert notifications and Prometheus counter (`calibration_drift_alerts_total`)
- [x] Added unit tests for drift alert generation and API response wiring
- [x] Updated environment/API documentation for new calibration alert controls

---

### TASK-033 Follow-up: Contradiction-Resolution Analytics in Reports
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `PROJECT_STATUS.md` (Next Up)

Add contradiction-resolution visibility to weekly and monthly report outputs.

**Completed**:
- [x] Added contradiction analytics block to weekly and monthly report statistics
- [x] Included resolved/unresolved counts, resolution rate, action breakdown, and avg resolution time
- [x] Updated fallback report narrative to mention contradiction pressure when present
- [x] Updated weekly/monthly report prompt guidance for contradiction context
- [x] Added unit tests for contradiction analytics aggregation and report statistics wiring

---

### TASK-025 Follow-up: Auth Key Persistence & Rotation
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `PROJECT_STATUS.md` (Next Up)

Harden API key lifecycle with persistence and safe rotation.

**Completed**:
- [x] Added optional runtime key metadata persistence (`API_KEYS_PERSIST_PATH`)
- [x] Persisted runtime key hashes/metadata across restarts (no raw keys stored)
- [x] Added endpoint `POST /api/v1/auth/keys/{key_id}/rotate`
- [x] Added manager/route tests for persistence reload and rotation behavior
- [x] Updated auth/docs references and env variable documentation

---

### TASK-027 Follow-up: Deployment Hardening
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `PROJECT_STATUS.md` (Next Up)

Harden production operations for secrets, TLS posture, and backups.

**Completed**:
- [x] Added `*_FILE` secret loading support for runtime settings (DB/Redis/API/OpenAI/Celery keys)
- [x] Added explicit `SQL_ECHO` setting defaulting to `false` for safer production logging
- [x] Added backup/restore scripts (`scripts/backup_postgres.sh`, `scripts/restore_postgres.sh`)
- [x] Added `make backup-db` and `make restore-db` operational targets
- [x] Updated deployment/environment docs with file-based secrets, TLS proxy guidance, and backup drills

---

### TASK-035: Calibration Dashboard & Early Visibility
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/BACKLOG.md` (Phase 5)

Build calibration analysis and quick visibility into trend movement.

**Completed**:
- [x] Added dashboard service for reliability buckets and Brier score timeline (`src/core/calibration_dashboard.py`)
- [x] Added endpoint `GET /api/v1/reports/calibration` for cross-trend calibration reporting
- [x] Added reliability statements ("When we said X%, it happened Y%")
- [x] Added trend movement text charts with weekly change + top movers
- [x] Added CLI command `horadus trends status` for terminal visibility
- [x] Added unit tests for dashboard helpers, reports API, and CLI formatting

---

### TASK-034: Human Feedback API
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/specs/034-human-feedback.md`

Allow analyst corrections and make feedback affect future processing.

**Completed**:
- [x] Added endpoint `POST /api/v1/events/{id}/feedback` (`pin`, `mark_noise`, `invalidate`)
- [x] Added endpoint `POST /api/v1/trends/{id}/override` for manual deltas
- [x] Added endpoint `GET /api/v1/feedback` for feedback audit history
- [x] Implemented event invalidation that removes event evidence and reverts trend log-odds
- [x] Implemented processing suppression for events marked `mark_noise` or `invalidate`
- [x] Added unit tests for feedback routes and suppression behavior

---

### TASK-033: Contradiction Detection
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/specs/033-contradiction-detection.md`

Detect and surface contradictory source claims at event level.

**Completed**:
- [x] Persisted contradiction annotations from Tier 2 (`has_contradictions`, `contradiction_notes`)
- [x] Updated Tier 2 prompt contract to include contradiction detection fields
- [x] Added `contradicted` filter on `GET /api/v1/events`
- [x] Exposed contradiction fields in event list/detail API responses
- [x] Added unit tests for Tier 2 contradiction handling and events API filtering

---

### TASK-036: Cost Protection & Budget Limits
**Status**: DONE ✓  
**Priority**: P1 (Critical)  
**Spec**: `tasks/specs/036-cost-protection.md`

Enforce LLM budget limits with daily usage tracking and pipeline-safe behavior.

**Completed**:
- [x] Added `api_usage` model and Alembic migration (`0004_add_api_usage_table`)
- [x] Added `CostTracker` service with `check_budget()` and `record_usage()`
- [x] Applied pre-call budget checks in Tier 1, Tier 2, and embedding requests
- [x] Recorded token/call usage after successful LLM/embedding calls
- [x] Added `BudgetExceededError` flow so pipeline keeps items `pending`
- [x] Added budget status API endpoint `GET /api/v1/budget`
- [x] Added unit tests for tracker, classifiers, pipeline budget flow, and budget API

---

### TASK-031: Source Tier and Reporting Type
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/specs/031-source-tiers.md`

Apply source tier/reporting semantics to effective credibility in processing.

**Completed**:
- [x] Applied source tier + reporting type multipliers in credibility calculation paths
- [x] Used effective source credibility for event primary-source selection
- [x] Used effective source credibility for trend impact evidence scoring
- [x] Added unit tests for tier/reporting multiplier behavior

---

### TASK-030: Event Lifecycle Tracking
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/030-event-lifecycle.md`

Track event progression (emerging → confirmed → fading → archived) and expose lifecycle filters.

**Completed**:
- [x] Added lifecycle manager with mention/decay transitions (`src/processing/event_lifecycle.py`)
- [x] Integrated lifecycle transitions into event clustering on new mentions
- [x] Added periodic worker task `workers.check_event_lifecycles`
- [x] Added hourly beat schedule and task routing for lifecycle checks
- [x] Implemented events API list/detail handlers and lifecycle filter support
- [x] Added unit tests for lifecycle manager, clusterer transitions, events API, and worker wiring

---

### TASK-029: Enhanced Trend Definitions
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/specs/029-enhanced-trend-config.md`

Enhance trend YAML semantics and enforce schema validation in config sync.

**Completed**:
- [x] Added trend config schema models (`src/core/trend_config.py`)
- [x] Added validation for indicator `type` (`leading`/`lagging`)
- [x] Added validation for `disqualifiers` and `falsification_criteria`
- [x] Wired schema validation into trend config sync (`load_trends_from_config`)
- [x] Added tests for enhanced config support and invalid indicator type handling
- [x] Updated trend config documentation example in `README.md`

---

### TASK-028: Risk Levels and Probability Bands
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/028-risk-levels.md`

Improve trend presentation with explicit uncertainty and confidence.

**Completed**:
- [x] Added risk presentation helpers (`src/core/risk.py`)
- [x] Added `risk_level`, `probability_band`, and `confidence` to trend responses
- [x] Added evidence-driven uncertainty band calculation
- [x] Added `top_movers_7d` in trend responses from recent high-impact evidence
- [x] Added unit tests for risk mapping/band/confidence logic
- [x] Updated API docs to describe risk presentation fields

---

### TASK-032: Trend Outcomes for Calibration
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/032-trend-outcomes.md`

Track resolved outcomes and calibration quality for trend predictions.

**Completed**:
- [x] Added calibration service with Brier score computation (`src/core/calibration.py`)
- [x] Added endpoint `POST /api/v1/trends/{id}/outcomes`
- [x] Added endpoint `GET /api/v1/trends/{id}/calibration`
- [x] Added probability bucket calibration analysis (expected vs actual rates)
- [x] Added unit tests for calibration math and trend calibration routes
- [x] Documented outcome recording and calibration endpoints (`docs/API.md`)

---

### TASK-027: Deployment Configuration
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/BACKLOG.md` (Phase 5)

Production deployment setup.

**Completed**:
- [x] Added production API Dockerfile (`docker/api/Dockerfile`)
- [x] Added production worker Dockerfile (`docker/worker/Dockerfile`)
- [x] Added production stack definition (`docker-compose.prod.yml`)
- [x] Added environment variable reference (`docs/ENVIRONMENT.md`)
- [x] Added deployment guide/runbook (`docs/DEPLOYMENT.md`)

---

### TASK-026: Monitoring & Alerting
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/BACKLOG.md` (Phase 5)

Set up observability baseline for API and workers.

**Completed**:
- [x] Added structured logging bootstrap (`src/core/logging_setup.py`)
- [x] Added Prometheus endpoint `GET /metrics`
- [x] Added core counters for ingestion volume, LLM calls/cost, and worker failures
- [x] Added worker instrumentation for collector/pipeline metrics and failure counts
- [x] Kept dependency health checks for DB and Redis (`/health`)
- [x] Added unit tests for metrics endpoint and worker metrics recording

---

### TASK-025: Authentication
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/BACKLOG.md` (Phase 5)

Add API key auth, per-key rate limiting, and key management endpoints.

**Completed**:
- [x] Added API key auth middleware with path exemptions for health/docs
- [x] Added per-key in-memory rate limiting with `429` and `Retry-After`
- [x] Added key management endpoints under `/api/v1/auth/keys` (list/create/revoke)
- [x] Added environment settings for auth enablement, key lists, admin key, and rate limits
- [x] Added unit tests for manager logic and middleware/route behavior

---

### TASK-024: API Documentation
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/BACKLOG.md` (Phase 5)

Finalize OpenAPI docs and endpoint examples.

**Completed**:
- [x] Added global API docs auth scheme for `X-API-Key` in OpenAPI
- [x] Added endpoint/tag documentation metadata for Swagger/ReDoc clarity
- [x] Added request/response schema examples across API models
- [x] Added dedicated reference guide with curl examples (`docs/API.md`)
- [x] Added unit tests to validate docs routes, auth scheme, and example presence

---

### TASK-023: Retrospective Analysis
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/specs/023-retrospective-analysis.md`

Analyze how past classifications affected trend movement.

**Completed**:
- [x] Added endpoint `GET /api/v1/trends/{id}/retrospective`
- [x] Added `start_date`/`end_date` query parameters with validation
- [x] Added pivotal-event and predictive-signal aggregation for the selected window
- [x] Added accuracy assessment metrics from trend outcomes
- [x] Added LLM-backed retrospective narrative generation with deterministic fallback
- [x] Added unit tests for retrospective endpoint behavior

---

### TASK-022: Report Generator - Monthly
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/specs/022-monthly-reports.md`

Generate monthly trend reports with retrospective comparisons.

**Completed**:
- [x] Added monthly report generation with category/source breakdowns
- [x] Included prior weekly report rollups in monthly statistics payload
- [x] Added month-over-month change comparison metrics
- [x] Added Celery task `workers.generate_monthly_reports` and monthly beat schedule
- [x] Added monthly report API endpoint `GET /api/v1/reports/latest/monthly`
- [x] Added unit tests for monthly scheduling/routes and reports API behavior

---

### TASK-021: Report Generator - Weekly
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/021-weekly-reports.md`

Generate weekly trend reports with computed statistics and narrative.

**Completed**:
- [x] Added weekly report generation service with per-trend stats and top events
- [x] Added Celery task `workers.generate_weekly_reports`
- [x] Added weekly beat schedule (configurable day/hour/minute in UTC)
- [x] Added report API implementations for list/get/latest weekly
- [x] Added unit tests for reports API and weekly report worker wiring

---

### TASK-020: Decay Worker
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/020-decay-worker.md`

Apply time-based probability decay for active trends.

**Completed**:
- [x] Added Celery task `workers.apply_trend_decay` for daily trend decay
- [x] Applied `TrendEngine.apply_decay` across all active trends in one run
- [x] Added decay task summary metrics (`scanned`, `decayed`, `unchanged`)
- [x] Added beat schedule wiring for daily decay execution
- [x] Added unit tests for schedule/routes and decay task invocation

---

### TASK-019: Trend Snapshots
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/019-trend-snapshots.md`

Store periodic snapshots for trend history tracking and reporting.

**Completed**:
- [x] Added Celery task `workers.snapshot_trends` to persist active trend snapshots
- [x] Added beat schedule wiring using `TREND_SNAPSHOT_INTERVAL_MINUTES`
- [x] Added history endpoint `GET /api/v1/trends/{id}/history`
- [x] Added date-range filtering and interval downsampling (`hourly`, `daily`, `weekly`)
- [x] Added unit tests for snapshot task scheduling and trend history API behavior

---

### TASK-018: Evidence Recording
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/018-evidence-recording.md`

Store evidence trail for all probability updates.

**Completed**:
- [x] Added evidence list endpoint `GET /api/v1/trends/{id}/evidence`
- [x] Added optional `start_at` and `end_at` date-range filters
- [x] Added response mapping for all persisted evidence scoring factors
- [x] Added request validation for invalid date windows
- [x] Added unit tests for evidence retrieval and date filter behavior

---

### TASK-017: Trend Engine Core
**Status**: DONE ✓  
**Priority**: P0 (Critical)  
**Spec**: `tasks/specs/017-trend-engine-core.md`

Implement log-odds trend engine orchestration and service integration.

**Completed**:
- [x] Added trend-impact orchestration in processing pipeline after Tier 2
- [x] Resolved indicator weights from trend config and skipped invalid signal weights safely
- [x] Applied deterministic log-odds deltas using severity/confidence/credibility/corroboration/novelty
- [x] Persisted trend evidence via `TrendEngine.apply_evidence` idempotent path
- [x] Added trend impact/update counters to pipeline run metrics
- [x] Added unit and integration tests for applied and skipped impact paths

---

### TASK-016: Trend Management
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/016-trend-management.md`

Add API endpoints and internal services to manage trends.

**Completed**:
- [x] Added trend CRUD endpoints (`GET/POST/GET by id/PATCH/DELETE`)
- [x] Added probability conversion in API responses (log-odds → probability)
- [x] Added YAML config sync endpoint and loader for `config/trends/*.yaml`
- [x] Added conflict/404 handling and soft-delete deactivation flow
- [x] Added unit tests for trend routes and config loading behavior

---

### TASK-015: Processing Pipeline
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/015-processing-pipeline.md`

Wire together the end-to-end processing pipeline.

**Completed**:
- [x] Added processing orchestrator (dedup → embed → cluster → tier1 → tier2)
- [x] Added per-item status transitions (`pending` → `processing` → terminal state)
- [x] Added robust per-item error handling with `error_message` persistence
- [x] Added Celery processing task + auto-trigger when ingestion stores new items
- [x] Added pipeline metrics summary for processing runs
- [x] Added unit and integration tests for end-to-end pipeline flow

---

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
