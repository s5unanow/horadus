# Backlog

All planned tasks for the Geopolitical Intelligence Platform.  
Tasks are organized by phase and priority.

---

## Task ID Policy

- Task IDs are global and never reused.
- Completed IDs are reserved permanently and tracked in `tasks/COMPLETED.md`.
- Next available task IDs start at `TASK-068`.
- Checklist boxes in this file are planning snapshots; canonical completion status lives in
  `tasks/CURRENT_SPRINT.md` and `tasks/COMPLETED.md`.

## Task Labels

- `[REQUIRES_HUMAN]`: task includes a mandatory manual step and must not be auto-completed by an agent.
- For `[REQUIRES_HUMAN]` tasks, agents may prepare instructions/checklists only and must stop for human completion.

---

## Phase 0: Setup & Foundation

### TASK-001: Python Project Setup
**Priority**: P0 (Critical)  
**Estimate**: 1 hour  
**Spec**: `tasks/specs/001-python-project-setup.md`

Set up Python project with pyproject.toml, dependencies, and dev tools.

**Acceptance Criteria**:
- [ ] pyproject.toml with all dependencies
- [ ] Dev dependencies (pytest, ruff, mypy)
- [ ] .env.example with all required variables
- [ ] Basic src/ package structure importable

---

### TASK-002: Docker Environment
**Priority**: P0 (Critical)  
**Estimate**: 1 hour  
**Spec**: `tasks/specs/002-docker-environment.md`

Set up Docker Compose for local development (PostgreSQL, Redis).

**Acceptance Criteria**:
- [ ] docker-compose.yml with postgres + redis
- [ ] PostgreSQL has pgvector and timescaledb extensions
- [ ] Volumes for data persistence
- [ ] Health checks configured
- [ ] Services start with `docker-compose up -d`

---

### TASK-003: Database Schema & Migrations
**Priority**: P0 (Critical)  
**Estimate**: 2 hours  
**Spec**: `tasks/specs/003-database-schema.md`

Create initial database schema using Alembic migrations.

**Acceptance Criteria**:
- [ ] Alembic configured and initialized
- [ ] Initial migration with all core tables
- [ ] pgvector extension enabled
- [ ] TimescaleDB hypertable for trend_snapshots
- [ ] Indexes created for common queries
- [ ] `alembic upgrade head` works

---

### TASK-004: FastAPI Skeleton
**Priority**: P0 (Critical)  
**Estimate**: 2 hours  
**Spec**: `tasks/specs/004-fastapi-skeleton.md`

Create basic FastAPI application structure with health endpoint.

**Acceptance Criteria**:
- [ ] FastAPI app in src/api/main.py
- [ ] Health endpoint at /health
- [ ] Database connection pool configured
- [ ] CORS configured
- [ ] Error handling middleware
- [ ] Async database session management
- [ ] App starts with `uvicorn src.api.main:app`

---

## Phase 1: Data Ingestion

### TASK-005: Source Management
**Priority**: P1 (High)  
**Estimate**: 2 hours  
**Spec**: `tasks/specs/005-source-management.md`

API endpoints for managing data sources (CRUD).

**Acceptance Criteria**:
- [ ] GET /api/v1/sources - list all sources
- [ ] POST /api/v1/sources - create source
- [ ] GET /api/v1/sources/{id} - get source
- [ ] PATCH /api/v1/sources/{id} - update source
- [ ] DELETE /api/v1/sources/{id} - delete source
- [ ] Input validation with Pydantic
- [ ] Unit tests for all endpoints

---

### TASK-006: RSS Collector
**Priority**: P1 (High)  
**Estimate**: 4 hours  
**Spec**: `tasks/specs/006-rss-collector.md`

Build RSS feed collector with full-text extraction.

**Acceptance Criteria**:
- [ ] Load feed configs from config/sources/rss_feeds.yaml
- [ ] Fetch and parse RSS feeds using feedparser
- [ ] Extract full article text using Trafilatura
- [ ] Deduplicate by URL and content hash
- [ ] Store in raw_items table
- [ ] Handle feed failures gracefully
- [ ] Rate limiting (1 req/sec per domain)
- [ ] Unit tests with mock feeds
- [ ] Integration test with real feed

---

### TASK-007: GDELT Client
**Priority**: P1 (High)  
**Estimate**: 4 hours  
**Spec**: `tasks/specs/007-gdelt-client.md`

Build GDELT API client for broad news coverage.

**Acceptance Criteria**:
- [ ] Query GDELT DOC 2.0 API
- [ ] Filter by relevant themes/actors
- [ ] Map GDELT events to our RawItem schema
- [ ] Handle pagination
- [ ] Deduplicate against existing items
- [ ] Store results in raw_items
- [ ] Unit tests with mock responses
- [ ] Integration test with real API

---

### TASK-008: Celery Setup
**Priority**: P1 (High)  
**Estimate**: 2 hours  
**Spec**: `tasks/specs/008-celery-setup.md`

Configure Celery for async task processing.

**Acceptance Criteria**:
- [ ] Celery app configured with Redis broker
- [ ] Beat scheduler configured
- [ ] Task for RSS collection (periodic)
- [ ] Task for GDELT collection (periodic)
- [ ] Worker starts and processes tasks
- [ ] Beat schedules tasks correctly
- [ ] Task retry configuration
- [ ] Dead letter handling

---

### TASK-009: Telegram Harvester
**Priority**: P2 (Medium)  
**Estimate**: 6 hours  
**Spec**: `tasks/specs/009-telegram-harvester.md`

Build Telegram channel collector using Telethon.

**Acceptance Criteria**:
- [ ] Telethon client setup with session management
- [ ] Subscribe to configured channels
- [ ] Real-time message handling
- [ ] Historical backfill capability
- [ ] Map messages to RawItem schema
- [ ] Handle media attachments (extract text if possible)
- [ ] Rate limit compliance
- [ ] Session persistence across restarts
- [ ] Unit tests
- [ ] Integration test with real channel

---

## Phase 2: Processing Layer

### TASK-010: Embedding Service
**Priority**: P1 (High)  
**Estimate**: 2 hours  
**Spec**: `tasks/specs/010-embedding-service.md`

Create service for generating text embeddings.

**Acceptance Criteria**:
- [ ] Use OpenAI embedding API
- [ ] Batch processing for efficiency
- [ ] Caching to avoid re-computing
- [ ] Store embeddings in pgvector
- [ ] Unit tests

---

### TASK-011: Deduplication Service
**Priority**: P1 (High)  
**Estimate**: 3 hours  
**Spec**: `tasks/specs/011-deduplication-service.md`

Build deduplication using hash + embedding similarity.

**Acceptance Criteria**:
- [ ] URL normalization and dedup
- [ ] Content hash (SHA256) dedup
- [ ] Embedding similarity check (cosine > 0.92)
- [ ] Configurable similarity threshold
- [ ] Returns duplicate status + matched item ID
- [ ] Unit tests with various edge cases

---

### TASK-012: Event Clusterer
**Priority**: P1 (High)  
**Estimate**: 4 hours  
**Spec**: `tasks/specs/012-event-clusterer.md`

Cluster related articles into events.

**Acceptance Criteria**:
- [ ] Find similar items from last 48 hours
- [ ] Create new event or merge into existing
- [ ] Update event source count
- [ ] Update canonical summary on merge
- [ ] Track primary source (highest credibility)
- [ ] Unit tests

---

### TASK-013: LLM Classifier - Tier 1
**Priority**: P1 (High)  
**Estimate**: 4 hours  
**Spec**: `tasks/specs/013-llm-classifier-tier1.md`

Build Tier 1 (fast/cheap) LLM filter for relevance scoring.

**Acceptance Criteria**:
- [ ] Use gpt-4.1-nano for speed/cost
- [ ] Relevance score 0-10 for each configured trend
- [ ] Structured output with Pydantic
- [ ] Batch processing (multiple items per call)
- [ ] Cost tracking
- [ ] Items scoring <5 marked as "noise"
- [ ] Items scoring >=5 queued for Tier 2
- [ ] Unit tests with mock responses

---

### TASK-014: LLM Classifier - Tier 2
**Priority**: P1 (High)
**Estimate**: 6 hours
**Spec**: `tasks/specs/014-llm-classifier-tier2.md`

Build Tier 2 (thorough) LLM classification.

**Acceptance Criteria**:
- [ ] Use gpt-4o-mini for quality
- [ ] Extract: who, what, where, when, claims
- [ ] Assign categories from taxonomy
- [ ] For each relevant trend:
  - Signal type detected
  - Impact direction (escalatory/de-escalatory)
  - **Severity score (0.0-1.0)**: Magnitude of the signal (routine=0.2, significant=0.5, major=0.8, critical=1.0)
  - **Confidence score (0.0-1.0)**: LLM certainty in classification
- [ ] Generate 2-sentence summary
- [ ] Structured output with Pydantic
- [ ] Store results in event record
- [ ] Cost tracking (integrates with TASK-036)
- [ ] Unit tests with mock responses

**Note on Severity**: This distinguishes "routine military exercises" (severity=0.2) from "100k troops massing on border" (severity=0.9). The severity multiplies the indicator weight in delta calculation.

---

### TASK-015: Processing Pipeline
**Priority**: P1 (High)  
**Estimate**: 4 hours  
**Spec**: `tasks/specs/015-processing-pipeline.md`

Wire together the full processing pipeline.

**Acceptance Criteria**:
- [ ] Celery task triggered when new raw_item arrives
- [ ] Pipeline: dedup → embed → cluster → tier1 → (tier2 if relevant)
- [ ] Update item status through pipeline
- [ ] Error handling and retry logic
- [ ] Pipeline metrics (items processed, filtered, etc.)
- [ ] Integration test end-to-end

---

### TASK-036: Cost Protection & Budget Limits
**Priority**: P1 (Critical)
**Estimate**: 2-3 hours
**Spec**: `tasks/specs/036-cost-protection.md`

Prevent runaway API costs from bugs or high-volume news events.

**Acceptance Criteria**:
- [ ] `api_usage` table for tracking daily usage by tier
- [ ] `CostTracker` service with `check_budget()` and `record_usage()`
- [ ] All LLM calls check budget before execution
- [ ] `BudgetExceededError` raised when limits hit
- [ ] Pipeline enters "sleep mode" when budget exceeded (items stay pending)
- [ ] Alert logged at configurable threshold (default 80%)
- [ ] `GET /api/v1/budget` endpoint for status
- [ ] CLI command: `horadus budget status`
- [ ] Unit tests

**Why Critical**: Without this, a bug or major news event could burn through entire API budget in hours.

---

### TASK-040: LLM Provider Fallback
**Priority**: P1 (High)
**Estimate**: 3-4 hours
**ID Note**: Renumbered from legacy draft `TASK-038` to avoid collision with completed IDs.

Configure a secondary LLM provider/model and automatically switch when the primary is rate limited or down.

**Acceptance Criteria**:
- [ ] Provider configuration supports primary + secondary
- [ ] Automatic failover on rate limit (HTTP 429) and transient outages (HTTP 5xx/timeouts)
- [ ] Switch events are logged with reason and provider/model chosen
- [ ] Schema validation remains strict (no silent shape changes on fallback)
- [ ] Unit tests simulate rate limit/outage and verify failover behavior

---

### TASK-041: Model Evaluation Gold Set
**Priority**: P2 (Medium)
**Estimate**: 6-8 hours
**ID Note**: Renumbered from legacy draft `TASK-039` to avoid collision with completed IDs.

Create a small labeled dataset and a benchmark script to compare model/provider quality and cost.

**Acceptance Criteria**:
- [ ] 200 labeled articles/items (gold set) in a repo-friendly format (e.g., JSONL) stored under `ai/eval/`
- [ ] Gold set file: `ai/eval/gold_set.jsonl`
- [ ] Labels include: relevance, trend match, signal type, direction, severity, and confidence (as applicable)
- [ ] Benchmark script produces accuracy metrics + estimated cost per item; outputs saved under `ai/eval/results/`
- [ ] Compare `gpt-4o-mini` against at least one alternative configuration
- [ ] Document how to run the benchmark and interpret results

---

### TASK-043: Eval Threshold Alignment + Label Provenance
**Priority**: P1 (High)
**Estimate**: 2-3 hours

Align benchmark routing metrics with runtime thresholding and make dataset label provenance explicit.

**Acceptance Criteria**:
- [ ] Queue-accuracy metric uses runtime `TIER1_RELEVANCE_THRESHOLD` (not a hardcoded cutoff)
- [ ] Gold-set rows support `label_verification` provenance metadata
- [ ] Benchmark output includes queue threshold + label provenance counts
- [ ] CLI supports a human-only evaluation mode for `label_verification=human_verified`
- [ ] Unit tests cover threshold alignment and human-only filtering behavior

---

### TASK-044: Curated Human-Verified Gold Dataset [REQUIRES_HUMAN]
**Priority**: P1 (High)
**Estimate**: 8-12 hours (human review)

Create a curated benchmark set from real items with manual human verification of labels.

**Acceptance Criteria**:
- [ ] Dataset sourced from representative real items across tracked trends/noise cases
- [ ] Each row reviewed and approved by a human (`label_verification=human_verified`)
- [ ] Tier-1 and Tier-2 labels validated for consistency and edge cases
- [ ] Labeling rubric documented in `ai/eval/README.md`
- [ ] Human reviewer sign-off recorded in sprint notes before marking DONE

---

### TASK-045: Gold-Set Quality Audit Tooling
**Priority**: P1 (High)
**Estimate**: 2-3 hours
**Spec**: `tasks/specs/045-gold-set-audit-tooling.md`

Add automated audit checks for evaluation dataset quality before benchmark runs.

**Acceptance Criteria**:
- [ ] CLI command audits gold-set provenance, diversity, and Tier-2 coverage
- [ ] Audit output saved as JSON artifact under `ai/eval/results/`
- [ ] Audit reports warnings for no human-verified rows and heavy duplication
- [ ] Optional non-zero exit mode for warning-gated workflows
- [ ] Unit tests cover warning and pass scenarios

---

### TASK-050: Upgrade Tier 2 LLM from gpt-4o-mini to gpt-4.1-mini
**Priority**: P2 (Medium)
**Estimate**: 1-2 hours

`gpt-4o-mini` is now 1-2 generations behind; `gpt-4.1-mini` is a drop-in upgrade (same provider, OpenAI-compatible) with significantly better classification, structured JSON, and reasoning quality at comparable cost.

**Acceptance Criteria**:
- [ ] Update `LLM_TIER2_MODEL` default from `gpt-4o-mini` to `gpt-4.1-mini` in `src/core/config.py`
- [ ] Update `LLM_REPORT_MODEL` and `LLM_RETROSPECTIVE_MODEL` defaults to match
- [ ] Update Tier 2 pricing constants in `cost_tracker.py` ($0.15/$0.60 → $0.40/$1.60 per M tokens)
- [ ] Update `.env.example` with DeepSeek V3.2 as recommended secondary/failover for Tier 2
- [ ] Add "2026-02 Review" section to `docs/adr/002-llm-provider.md` documenting the evaluation and decision
- [ ] Tests pass with updated defaults

**Context**: 2026-02 model evaluation confirmed Tier 1 (`gpt-4.1-nano`) and embeddings (`text-embedding-3-small`) are still optimal. DeepSeek V3.2 ($0.28/$0.42) is the recommended failover — 85-95% of GPT-5 quality, OpenAI-compatible API.

---

## Phase 3: Trend Engine

### TASK-016: Trend Management
**Priority**: P1 (High)  
**Estimate**: 3 hours  
**Spec**: `tasks/specs/016-trend-management.md`

API endpoints for managing trends.

**Acceptance Criteria**:
- [ ] GET /api/v1/trends - list all trends
- [ ] POST /api/v1/trends - create trend
- [ ] GET /api/v1/trends/{id} - get trend with current probability
- [ ] PATCH /api/v1/trends/{id} - update trend config
- [ ] DELETE /api/v1/trends/{id} - deactivate trend
- [ ] Load trends from config/trends/ YAML files
- [ ] Unit tests

---

### TASK-017: Trend Engine Core
**Priority**: P0 (Critical)  
**Estimate**: 4 hours  
**Spec**: `tasks/specs/017-trend-engine-core.md`

Implement log-odds probability engine.

**Acceptance Criteria**:
- [ ] prob_to_logodds and logodds_to_prob functions
- [ ] calculate_evidence_delta function
- [ ] apply_evidence function (update trend log_odds)
- [ ] apply_decay function (time-based decay)
- [ ] get_probability function
- [ ] get_direction function (rising/falling/stable)
- [ ] Comprehensive unit tests
- [ ] Test with various scenarios

---

### TASK-018: Evidence Recording
**Priority**: P1 (High)  
**Estimate**: 2 hours  
**Spec**: `tasks/specs/018-evidence-recording.md`

Store evidence trail for all probability updates.

**Acceptance Criteria**:
- [ ] Create trend_evidence record for each update
- [ ] Store all scoring factors
- [ ] Store delta_log_odds and reasoning
- [ ] API: GET /api/v1/trends/{id}/evidence
- [ ] Query evidence by date range
- [ ] Unit tests

---

### TASK-019: Trend Snapshots
**Priority**: P1 (High)  
**Estimate**: 2 hours  
**Spec**: `tasks/specs/019-trend-snapshots.md`

Periodic snapshots for time-series tracking.

**Acceptance Criteria**:
- [ ] Celery task to snapshot all trends hourly
- [ ] Store in trend_snapshots table (TimescaleDB)
- [ ] API: GET /api/v1/trends/{id}/history
- [ ] Support date range queries
- [ ] Support downsampling (hourly/daily/weekly)
- [ ] Unit tests

---

### TASK-020: Decay Worker
**Priority**: P1 (High)  
**Estimate**: 2 hours  
**Spec**: `tasks/specs/020-decay-worker.md`

Apply time-based probability decay.

**Acceptance Criteria**:
- [ ] Celery task runs daily
- [ ] For each trend, apply decay toward baseline
- [ ] Use configured decay_half_life_days
- [ ] Log decay operations
- [ ] Unit tests

---

## Phase 4: Reporting

### TASK-021: Report Generator - Weekly
**Priority**: P1 (High)  
**Estimate**: 4 hours  
**Spec**: `tasks/specs/021-weekly-reports.md`

Generate weekly trend reports.

**Acceptance Criteria**:
- [ ] Celery task runs weekly (configurable day/time)
- [ ] For each active trend:
  - Current probability
  - Change from last week
  - Top 5 contributing events
  - Direction (rising/falling/stable)
- [ ] LLM generates narrative from computed data
- [ ] Store report in database
- [ ] API: GET /api/v1/reports
- [ ] API: GET /api/v1/reports/{id}
- [ ] Unit tests

---

### TASK-022: Report Generator - Monthly
**Priority**: P2 (Medium)  
**Estimate**: 3 hours  
**Spec**: `tasks/specs/022-monthly-reports.md`

Generate monthly trend reports with deeper analysis.

**Acceptance Criteria**:
- [ ] Celery task runs monthly
- [ ] Includes weekly report data
- [ ] Adds: category breakdown, source breakdown
- [ ] Trend comparison across time
- [ ] LLM generates executive summary
- [ ] Store and expose via API
- [ ] Unit tests

---

### TASK-023: Retrospective Analysis
**Priority**: P2 (Medium)  
**Estimate**: 4 hours  
**Spec**: `tasks/specs/023-retrospective-analysis.md`

Analyze how past classifications affected trends.

**Acceptance Criteria**:
- [ ] API: GET /api/v1/trends/{id}/retrospective
- [ ] Parameters: start_date, end_date
- [ ] Returns: pivotal events, category breakdown, accuracy assessment
- [ ] Identify which signals were most predictive
- [ ] LLM generates retrospective narrative
- [ ] Unit tests

---

## Phase 5: Polish & Deploy

### TASK-024: API Documentation
**Priority**: P2 (Medium)  
**Estimate**: 2 hours

Finalize OpenAPI documentation.

**Acceptance Criteria**:
- [ ] All endpoints documented
- [ ] Request/response examples
- [ ] Authentication documented
- [ ] Hosted at /docs

---

### TASK-025: Authentication
**Priority**: P2 (Medium)  
**Estimate**: 3 hours

Add API key authentication.

**Acceptance Criteria**:
- [ ] API key validation middleware
- [ ] Rate limiting per key
- [ ] Key management endpoints
- [ ] Unit tests

---

### TASK-026: Monitoring & Alerting
**Priority**: P2 (Medium)  
**Estimate**: 3 hours

Set up observability.

**Acceptance Criteria**:
- [ ] Structured logging (JSON)
- [ ] Prometheus metrics endpoint
- [ ] Key metrics: items processed, LLM costs, errors
- [ ] Health checks for dependencies
- [ ] Unit tests

---

### TASK-027: Deployment Configuration
**Priority**: P2 (Medium)  
**Estimate**: 4 hours

Production deployment setup.

**Acceptance Criteria**:
- [ ] Dockerfile for API
- [ ] Dockerfile for worker
- [ ] docker-compose.prod.yml
- [ ] Environment variable documentation
- [ ] Deployment guide

---

## Phase 6: Calibration & Learning (Expert Recommendations)

### TASK-028: Risk Levels and Probability Bands
**Priority**: P1 (High)  
**Estimate**: 2 hours  
**Spec**: `tasks/specs/028-risk-levels.md`

Replace single probability numbers with risk levels and confidence bands.

**Acceptance Criteria**:
- [ ] Risk level enum: Low / Guarded / Elevated / High / Severe
- [ ] Probability band calculation (confidence interval)
- [ ] Confidence rating: Low / Medium / High
- [ ] API returns all three alongside raw probability
- [ ] Unit tests for risk level mapping

---

### TASK-029: Enhanced Trend Definitions
**Priority**: P2 (Medium)  
**Estimate**: 3 hours  
**Spec**: `tasks/specs/029-enhanced-trend-config.md`

Add leading/lagging indicators, disqualifiers, and falsification criteria.

**Acceptance Criteria**:
- [ ] Indicator type field: leading vs lagging
- [ ] Disqualifiers section in trend config
- [ ] Falsification criteria (what would change assessment)
- [ ] Schema validation for new fields
- [ ] Update eu-russia.yaml with new fields
- [ ] Documentation updated

---

### TASK-030: Event Lifecycle Tracking
**Priority**: P1 (High)  
**Estimate**: 3 hours  
**Spec**: `tasks/specs/030-event-lifecycle.md`

Track event progression: emerging → confirmed → fading → archived.

**Acceptance Criteria**:
- [ ] lifecycle_status field on events table
- [ ] last_mention_at timestamp
- [ ] Automatic promotion: emerging → confirmed (3+ sources)
- [ ] Automatic demotion: confirmed → fading (48h no mentions)
- [ ] Celery task for lifecycle updates
- [ ] Filter events by lifecycle in API
- [ ] Unit tests

---

### TASK-031: Source Tier and Reporting Type
**Priority**: P2 (Medium)  
**Estimate**: 2 hours  
**Spec**: `tasks/specs/031-source-tiers.md`

Distinguish primary sources from re-reporting and aggregators.

**Acceptance Criteria**:
- [ ] source_tier field: primary / wire / major / regional / aggregator
- [ ] reporting_type field: firsthand / secondary / aggregator
- [ ] Tier multipliers in credibility calculation
- [ ] Update RSS config with tiers
- [ ] Migration for existing sources

---

### TASK-032: Trend Outcomes for Calibration
**Priority**: P1 (High)  
**Estimate**: 4 hours  
**Spec**: `tasks/specs/032-trend-outcomes.md`

Track resolved outcomes to measure prediction accuracy.

**Acceptance Criteria**:
- [ ] trend_outcomes table
- [ ] API: POST /trends/{id}/outcomes (record outcome)
- [ ] API: GET /trends/{id}/calibration (calibration stats)
- [ ] Brier score calculation
- [ ] Calibration bucket analysis query
- [ ] Documentation on how to record outcomes

---

### TASK-033: Contradiction Detection
**Priority**: P2 (Medium)  
**Estimate**: 3 hours  
**Spec**: `tasks/specs/033-contradiction-detection.md`

Detect when sources contradict each other on claims.

**Acceptance Criteria**:
- [ ] has_contradictions flag on events
- [ ] contradiction_notes field
- [ ] LLM prompt updated to detect contradictions
- [ ] API filter for contradicted events
- [ ] Unit tests

---

### TASK-034: Human Feedback API
**Priority**: P2 (Medium)
**Estimate**: 3 hours
**Spec**: `tasks/specs/034-human-feedback.md`

Allow human corrections and annotations.

**Acceptance Criteria**:
- [ ] human_feedback table
- [ ] POST /events/{id}/feedback (pin, mark_noise, **invalidate**)
- [ ] POST /trends/{id}/override (manual delta adjustment)
- [ ] GET /feedback (list all feedback)
- [ ] Feedback affects future processing (marked noise skipped)
- [ ] **Invalidate event**: Recalculates trend by removing event's log-odds contribution
- [ ] Audit trail preserved

**Note**: The "invalidate" action is critical for handling LLM hallucinations or misclassifications. When an event is invalidated, the system must reverse its probability impact on all affected trends.

---

### TASK-035: Calibration Dashboard & Early Visibility
**Priority**: P2 (Medium) - **Bumped from P3**
**Estimate**: 4 hours

Build calibration analysis and early visibility into trend movements.

**Acceptance Criteria**:
- [ ] CLI command: `horadus trends status` (quick view of all trends)
- [ ] Calibration curve generation
- [ ] Brier score over time
- [ ] "When we said X%, it happened Y% of the time"
- [ ] Report endpoint: GET /reports/calibration
- [ ] Simple trend movement visualization (text-based or basic chart)

**Why Bumped**: Expert advice: "You need to see the graph moving to know if your math is broken." Without visibility, you're flying blind on weight tuning.

**Early Phase**: Even before full calibration data, provide simple status output:
```
horadus trends status
# EU-Russia: 12.3% (Guarded) ↑ +2.1% this week
# Top movers: military_movement (3), diplomatic_breakdown (1)
```

---

## Phase 7: Release and Operations Governance

### TASK-046: Release Process Runbook
**Priority**: P1 (High)
**Estimate**: 2-3 hours

Create a formal release workflow document for versioning, tagging, rollout, and rollback.

**Acceptance Criteria**:
- [ ] Add `docs/RELEASING.md` with a step-by-step release checklist
- [ ] Document version bump workflow and Git tagging conventions (e.g. `vX.Y.Z`)
- [ ] Define changelog/update policy (manual or automated) and required release notes
- [ ] Include pre-release quality gates (tests, lint, mypy, migrations, eval policy checks)
- [ ] Include production rollout + post-deploy verification steps
- [ ] Include rollback criteria and rollback procedure linked to deployment runbook
- [ ] Link release runbook from `README.md` and deployment docs

---

### TASK-047: Pinned Evaluation Baseline Artifact
**Priority**: P1 (High)
**Estimate**: 1-2 hours

Create and maintain a committed pinned evaluation baseline artifact for prompt/model comparisons.

**Acceptance Criteria**:
- [ ] Generate a benchmark artifact from current accepted configuration
- [ ] Commit pinned baseline JSON at `ai/eval/baselines/current.json`
- [ ] Ensure baseline metadata captures run context (date, config, dataset scope, threshold mode)
- [ ] Update eval documentation to reference the concrete baseline file path
- [ ] Add a simple update procedure for replacing baseline on approved prompt/model changes
- [ ] Confirm policy docs and baseline README are aligned with the committed artifact

---

### TASK-048: CI Gate Hardening for Integration and Security
**Priority**: P1 (High)
**Estimate**: 2-3 hours

Make integration and security checks enforceable CI gates (no silent pass-through on failures).

**Acceptance Criteria**:
- [ ] Remove permissive `||` fallbacks that mask failures in integration test job
- [ ] Remove permissive `||` fallback that masks Bandit failures (or explicitly scope intentional ignores in config)
- [ ] Keep lockfile validation and existing lint/type/unit jobs intact
- [ ] Document expected CI failure behavior and remediation path in repo docs
- [ ] Verify CI workflow syntax and job dependency graph after changes
- [ ] Add/update tests or fixtures if needed to keep gates deterministic

---

### TASK-049: Documentation Drift and Consistency Cleanup
**Priority**: P2 (Medium)
**Estimate**: 1-2 hours

Resolve inconsistencies between status docs and repository reality.

**Acceptance Criteria**:
- [ ] Reconcile `PROJECT_STATUS.md` claims with actual files/features in repo
- [ ] Fix naming/path inconsistencies in `README.md` (project directory/repo naming)
- [ ] Remove or correct references to missing artifacts (for example absent compose overlay files)
- [ ] Ensure cross-links between README, deployment, environment, and eval docs are valid
- [ ] Add a lightweight doc freshness check process (owner + when to update)

---

## Phase 8: Assessment-Driven Hardening (2026-02)

### TASK-051: API Key Hash Hardening and Migration
**Priority**: P1 (High)
**Estimate**: 3-4 hours

Harden API key storage and verification to reduce credential exposure risk if persisted metadata is leaked.

**Acceptance Criteria**:
- [ ] Replace plain SHA-256 key hashes with salted, memory-hard hashes (scrypt/argon2/pbkdf2) and hash-version metadata
- [ ] Use constant-time verification for key comparison paths
- [ ] Support backward-compatible validation for existing persisted keys and migrate on successful auth
- [ ] Add unit tests for legacy hash compatibility and new hash verification behavior

---

### TASK-052: Distributed Rate Limiting + Admin Audit Trail
**Priority**: P1 (High)
**Estimate**: 4-5 hours

Move per-key limits out of process memory and add traceability for privileged auth actions.

**Acceptance Criteria**:
- [ ] Add Redis-backed per-key rate limiting with TTL windows that works across multiple API instances
- [ ] Preserve `Retry-After` behavior with deterministic calculation
- [ ] Add structured audit logs for admin key management operations (create/revoke/rotate/list attempts)
- [ ] Add tests for multi-worker consistency and rate-limit edge behavior

---

### TASK-053: Atomic Budget Enforcement Under Concurrency
**Priority**: P1 (Critical)
**Estimate**: 3-4 hours

Eliminate race windows between budget checks and usage recording across concurrent workers.

**Acceptance Criteria**:
- [ ] Implement atomic budget reservation/check-record flow in one transactional path
- [ ] Prevent daily call and cost limit overshoot under concurrent worker execution
- [ ] Add concurrency-focused tests that simulate parallel Tier1/Tier2/embedding calls
- [ ] Add structured logging/metrics for budget reservation denials

---

### TASK-054: LLM Input Safety Guardrails (Injection + Token Precheck)
**Priority**: P1 (High)
**Estimate**: 4-6 hours

Harden Tier1/Tier2 input handling against malicious prompt content and context-window overruns.

**Acceptance Criteria**:
- [ ] Delimit untrusted article/context content explicitly in Tier1/Tier2 payload contracts
- [ ] Add explicit prompt rules to ignore instructions embedded in article content
- [ ] Add token estimation pre-checks with safe truncation markers before LLM calls
- [ ] Add tests for adversarial prompt-injection content and overlong context inputs

---

### TASK-055: Stuck Processing Reaper Worker
**Priority**: P1 (High)
**Estimate**: 2-3 hours

Recover items stranded in `processing` after worker crashes or abnormal terminations.

**Acceptance Criteria**:
- [ ] Add scheduled worker task to reset stale `processing` items to `pending`
- [ ] Add configurable timeout threshold for stale processing detection
- [ ] Emit metrics/logs for reset counts and affected item IDs
- [ ] Add tests for reset and non-reset scenarios

---

### TASK-056: Bounded Embedding Cache
**Priority**: P2 (Medium)
**Estimate**: 1-2 hours

Prevent unbounded memory growth from embedding cache accumulation.

**Acceptance Criteria**:
- [ ] Replace unbounded in-memory embedding cache with bounded LRU cache
- [ ] Add configurable max cache size and sensible defaults
- [ ] Preserve cache hit behavior and current embedding output correctness
- [ ] Add tests for eviction behavior and cache hit/miss accounting

---

### TASK-057: Runtime Resilience Guardrails
**Priority**: P1 (High)
**Estimate**: 4-5 hours

Strengthen runtime safety for production operations and health visibility.

**Acceptance Criteria**:
- [ ] Add CPU/memory limits in `docker-compose.prod.yml` for API/worker/beat/postgres/redis services
- [ ] Add worker activity health signal (heartbeat or recent-task timestamp) to health reporting
- [ ] Add Timescale retention/compression policy migration for `trend_snapshots`
- [ ] Add configurable DB pool timeout setting and document production defaults

---

### TASK-058: Vector Retrieval Quality Tuning (HNSW vs IVFFlat)
**Priority**: P2 (Medium)
**Estimate**: 4-6 hours

Tune event/raw-item vector retrieval quality for current small-table operating regime.

**Acceptance Criteria**:
- [ ] Add reproducible benchmark comparing IVFFlat vs HNSW (and/or exact search fallback) for recall/latency
- [ ] Select and document default ANN strategy for current dataset sizes
- [ ] Add migration/update path for selected index strategy
- [ ] Add tests covering nearest-neighbor behavior against configured similarity thresholds

---

### TASK-059: Active-Learning Human Review Queue
**Priority**: P1 (High)
**Estimate**: 4-6 hours

Prioritize analyst review using expected information gain to speed high-value labeling.

**Acceptance Criteria**:
- [ ] Implement ranking score using uncertainty x projected delta x contradiction risk
- [ ] Add `GET /api/v1/review-queue` endpoint with ranked review candidates
- [ ] Include payload fields needed for reviewer triage and label provenance updates
- [ ] Add tests for deterministic ranking and filter behavior

---

### TASK-060: Counterfactual Simulation API
**Priority**: P2 (Medium)
**Estimate**: 4-6 hours

Provide non-persistent "what-if" probability projections using deterministic trend math.

**Acceptance Criteria**:
- [ ] Support "remove historical event impact" simulation mode
- [ ] Support "inject hypothetical signal" simulation mode
- [ ] Expose projected probability + delta + factor breakdown without DB mutation
- [ ] Add tests ensuring simulation calls are side-effect free

---

### TASK-061: Recency-Aware Novelty + Per-Indicator Decay
**Priority**: P1 (High)
**Estimate**: 3-4 hours

Improve evidence math realism by removing coarse novelty cliffs and global decay assumptions.

**Acceptance Criteria**:
- [ ] Replace binary novelty with continuous recency-aware novelty scoring
- [ ] Add optional per-indicator decay half-life support in trend definitions
- [ ] Keep factor provenance explicit in `TrendEvidence` for explainability
- [ ] Add unit tests validating expected deltas across recency and indicator decay scenarios

---

### TASK-062: Hermetic Integration Test Environment Parity
**Priority**: P1 (High)
**Estimate**: 4-6 hours

Align local and CI integration environments to eliminate config drift and silent failures.

**Acceptance Criteria**:
- [ ] Ensure CI uses pgvector-capable Postgres image consistent with local integration expectations
- [ ] Remove migration failure masking patterns in CI integration jobs
- [ ] Normalize integration DB credentials/URLs between local and CI fixtures
- [ ] Add/update integration fixtures for deterministic setup/teardown behavior

---

### TASK-063: Source Reliability Diagnostics (Read-Only)
**Priority**: P2 (Medium)
**Estimate**: 3-4 hours

Add visibility into source/tier outcome calibration before enabling any adaptive weighting.

**Acceptance Criteria**:
- [ ] Add source and source-tier reliability diagnostics in calibration reporting
- [ ] Include sample-size/confidence gating to avoid over-interpreting sparse outcomes
- [ ] Keep output advisory-only (no automatic source-weight mutations)
- [ ] Add tests for diagnostic aggregation and sparse-data guardrails

---

### TASK-064: Historical Replay and Champion/Challenger Harness
**Priority**: P2 (Medium)
**Estimate**: 5-7 hours

Enable safe evaluation of model/prompt/threshold changes before production rollout.

**Acceptance Criteria**:
- [ ] Add replay runner over historical items/events/evidence snapshots
- [ ] Support side-by-side config comparisons with shared dataset/time-window inputs
- [ ] Output quality/cost/latency comparison artifact suitable for release decisions
- [ ] Document promotion criteria for champion/challenger decisions

---

### TASK-065: Independence-Aware Corroboration and Claim Graph
**Priority**: P2 (Medium)
**Estimate**: 5-7 hours

Reduce false confidence from syndicated/derivative coverage by modeling claim-level independence.

**Acceptance Criteria**:
- [ ] Add normalized claim representation on events with support/contradiction links
- [ ] Compute corroboration factor from independent source clusters instead of raw source count
- [ ] Penalize derivative coverage in corroboration math
- [ ] Add tests for overcount prevention and contradiction-aware corroboration behavior

---

### TASK-066: Expand Trend Catalog to Multi-Trend Baseline [REQUIRES_HUMAN]
**Priority**: P1 (High)
**Estimate**: 6-10 hours (human analysis + review)

Reduce single-trend bottleneck by adding a minimal operational set of additional trend definitions.

**Acceptance Criteria**:
- [ ] Define at least 5 additional trend YAMLs with baseline/indicators/disqualifiers/falsification criteria
- [ ] Human analyst review and sign-off for each new trend definition
- [ ] Validate all new trend configs with existing sync/validation tooling
- [ ] Record trend-definition rationale and reviewer sign-off in sprint notes

---

### TASK-067: Report Narrative Prompt Hardening
**Priority**: P2 (Medium)
**Estimate**: 2-3 hours

Improve narrative usefulness while minimizing unsupported claims in weekly/monthly/retrospective reports.

**Acceptance Criteria**:
- [ ] Expand report prompts with explicit audience, uncertainty, and contradiction guidance
- [ ] Add guardrails that disallow unsupported entities/events not present in structured inputs
- [ ] Improve deterministic fallback narrative quality for no-LLM paths
- [ ] Add tests for prompt contract/output-shape validation where applicable

---

## Future Ideas (Not Scheduled)

- [ ] WebSocket for real-time trend updates
- [ ] Multi-language support
- [ ] Custom trend definitions via API
- [ ] Trend correlations (how trends affect each other)
- [ ] Knowledge graph of actors/orgs/locations (Neo4j if needed)
- [ ] Red-team mode (LLM argues opposite position)
- [ ] Fine-tuned classification model (once we have labeled data)
- [ ] PDF report generation
- [ ] Email report delivery
- [ ] Mobile push notifications for significant changes
- [ ] Historical accuracy learning (auto-adjust source credibility)
