# Backlog

All planned tasks for the Geopolitical Intelligence Platform.  
Tasks are organized by phase and priority.

---

## Task ID Policy

- Task IDs are global and never reused.
- Completed IDs are reserved permanently and tracked in `tasks/COMPLETED.md`.
- Next available task IDs start at `TASK-161`.
- Checklist boxes in this file are planning snapshots; canonical completion status lives in
  `tasks/CURRENT_SPRINT.md` and `tasks/COMPLETED.md`.

## Task Labels

- `[REQUIRES_HUMAN]`: task includes a mandatory manual step and must not be auto-completed by an agent.
- For `[REQUIRES_HUMAN]` tasks, agents may prepare instructions/checklists only and must stop for human completion.

## Task Branching Policy (Hard Rule)

- Every implementation task must be executed on a dedicated task branch created from `main`.
- Each task branch must contain changes for one `TASK-XXX` only.
- Starting a task branch must pass sequencing preflight (`make task-preflight`) and use guarded branch creation (`make task-start TASK=XXX NAME=short-name`).
- Task start is blocked unless `main` is clean + synced and there are no open non-merged task PRs for the current operator.
- Open one PR per task branch; merge only after required checks are green.
- Every task PR body must include a single canonical metadata line: `Primary-Task: TASK-XXX` (must match branch task ID).
- Delete merged task branches to reduce stale branch drift.
- Mandatory start sequence per task: `git switch main` → `git pull --ff-only` → create/switch task branch.
- Mandatory completion sequence per task: merge PR → delete branch → `git switch main` → `git pull --ff-only` and verify merge commit is present locally.
- Autonomous engineering-task completion is defined as full delivery lifecycle (implement → commit → push → PR → green checks → merge → local main sync).
- If any lifecycle step is blocked (permissions/CI/platform), stop at the furthest completed step and capture exact blocker + required manual action.
- If unrelated work appears, create a new task immediately but do not switch branches by default; continue current task unless the new work blocks current acceptance criteria or is urgent.
- Never mix two tasks in one commit/PR; blockers must be done on a separate task branch after a safe checkpoint.

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

### TASK-068: Gold-Set Change Governance and Baseline Supersession
**Priority**: P1 (High)
**Estimate**: 1-2 hours

Define how evaluation baselines are handled when the gold-set content/labels change.

**Acceptance Criteria**:
- [ ] Document that gold-set content/label updates supersede prior pass/fail baseline comparisons
- [ ] Document baseline lifecycle (`current.json` promotion + `history/` archival for replaced baselines)
- [ ] Ensure benchmark artifacts include dataset fingerprint metadata for comparison integrity
- [ ] Update eval policy and baseline docs with a concrete operator checklist for dataset-version transitions
- [ ] Keep process aligned with `[REQUIRES_HUMAN]` gold-set curation flow (`TASK-044`)

---

### TASK-069: Baseline Source-of-Truth Unification for Decay
**Priority**: P1 (High)
**Estimate**: 2-3 hours

Fix baseline inconsistency so trend decay always uses the canonical stored baseline.

**Acceptance Criteria**:
- [ ] Update decay logic to use `Trend.baseline_log_odds` as the single source of truth (no decay fallback to `definition.baseline_probability`)
- [ ] Keep `definition.baseline_probability` synchronized on trend create/update/config-sync paths for metadata consistency
- [ ] Add one-time baseline backfill to align existing `definition.baseline_probability` values with stored `baseline_log_odds`
- [ ] Add unit tests covering stale/missing `definition.baseline_probability` and confirming decay targets DB baseline
- [ ] Update docs to clarify canonical baseline field and synchronization behavior

---

### TASK-070: Trend Baseline Prior Review and Sign-Off [REQUIRES_HUMAN]
**Priority**: P1 (High)
**Estimate**: 3-5 hours (human analysis + review)

Manually validate whether initial trend baselines reflect defensible priors before relying on long-run decay behavior.

**Acceptance Criteria**:
- [ ] Human analyst reviews baseline probability for each active trend and documents rationale + date stamp
- [ ] Human analyst approves or adjusts each baseline prior (with justification) in config/API records
- [ ] Baseline decisions are logged in sprint notes with reviewer sign-off
- [ ] Post-review check confirms DB baseline and trend definition baseline are consistent for reviewed trends
- [ ] Task remains blocked for autonomous completion until explicit human sign-off is recorded

---

### TASK-071: Migration Drift Quality Gates
**Priority**: P1 (High)
**Estimate**: 1-2 hours

Add enforceable migration parity gates so schema drift is caught before tests/release checks.

**Acceptance Criteria**:
- [ ] Add a reusable migration-drift check script that fails when current DB revision != Alembic head
- [ ] Include optional strict Alembic autogenerate parity mode (`MIGRATION_GATE_VALIDATE_AUTOGEN=true`)
- [ ] Wire migration gate into local integration workflow (Make target / integration test path)
- [ ] Wire migration gate into CI integration path before tests execute
- [ ] Document migration gate command(s) in release and deployment runbooks

---

### TASK-072: Runtime Migration Parity Health Signal
**Priority**: P1 (High)
**Estimate**: 2-3 hours

Expose schema revision parity at runtime to prevent long-lived drift in always-on environments.

**Acceptance Criteria**:
- [ ] Add startup/runtime check that compares app DB revision to Alembic head
- [ ] Surface migration parity state in `/health` payload for operators
- [ ] Add strict mode option to fail startup when migration drift is detected
- [ ] Add tests for healthy, drifted, and strict-mode startup behavior
- [ ] Document runtime migration parity controls in environment/deployment docs

---

### TASK-073: Alembic Autogenerate Baseline Drift Cleanup
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Resolve existing model/schema parity diffs so `alembic check` can be enforced as a fail-closed default gate.

**Acceptance Criteria**:
- [ ] Reproduce and document current `alembic check` drift findings in a deterministic local command path
- [ ] Align SQLAlchemy models and migrations to eliminate known autogenerate drift (server-default/index metadata mismatches)
- [ ] Add or adjust migration(s) where needed so upgraded DB state matches model metadata
- [ ] Validate `alembic check` passes on the integration DB after `alembic upgrade head`
- [ ] Add/adjust tests to prevent regression of the fixed drift cases

---

### TASK-074: Enforce Strict Alembic Check Gate by Default
**Priority**: P1 (High)
**Estimate**: 1-2 hours

Enable strict autogenerate parity validation in default local and CI quality gates after baseline cleanup.

**Acceptance Criteria**:
- [ ] Set migration gate strict mode (`MIGRATION_GATE_VALIDATE_AUTOGEN=true`) in CI integration workflow
- [ ] Set migration gate strict mode in local integration path (`make test-integration`) by default
- [ ] Keep an explicit override path for emergency bypass (`MIGRATION_GATE_VALIDATE_AUTOGEN=false`) while documenting policy
- [ ] Update release/deployment/environment docs with strict-gate expectations and remediation steps
- [ ] Verify CI/local integration commands pass with strict mode enabled

---

### TASK-075: Container Secret Provisioning and Rotation Runbook
**Priority**: P1 (High)
**Estimate**: 2-4 hours  
**Spec**: `tasks/specs/075-container-secret-provisioning-rotation.md`

Standardize production secret handling for containerized deploys using mounted
secret files + `*_FILE` variables, with a documented low-risk rotation workflow.

**Acceptance Criteria**:
- [ ] Document production secret provisioning via read-only mounted files and `*_FILE` environment variables (no raw secrets in `.env`)
- [ ] Provide a concrete host-side secret layout example and Docker Compose mount pattern for `api`, `worker`, and `beat`
- [ ] Document key rotation workflow (prepare new secret, apply mount/env updates, restart/recreate app containers, verify health)
- [ ] Document emergency rollback flow for failed secret rotation
- [ ] Update deployment and environment docs with an operator checklist for secret hygiene (`chmod`, ownership, access scope)

---

### TASK-076: Trend Taxonomy Contract and Gold-Set Validation Gate
**Priority**: P1 (High)
**Estimate**: 3-5 hours  
**Spec**: `tasks/specs/076-trend-taxonomy-validation-gate.md`

Add an enforceable validation gate that prevents `trend_id`/schema drift between
`config/trends/*.yaml` and evaluation datasets (gold sets).

**Acceptance Criteria**:
- [ ] Add a reusable validation command/script that loads and validates all trend YAMLs via `TrendConfig`
- [ ] Fail when trend `id` values are duplicated or missing in trend configs
- [ ] Validate gold-set `tier2.trend_id` values are members of configured trend IDs
- [ ] Validate gold-set `tier1.trend_scores` keys match configured trend IDs (strict mode) with a documented subset/lenient mode if needed
- [ ] Validate `tier2.signal_type` exists in configured trend indicators for the selected `trend_id` (strict or warning mode, documented)
- [ ] Add unit tests for pass/fail scenarios (duplicate IDs, unknown trend IDs, key mismatch, unknown signal types)
- [ ] Wire validation into local/CI quality gate path and document usage

---

### TASK-077: Cost-First Pipeline Ordering [REQUIRES_HUMAN]
**Priority**: P1 (High)
**Estimate**: 3-5 hours

Reduce avoidable compute cost by ensuring high-noise items are filtered before
embedding/clustering work where feasible.

**Acceptance Criteria**:
- [ ] Refactor pipeline flow so Tier-1 relevance filtering runs before embedding + clustering for new pending raw items
- [ ] Keep deterministic duplicate suppression behavior intact and idempotent
- [ ] Ensure Tier-1 noise items do not trigger embedding API calls or clustering operations
- [ ] Preserve metric accounting for scanned/noise/classified flows after reordering
- [ ] Add/adjust unit and integration tests for reordered pipeline behavior

---

### TASK-078: Tier-1 Batch Classification in Orchestrator
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Use existing Tier-1 batch capability from orchestrator execution instead of
single-item invocation to improve token/call efficiency.

**Acceptance Criteria**:
- [ ] Replace per-item Tier-1 invocation with batched `classify_items` orchestration
- [ ] Respect configured Tier-1 batch-size controls
- [ ] Preserve one-to-one mapping from item to Tier-1 result with deterministic ordering
- [ ] Keep budget, retry, and failure handling semantics unchanged
- [ ] Add/adjust tests for batch result mapping and partial failure handling

---

### TASK-079: Periodic Pending Processing Schedule
**Priority**: P1 (High)
**Estimate**: 2-3 hours

Prevent pending-item stalls during quiet ingestion periods by adding periodic
`workers.process_pending_items` scheduling.

**Acceptance Criteria**:
- [ ] Add Celery beat schedule entry for `workers.process_pending_items`
- [ ] Gate schedule by `ENABLE_PROCESSING_PIPELINE`
- [ ] Add configurable interval setting for periodic pending processing cadence
- [ ] Ensure schedule is idempotent and safe under concurrent worker execution
- [ ] Add tests for beat schedule composition and setting-driven enable/disable behavior

---

### TASK-080: Telegram Collector Task Wiring [REQUIRES_HUMAN]
**Priority**: P2 (Medium)
**Estimate**: 3-5 hours

Wire existing Telegram harvester into worker task and scheduler paths.

**Acceptance Criteria**:
- [ ] Add `workers.collect_telegram` task implementation in worker tasks module
- [ ] Add Celery routing and beat scheduling for Telegram collection
- [ ] Gate execution via `ENABLE_TELEGRAM_INGESTION`
- [ ] Add configurable Telegram collection interval setting
- [ ] Include Telegram in source-freshness monitoring/reporting and catch-up eligibility when enabled
- [ ] Add tests for scheduling/task wiring and disabled-mode behavior

---

### TASK-081: Readiness Probe HTTP Semantics Fix
**Priority**: P1 (High)
**Estimate**: 1-2 hours

Ensure readiness endpoint returns proper non-2xx status when dependencies fail.

**Acceptance Criteria**:
- [ ] Update `/health/ready` to return HTTP 503 on readiness failures
- [ ] Keep success response as HTTP 200 with stable payload shape
- [ ] Preserve structured warning logs for failure reasons
- [ ] Add/adjust API tests validating status-code semantics for success/failure

---

### TASK-082: Vector Index Profile Parity (Model vs Migration)
**Priority**: P1 (High)
**Estimate**: 1-2 hours

Align vector index metadata with deployed migration profile to avoid drift and
operator confusion.

**Acceptance Criteria**:
- [ ] Align SQLAlchemy model metadata index profile with current migration-managed profile (`lists=64`) or explicitly document intentional divergence
- [ ] Ensure `alembic check` remains clean after alignment
- [ ] Add/adjust tests asserting expected vector index metadata values
- [ ] Update docs where vector index profile is referenced

---

### TASK-083: Documentation and OpenAPI Drift Cleanup
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Remove stale statements that conflict with current implementation and hardening
state.

**Acceptance Criteria**:
- [ ] Update `docs/ARCHITECTURE.md` sections that still describe now-implemented features as future work
- [ ] Refresh or explicitly archive stale `docs/POTENTIAL_ISSUES.md` snapshot content so status labels are accurate
- [ ] Fix stale OpenAPI/auth wording in API bootstrap comments/descriptions
- [ ] Add concrete "last verified" timestamps where appropriate in operational docs

---

### TASK-084: Production Security Default Guardrails [REQUIRES_HUMAN]
**Priority**: P1 (High)
**Estimate**: 3-5 hours

Reduce accidental insecure deployments by enforcing fail-fast checks for
production runtime configuration.

**Acceptance Criteria**:
- [ ] Add production-mode validation that rejects known insecure defaults (e.g., weak `SECRET_KEY`)
- [ ] Add production-mode validation/policy for API auth enablement expectations
- [ ] Keep local development defaults ergonomic without weakening production safeguards
- [ ] Add tests for production config validation pass/fail paths
- [ ] Update environment/deployment docs with explicit production-safe defaults

---

### TASK-085: Require Explicit Admin Key for Key Management [REQUIRES_HUMAN]
**Priority**: P1 (High)
**Estimate**: 2-3 hours

Tighten admin access controls by removing permissive fallback behavior for auth
key-management endpoints.

**Acceptance Criteria**:
- [ ] Remove fallback that grants admin access from any authenticated API key when `API_ADMIN_KEY` is unset
- [ ] Require explicit admin credential configuration for key-management operations
- [ ] Return clear 403/configuration errors when admin key is missing or invalid
- [ ] Add/adjust endpoint tests for authorized, unauthorized, and misconfigured admin scenarios
- [ ] Update auth/deployment docs with explicit admin-key requirements

---

### TASK-086: LLM Route Retry Before Failover
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Improve LLM resilience by adding bounded retries for transient failures on each
route before escalating to failover.

**Acceptance Criteria**:
- [ ] Add configurable retry policy to `LLMChatFailoverInvoker` for transient errors (429/5xx/timeouts/connection errors)
- [ ] Retry primary route with bounded attempts and backoff before secondary failover route
- [ ] Retry secondary route with bounded attempts before final failure
- [ ] Preserve failover observability fields (provider/model/reason) and add retry-attempt telemetry
- [ ] Add unit tests covering primary retry success, failover after primary retries, and total failure after retry budgets

---

### TASK-087: Budget and Safety Guardrails for Report/Retrospective LLM Calls
**Priority**: P1 (High)
**Estimate**: 3-5 hours

Apply the same budget, failover, and input-safety protections used by Tier-1/2
to report and retrospective narrative generation paths.

**Acceptance Criteria**:
- [ ] Route report/retrospective LLM calls through budget enforcement (`CostTracker`) with usage recording
- [ ] Add provider/model failover for narrative calls on retryable failures
- [ ] Add payload-size/token precheck and safe truncation behavior for narrative prompts
- [ ] Ensure fallback narrative still works when budget is exceeded or both routes fail
- [ ] Add unit tests for budget denial, failover, and truncation behavior

---

### TASK-088: Remove or Integrate Legacy `_process_item` Pipeline Path
**Priority**: P2 (Medium)
**Estimate**: 1-2 hours

Eliminate duplicate execution logic in pipeline orchestration to reduce drift and
maintenance risk.

**Acceptance Criteria**:
- [ ] Confirm legacy `_process_item` path is unreachable from production flow
- [ ] Remove dead method or integrate it into the current execution path (single canonical implementation)
- [ ] Keep behavior/metrics parity with current orchestrator flow
- [ ] Add/adjust tests to ensure canonical path coverage and prevent regression

---

### TASK-089: Adopt Strict Structured Outputs for Tier-1/Tier-2
**Priority**: P1 (High)
**Estimate**: 3-5 hours

Migrate from JSON-object mode to strict schema-constrained outputs where
supported to improve output contract adherence.

**Acceptance Criteria**:
- [ ] Replace `response_format={"type": "json_object"}` with strict schema-driven output mode for Tier-1 and Tier-2 calls
- [ ] Keep existing Pydantic alignment/validation semantics and explicit error handling
- [ ] Preserve failover behavior and usage accounting
- [ ] Add tests for schema-constrained output pass/fail behavior
- [ ] Document model compatibility and fallback behavior if strict schema mode is unavailable

---

### TASK-090: Responses API Migration Plan and Pilot
**Priority**: P2 (Medium)
**Estimate**: 4-6 hours

Incrementally migrate chat-completions call sites to Responses API primitives
for forward compatibility.

**Acceptance Criteria**:
- [ ] Produce migration inventory for LLM call sites (Tier-1, Tier-2, reports, retrospectives, eval)
- [ ] Implement pilot migration for one non-critical call path with parity tests
- [ ] Define adapter layer to avoid duplicating provider-specific request/response plumbing
- [ ] Document migration strategy, risks, and rollback path
- [ ] Add follow-up checklist for remaining call sites

---

### TASK-091: Batch/Flex Evaluation and Backfill Cost Mode
**Priority**: P2 (Medium)
**Estimate**: 3-5 hours

Add optional lower-cost execution modes for non-real-time workloads
(benchmark/audit/replay/backfills).

**Acceptance Criteria**:
- [ ] Add optional batch-oriented mode for eligible offline commands
- [ ] Add optional flex/low-priority mode flags where provider capabilities support it
- [ ] Keep default behavior unchanged for real-time paths
- [ ] Add clear CLI/docs guidance for when to use each mode
- [ ] Add tests for option parsing and mode-selection behavior

---

### TASK-092: End-to-End OpenTelemetry Tracing
**Priority**: P2 (Medium)
**Estimate**: 4-8 hours

Introduce distributed tracing across API, workers, DB, Redis, and LLM calls.

**Acceptance Criteria**:
- [x] Add OpenTelemetry SDK/instrumentation dependencies and bootstrap config
- [x] Propagate trace context from FastAPI requests into Celery tasks
- [x] Instrument SQLAlchemy, HTTP/LLM client, and Redis interactions
- [x] Add configuration toggles and exporter configuration docs
- [x] Validate traces locally with a documented quickstart collector/viewer setup

---

### TASK-093: Vector Strategy Revalidation Cadence and Gate
**Priority**: P2 (Medium)
**Estimate**: 2-4 hours

Operationalize periodic ANN strategy revalidation as dataset scale and
distribution change over time.

**Acceptance Criteria**:
- [x] Define a revalidation cadence trigger (time- or data-growth-based)
- [x] Add command/runbook step to execute `horadus eval vector-benchmark` against current data profile
- [x] Define promotion criteria for changing IVFFlat/HNSW/exact strategy parameters
- [x] Persist benchmark artifacts and recommendation summary for historical comparison
- [x] Update docs with revalidation policy and operator checklist

---

### TASK-094: Pipeline Cost Metrics Parity in Observability
**Priority**: P1 (High)
**Estimate**: 1-3 hours

Fix mismatch between pipeline result payload and observability recorder so LLM
cost counters reflect actual run outputs.

**Acceptance Criteria**:
- [ ] Align `ProcessingPipeline.run_result_to_dict` and `record_pipeline_metrics` on expected cost fields
- [ ] Ensure estimated cost metrics are emitted for tier1, tier2, and embeddings (or explicitly remove/replace unsupported counters)
- [ ] Add tests covering recorder behavior with real pipeline result payload shape
- [ ] Confirm Prometheus counters update correctly in integration path

---

### TASK-095: CI Docs Freshness and Drift Guard
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Add automated checks that catch stale architecture/status/security statements
before merge.

**Acceptance Criteria**:
- [ ] Add a docs consistency check command that validates key invariants across `docs/`, `PROJECT_STATUS.md`, and runtime reality markers
- [ ] Fail CI when stale known-risk statements conflict with implemented controls (e.g., auth/rate-limit status claims)
- [ ] Add a lightweight allowlist/override mechanism for intentional temporary drift with explicit rationale
- [ ] Document remediation workflow when docs freshness gate fails

---

### TASK-096: Unified LLM Invocation Policy Layer
**Priority**: P2 (Medium)
**Estimate**: 4-6 hours
**Depends On**: None

Introduce a shared LLM invocation layer so all call sites enforce consistent
policy (budget, retry/failover, safety, and telemetry) without duplicated logic.

**Acceptance Criteria**:
- [x] Define shared invocation interface usable by Tier1, Tier2, reports, and retrospectives
- [x] Centralize budget checks/usage accounting, retry/failover handling, and safety preprocessing hooks
- [x] Preserve per-stage model/provider configurability
- [x] Introduce provider-neutral invocation error taxonomy so retry/failover behavior is not coupled to OpenAI exception types
- [x] Centralize per-model pricing metadata outside classifier classes to avoid hard-coded OpenAI-specific cost tables
- [x] Migrate at least one non-Tier path (report or retrospective) to the unified layer with parity tests
- [x] Document migration plan for remaining call sites

---

### TASK-097: Rate Limiter Smoothing Strategy (Token/Sliding Window)
**Priority**: P2 (Medium)
**Estimate**: 3-5 hours
**Depends On**: None

Reduce boundary-burst behavior from fixed-window rate limiting while preserving
operator clarity and deterministic throttling semantics.

**Acceptance Criteria**:
- [x] Add configurable rate-limit strategy modes (`fixed_window` default + `token_bucket` or `sliding_window`)
- [x] Implement distributed-safe algorithm path for Redis backend with atomic updates
- [x] Preserve or improve `Retry-After` correctness for denied requests
- [x] Add tests for minute-boundary burst behavior and multi-worker consistency
- [x] Update auth/deployment docs with strategy tradeoffs and recommended defaults

---

### TASK-098: Cross-Worker Semantic Cache for Tier-1/Tier-2
**Priority**: P2 (Medium)
**Estimate**: 4-6 hours
**Depends On**: TASK-096

Add a shared cache for repeated classification payloads so duplicate items across
workers do not repeatedly incur LLM cost.

**Acceptance Criteria**:
- [x] Add optional Redis-backed semantic cache for Tier-1 and Tier-2 response payloads
- [x] Define stable cache keys including model, prompt/version hash, and normalized input payload hash
- [x] Add TTL and size-control policy with safe fallback when cache backend is unavailable
- [x] Emit cache hit/miss metrics by stage and verify no correctness regressions on cache hits
- [x] Add tests for cache key stability, hit/miss behavior, and invalidation on prompt/model changes

---

### TASK-099: Backpressure-Aware Processing Scheduling
**Priority**: P2 (Medium)
**Estimate**: 3-5 hours
**Depends On**: None

Prevent queue thrash and uneven latency by adapting processing dispatch to queue
depth, worker saturation, and budget posture.

**Acceptance Criteria**:
- [x] Add scheduler controls that modulate `process_pending_items` dispatch based on backlog depth and in-flight processing
- [x] Keep ingestion-triggered fast-path queueing while preventing duplicate or excessive task fan-out
- [x] Add guardrails tying dispatch aggressiveness to budget-denial signals or budget headroom
- [x] Emit metrics for backlog depth, dispatch decisions, and throttle reasons
- [x] Add tests for normal, burst, and throttled scheduling scenarios

---

### TASK-100: Embedding Lineage and Re-Embedding Safety Gate
**Priority**: P1 (High)
**Estimate**: 3-5 hours
**Depends On**: None

Prevent silent vector-space drift when embedding models change, and make
re-embedding operations explicit and auditable.

**Acceptance Criteria**:
- [x] Add embedding lineage metadata for stored vectors (model identifier and created-at/version marker) on relevant entities
- [x] Prevent cross-model similarity comparisons in dedup/clustering paths (fail-safe skip or explicit fallback behavior)
- [x] Add operator command/report to detect mixed embedding-model populations and estimate re-embed scope
- [x] Document embedding-model upgrade workflow (cutover strategy, backfill order, rollback)
- [x] Add tests for lineage persistence and cross-model safety checks

---

### TASK-101: Multilingual Coverage Policy and Processing Guardrails
**Priority**: P2 (Medium)
**Estimate**: 3-5 hours
**Depends On**: None

Replace implicit multilingual handling with an explicit, testable language
coverage policy.

**Acceptance Criteria**:
- [x] Define launch language policy with explicit support targets: English (`en`), Ukrainian (`uk`), Russian (`ru`)
- [x] Add deterministic handling for unsupported languages (explicit skip/defer/translate mode, documented)
- [x] Emit language-segmented quality/cost metrics (ingested, Tier-1 pass rate, Tier-2 usage)
- [x] Add evaluation coverage for all three launch languages (`en`/`uk`/`ru`) including clustering and Tier-1/Tier-2 quality checks
- [x] Update architecture and ops docs with language support guarantees and limits

---

### TASK-102: Deterministic Grounding Verification for Narratives
**Priority**: P1 (High)
**Estimate**: 3-6 hours
**Depends On**: None

Reduce report/retrospective hallucination risk by validating generated narratives
against structured evidence before persistence.

**Acceptance Criteria**:
- [x] Add post-generation grounding verifier that checks narrative claims against provided statistics/top-events payload
- [x] Enforce fail-safe behavior (fallback narrative or flagged output) when unsupported claims exceed threshold
- [x] Persist grounding metadata (`grounding_status`, violation_count, optional references) with generated narratives
- [x] Expose grounding metadata in report/retrospective API responses for operator visibility
- [x] Add tests for grounded pass, unsupported-claim failure, and fallback behavior

---

### TASK-103: Six-Hour Polling Operating Profile and Defaults
**Priority**: P1 (High)
**Estimate**: 2-4 hours
**Depends On**: None

Align scheduler cadence and operational docs with the intended low-frequency
usage pattern (6-hour polling, daily review).

**Acceptance Criteria**:
- [x] Define and document a 6-hour ingestion profile with concrete baseline defaults: `RSS_COLLECTION_INTERVAL=360`, `GDELT_COLLECTION_INTERVAL=360`, `PROCESS_PENDING_INTERVAL_MINUTES=15`, `PROCESSING_PIPELINE_BATCH_SIZE=200`
- [x] Define source-window defaults for 6-hour mode to avoid gaps: `default_lookback_hours=12` for GDELT and `default_max_items_per_fetch=200` for RSS (with documented per-source override guidance)
- [x] Ensure scheduler/task behavior remains safe and deterministic for 6-hour cadence under bursty ingestion volumes
- [x] Add/adjust tests for beat schedule composition under 6-hour interval configuration
- [x] Update deployment/environment docs with a “6-hour mode” example and tuning checklist (`batch size`, `pending interval`, `worker concurrency`, `per-source max items`)
- [x] Add a short operator runbook for manual catch-up/replay when the service was down for multiple days

---

### TASK-104: Ingestion Completeness Watermark and Overlap Guard
**Priority**: P1 (High)
**Estimate**: 4-6 hours
**Depends On**: TASK-103

Prevent silent ingestion gaps by tracking per-source progress and enforcing safe
window overlap semantics.

**Acceptance Criteria**:
- [x] Persist per-source ingestion progress markers (last successful window end / high-water timestamp) for GDELT and RSS collectors
- [x] Enforce overlap-aware next-window calculation so delayed runs do not create uncovered time ranges
- [x] Add duplicate-safe behavior for overlap reprocessing (idempotent upsert/dedup remains authoritative)
- [x] Emit structured metrics/logs for window coverage (`expected_start`, `actual_start`, `gap_seconds`, `overlap_seconds`)
- [x] Add tests covering on-time runs, delayed runs, and restart-after-outage continuity

---

### TASK-105: Source Freshness SLO and Automatic Catch-Up Dispatch
**Priority**: P1 (High)
**Estimate**: 3-5 hours
**Depends On**: TASK-104

Detect missed collection windows early and recover automatically before data loss
accumulates.

**Acceptance Criteria**:
- [x] Define freshness SLO thresholds per collector (for example alert when `last_fetched_at` exceeds `2x` interval)
- [x] Add stale-source detector task that scans source freshness and emits alertable metrics/events
- [x] Trigger bounded catch-up dispatch when freshness SLO is violated (with dedup-safe overlap)
- [x] Add operator-visible status endpoint/CLI summary for stale sources and catch-up progress
- [x] Add tests for stale detection, catch-up triggering, and non-trigger cases

---

### TASK-106: Collector Retry and Timeout Hardening for Low-Frequency Mode
**Priority**: P1 (High)
**Estimate**: 2-4 hours
**Depends On**: TASK-103, TASK-104

Harden collector failure handling so a single transient outage does not wipe out
an entire 6-hour collection window.

**Acceptance Criteria**:
- [x] Review and tune retry/backoff settings for `workers.collect_rss` and `workers.collect_gdelt` against 6-hour cadence assumptions
- [x] Add explicit collector timeout budgets and failure classification (transient vs terminal) with deterministic logging fields
- [x] Add bounded requeue behavior for transient collector failures before marking run as failed
- [x] Add tests for transient network failures, prolonged outage behavior, and successful recovery paths
- [x] Document retry/timeout policy with concrete operational examples and expected worst-case recovery time

---

### TASK-107: Task Dependency Governance and Execution Policy
**Priority**: P2 (Medium)
**Estimate**: 1-2 hours
**Depends On**: None

Formalize dependency metadata and enforce a priority+dependency execution policy
for autonomous task selection.

**Acceptance Criteria**:
- [x] Add a hard-rule dependency policy section to task governance docs
- [x] Require and document `Depends On` metadata for non-atomic backlog tasks
- [x] Add dependency metadata for currently open engineering tasks (`TASK-096`..`TASK-106`)
- [x] Update sprint/project execution guidance to choose work by priority, then dependency readiness, then task ID
- [x] Keep `[REQUIRES_HUMAN]` gating behavior unchanged and explicit

---

### TASK-108: Working Tree Hygiene Audit and Disposition Plan
**Priority**: P1 (High)
**Estimate**: 1-2 hours
**Depends On**: None

Assess why local unstaged/untracked files accumulated, determine whether each
file group is required, and provide a concrete cleanup/commit disposition plan.

**Acceptance Criteria**:
- [x] Produce an inventory of current unstaged/untracked files grouped by purpose (runtime code, docs, generated artifacts, scratch)
- [x] Identify root causes for accumulation (task-scoped commits, generated outputs, abandoned local drafts)
- [x] Mark each file group with recommended action (`commit now`, `drop`, `archive`, `defer`)
- [x] Flag risky mismatches between task status docs and uncommitted implementation files
- [x] Document next-step cleanup sequence to return to a controlled/clean working tree

---

### TASK-109: Enforce Branch-Per-Task Delivery Policy
**Priority**: P1 (High)
**Estimate**: 30-60 minutes
**Depends On**: None

Add explicit governance rules requiring dedicated task branches and one-task PR
scope to prevent multi-task working tree drift.

**Acceptance Criteria**:
- [x] Add branch-per-task hard rule to `AGENTS.md`
- [x] Add matching branch policy to `tasks/BACKLOG.md`
- [x] Require single-task branch scope (`TASK-XXX`) and one PR per task branch
- [x] Require merge-only-on-green-checks and post-merge branch deletion
- [x] Require creating a new task + branch for unrelated mid-task discoveries

---

### TASK-110: Task Delivery Workflow Guardrails and Enforcement
**Priority**: P1 (High)
**Estimate**: 2-4 hours
**Depends On**: TASK-109

Codify and enforce the mandatory task delivery workflow (task-scoped branch/PR,
CI scope guard, local branch guard hooks, and main-branch protection defaults).

**Acceptance Criteria**:
- [x] Document hard workflow sequence (`main` sync → task branch → PR/green → merge/delete → `main` sync/verify)
- [x] Clarify unrelated-work handling: create follow-up task immediately but do not auto-switch branches unless blocked/urgent
- [x] Add CI guard that fails PRs when `TASK-XXX` is missing or multiple task IDs are present
- [x] Add local hook guard to block commit/push when branch name does not match task-branch pattern
- [x] Require and document one-task-per-branch and one-task-per-PR as non-negotiable
- [x] Apply repository protection settings: PR-required, checks-required, admins-enforced, direct-push blocked, linear history/squash-rebase policy

---

### TASK-111: Main Branch Merge-Completeness Audit
**Priority**: P1 (High)
**Estimate**: 1-2 hours
**Depends On**: None

Verify whether backlog-tracked implemented work is actually merged into `main`,
and produce a deterministic list of any missing/unmerged task work.

**Acceptance Criteria**:
- [x] Create an auditable inventory of task branches/PRs relative to `main`
- [x] Verify merge status for completed backlog tasks and identify gaps
- [x] Produce a list of missing/unmerged tasks (or explicit confirmation none missing)
- [x] Document findings with concrete references (branch, PR, commit where applicable)
- [x] Record recommended remediation sequence for any missing task merges

---

### TASK-112: Recover Stranded TASK-086..TASK-107 from `task-061`
**Priority**: P0 (Critical)
**Estimate**: 4-8 hours
**Depends On**: TASK-111

Recover backlog-tracked work that remained on `codex/task-061-recency-decay`
and was not merged into `main`, then reconcile task-status docs with recovered
implementation reality.

**Acceptance Criteria**:
- [x] Produce deterministic recovery matrix for `TASK-086..TASK-107` (recoverable commits vs missing artifacts)
- [x] Cherry-pick/apply recoverable committed changes from `codex/task-061-recency-decay` onto `main` lineage with conflict resolution
- [x] Reconstruct or explicitly defer tasks whose required files were never committed on `task-061` (with concrete follow-up tasks)
- [x] Run targeted validation for recovered areas (unit tests + CI green)
- [x] Update `tasks/BACKLOG.md`, `tasks/CURRENT_SPRINT.md`, `tasks/COMPLETED.md`, and `PROJECT_STATUS.md` to match recovered state

---

### TASK-113: Complete Deferred Eval Mode and Vector Revalidation Recovery
**Priority**: P1 (High)
**Estimate**: 3-5 hours
**Depends On**: TASK-112

Complete deferred recovery gaps for TASK-091 and TASK-093 where task-061 only
landed partial plumbing without full benchmark/runtime integration artifacts.

**Acceptance Criteria**:
- [x] Implement benchmark runtime support for `dispatch_mode` and `request_priority` flags
- [x] Restore vector revalidation artifacts (runbook + summary persistence + tests)
- [x] Validate eval docs/examples match actual CLI/runtime behavior
- [x] Add/update unit tests for deferred paths and pass targeted eval tests

---

### TASK-114: Complete Deferred Docs Freshness Gate Recovery
**Priority**: P1 (High)
**Estimate**: 2-4 hours
**Depends On**: TASK-112

Recover TASK-095 artifacts that were missing from committed task-061 history
(docs freshness checker, override policy, and CI/local gate wiring).

**Acceptance Criteria**:
- [x] Add docs freshness checker module and command entrypoint
- [x] Add override policy file with expiry/rationale schema checks
- [x] Wire docs freshness gate into CI and local quality targets
- [x] Add/restore unit tests for conflict detection and override behavior

---

### TASK-115: Finish Partial Recovery for Tracing/Lineage/Grounding
**Priority**: P1 (High)
**Estimate**: 3-6 hours
**Depends On**: TASK-112

Close remaining partials left after TASK-112 for TASK-092, TASK-100, and
TASK-102 (dependency parity, remaining runtime guards, and API exposure parity).

**Acceptance Criteria**:
- [x] Add missing tracing dependency lock/runtime parity and API bootstrap instrumentation
- [x] Complete embedding-lineage safety checks in deduplication/clustering paths and docs
- [x] Expose grounding metadata parity across report/retrospective API response contracts
- [x] Run targeted unit tests for tracing, lineage, grounding, and affected API routes

---

### TASK-116: Backlog Continuity Restoration for TASK-086..TASK-108
**Priority**: P1 (High)
**Estimate**: 1-2 hours
**Depends On**: TASK-112

Restore complete backlog documentation coverage for recovered tasks and reintroduce
missing TASK-108 specification so backlog reflects full historical task record.

**Acceptance Criteria**:
- [x] Restore full task spec entries in `tasks/BACKLOG.md` for `TASK-086` through `TASK-107`
- [x] Restore explicit `TASK-108` task specification with open (not completed) status
- [x] Keep `TASK-108` absent from completed-task records until implementation is done
- [x] Preserve existing task sequencing and update next available task ID

---

### TASK-117: Enforce Task Sequencing Guards End-to-End
**Priority**: P1 (High)
**Estimate**: 3-5 hours
**Depends On**: TASK-110

Add hard workflow enforcement so autonomous/local agents cannot start or advance
task work outside the required sequence.

**Acceptance Criteria**:
- [x] Add a preflight guard that blocks task-branch start unless `main` is clean and synced (`git switch main && git pull --ff-only`)
- [x] Add a single-active-task guard that blocks starting a new task when there is an open, non-merged task PR
- [x] Add a post-merge guard that blocks next task start until local `main` is synced to remote `main`
- [x] Harden PR scope policy to use one canonical metadata field (`Primary-Task: TASK-XXX`) instead of parsing arbitrary PR text
- [x] Update runbook/docs and local hook instructions with the enforced sequencing workflow

---

### TASK-118: Launch Readiness and Guidance Drift Assessment [REQUIRES_HUMAN]
**Priority**: P0 (Critical)
**Estimate**: 2-3 hours

Produce a current-state assessment that reconciles runtime behavior, status docs,
and operating guidance, then capture prioritized remediation tasks with explicit
human sign-off on sequencing and launch gates.

**Acceptance Criteria**:
- [ ] Publish assessment artifact under `tasks/assessments/` with concrete file/line references for each finding
- [ ] Classify findings by relevance and launch impact (`public launch blocker`, `pre-launch high`, `non-blocking`)
- [ ] Define authoritative source-of-truth order for execution/status guidance (code/tests vs sprint/status docs)
- [ ] Capture accepted remediation sequence and dependencies in backlog tasks
- [ ] Obtain explicit human approval for remediation order and launch-go/no-go criteria

---

### TASK-119: Guidance Hierarchy and AGENTS Router Tightening
**Priority**: P1 (High)
**Estimate**: 2-4 hours
**Depends On**: TASK-118

Reduce guidance ambiguity by keeping `AGENTS.md` strictly map-oriented and
making source-of-truth precedence explicit across task/status docs.

**Acceptance Criteria**:
- [x] Add a concise source-of-truth hierarchy section in `AGENTS.md` (execution + status precedence)
- [x] Remove or relocate non-critical procedural prose from `AGENTS.md` into task/runbook docs
- [x] Ensure `AGENTS.md` "Where to look first" ordering is consistent with current workflow
- [x] Add cross-links from `PROJECT_STATUS.md` and `tasks/CURRENT_SPRINT.md` to the hierarchy policy
- [x] Add/update unit-level docs checks if needed to enforce the hierarchy marker presence

---

### TASK-120: Documentation Drift Fixes (ADR References + Data Model Coverage)
**Priority**: P1 (High)
**Estimate**: 3-5 hours
**Depends On**: TASK-118

Resolve high-impact documentation drift that can mislead implementation and
operational decisions.

**Acceptance Criteria**:
- [x] Resolve `ADR-006` mismatch in architecture docs (either add ADR file or update references)
- [x] Expand `docs/DATA_MODEL.md` with implemented schema sections for `reports`, `api_usage`, `trend_outcomes`, and `human_feedback`
- [x] Validate updated docs against SQLAlchemy model reality (`src/storage/models.py`) with explicit line-referenced verification notes
- [x] Keep archived-risk language in `docs/POTENTIAL_ISSUES.md` clearly superseded and non-authoritative
- [x] Run docs freshness gate and ensure no new drift errors are introduced

---

### TASK-121: Docs Freshness Gate Expansion (Integrity + Coverage Rules)
**Priority**: P1 (High)
**Estimate**: 3-5 hours
**Depends On**: TASK-114, TASK-120

Extend the existing docs freshness checker so drift classes identified in the
assessment fail early in CI/local quality paths.

**Acceptance Criteria**:
- [x] Add checker rule for ADR reference integrity (referenced ADR IDs must resolve to existing files)
- [x] Add checker rule for required `DATA_MODEL.md` table coverage for runtime-critical models
- [x] Add checker rule for archived-doc banners and authoritative-pointer presence
- [x] Preserve override/expiry workflow for intentional temporary drift with explicit rationale
- [x] Wire new checks into existing CI/local docs freshness command paths with tests

---

### TASK-122: Launch-Critical Production Guardrails Hardening
**Priority**: P0 (Critical)
**Estimate**: 4-6 hours
**Depends On**: TASK-118

Close immediate launch-risk gaps in auth/secret defaults and readiness
semantics so public deployment fails safe by default.

**Acceptance Criteria**:
- [x] Enforce production-safe secret handling (`SECRET_KEY` must be explicit in production or startup fails)
- [x] Enforce explicit admin-key requirement for key-management endpoints (no permissive fallback)
- [x] Tighten auth default posture for production mode and document safe rollout controls
- [x] Return non-2xx readiness status when dependencies are unavailable
- [x] Add/update unit tests and deployment/environment docs for all guardrail behaviors

---

### TASK-123: Current Sprint File Right-Sizing and Sprint Archive Split
**Priority**: P1 (High)
**Estimate**: 1-2 hours

Reduce execution-context noise by splitting historical sprint detail into
versioned sprint archive files and keeping `tasks/CURRENT_SPRINT.md` focused on
active execution state.

**Acceptance Criteria**:
- [x] Archive current `tasks/CURRENT_SPRINT.md` detailed history into `tasks/sprints/SPRINT_001.md`
- [x] Replace `tasks/CURRENT_SPRINT.md` with a concise active-sprint view (goal, active tasks, immediate done)
- [x] Preserve traceability via explicit links between `CURRENT_SPRINT.md` and archived sprint files
- [x] Update `tasks/COMPLETED.md` with `TASK-123` completion record
- [x] Keep backlog task-ID policy aligned after reserving `TASK-123`

---

### TASK-124: Status Ledger Reconciliation and Active Queue Cleanup
**Priority**: P1 (High)
**Estimate**: 1-2 hours
**Depends On**: TASK-123

Reconcile status/task ledgers so active and completed task views are consistent
with source-of-truth precedence and current sprint execution reality.

**Acceptance Criteria**:
- [x] Align `PROJECT_STATUS.md` in-progress and next-up sections with `tasks/CURRENT_SPRINT.md` and `tasks/COMPLETED.md`
- [x] Remove already completed non-human tasks from active/in-progress status narratives
- [x] Ensure open `[REQUIRES_HUMAN]` launch-readiness task (`TASK-118`) is consistently visible in active/blocked priorities
- [x] Update task ledgers (`tasks/CURRENT_SPRINT.md`, `tasks/COMPLETED.md`, `tasks/BACKLOG.md`) to record `TASK-124` completion and next available task ID

---

### TASK-125: Delivery Lifecycle Clarification and PR Scope Guard Hardening
**Priority**: P1 (High)
**Estimate**: 1-3 hours
**Depends On**: TASK-124

Clarify that autonomous engineering work is complete only after full branch/PR
lifecycle closure, and harden PR scope guard parsing so canonical
`Primary-Task` metadata is recognized for multiline and escaped-newline PR
bodies.

**Acceptance Criteria**:
- [x] Add explicit full-lifecycle completion expectation to canonical task workflow guidance
- [x] Add explicit blocker-handling guidance requiring exact step + manual action reporting
- [x] Harden `scripts/check_pr_task_scope.sh` to normalize escaped newline payloads from PR body contexts
- [x] Add/extend automated tests covering multiline and escaped-newline PR body parsing behavior
- [x] Update task ledgers (`tasks/CURRENT_SPRINT.md`, `tasks/COMPLETED.md`, `tasks/BACKLOG.md`) to record `TASK-125` completion and next available task ID

---

### TASK-126: Taxonomy Drift Guardrails (Runtime Gap Queue + Benchmark Alignment)
**Priority**: P1 (High)
**Estimate**: 4-7 hours
**Depends On**: TASK-066

Prevent silent taxonomy drift from reducing signal quality by making unknown
trend/signal mismatches visible and actionable in runtime, and by enforcing the
same taxonomy source-of-truth in benchmark workflows.

**Acceptance Criteria**:
- [x] Capture non-scoring taxonomy-gap records whenever trend impacts are skipped for unknown `trend_id` or unknown `signal_type`/indicator mapping
- [x] Keep current probability safety behavior: unknown taxonomy impacts never apply trend deltas
- [x] Add observability for taxonomy-gap volume/rate (including top unknown signal keys by trend) suitable for operator review
- [x] Provide an analyst-facing review path (API/CLI/report artifact) for taxonomy-gap triage and resolution tracking
- [x] Update benchmark trend loading to use `config/trends/*.yaml` (`TrendConfig`) instead of hardcoded fixture taxonomy
- [x] Add benchmark/taxonomy preflight that fails fast on dataset taxonomy mismatch (no silent score degradation via implicit zero fill)
- [x] Add/adjust tests for runtime gap capture, benchmark taxonomy loading, and fail-fast mismatch behavior
- [x] Document operator workflow for resolving taxonomy gaps (map to existing indicator, add indicator, or reject as out-of-scope)

---

### TASK-127: Cross-Ledger Drift Reconciliation and Dependency Hygiene
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Resolve recurring inconsistencies across `PROJECT_STATUS.md`,
`tasks/CURRENT_SPRINT.md`, `tasks/COMPLETED.md`, and backlog dependency
metadata so status views remain coherent after rapid task execution.

**Acceptance Criteria**:
- [x] Reconcile any mismatch where tasks are listed as both in-progress and completed (starting with `TASK-113`, `TASK-114`, `TASK-115`)
- [x] Ensure active `[REQUIRES_HUMAN]` tasks in `tasks/CURRENT_SPRINT.md` are represented consistently in `PROJECT_STATUS.md` in-progress/blocked sections (including `TASK-118`)
- [x] Normalize backlog dependency metadata for already-completed tasks that depended on still-open human-gated tasks (audit result 2026-02-18: no remaining completed tasks depend on currently open `[REQUIRES_HUMAN]` tasks)
- [x] Add a lightweight consistency check (script/test/docs-freshness rule) that flags: (a) in-progress+completed dual-listing, and (b) active sprint tasks missing from project-status in-progress list
- [x] Update task ledgers (`tasks/CURRENT_SPRINT.md`, `tasks/COMPLETED.md`, `tasks/BACKLOG.md`) when this task is executed

---

### TASK-128: Corroboration Row-Parsing Runtime Fix
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Restore independence-aware corroboration weighting in runtime by fixing SQLAlchemy
row-shape parsing in pipeline evidence aggregation.

**Acceptance Criteria**:
- [x] Replace tuple-only row filtering in corroboration aggregation with SQLAlchemy `Row`/mapping-safe extraction
- [x] Ensure cluster-aware corroboration path is used when source-cluster fields are present; fallback path is used only when fields are truly absent
- [x] Add unit/integration tests that cover SQLAlchemy `Row` results and verify expected corroboration factors
- [x] Add instrumentation/logging to surface fallback-corroboration usage rate for operator visibility

---

### TASK-129: Atomic Trend Delta Updates Under Concurrency
**Priority**: P0 (Critical)
**Estimate**: 3-5 hours

Prevent lost trend probability updates by making evidence/decay/manual
adjustments atomic and concurrency-safe.

**Acceptance Criteria**:
- [x] Replace read-modify-write update path for `trend.current_log_odds` with a concurrency-safe atomic update strategy
- [x] Preserve deterministic trend-snapshot/audit behavior while applying atomic updates
- [x] Add concurrency-focused tests (parallel workers/updates) proving no dropped deltas under contention
- [x] Document expected locking/serialization behavior for trend updates in architecture or operations docs

---

### TASK-130: Suppression-First Event Lifecycle Guard
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Ensure suppressed/invalidated events are blocked before clustering merge/lifecycle
touches so they cannot be unintentionally reactivated.

**Acceptance Criteria**:
- [x] Move suppression/invalidated checks ahead of clustering merge and event lifecycle mention hooks
- [x] Ensure invalidated/suppressed events are never revived by mention-side effects during processing
- [x] Add tests for invalidated-event, suppressed-event, and normal-event paths across orchestrator + lifecycle interactions
- [x] Preserve explicit audit logs/metrics for skipped suppressed items

---

### TASK-131: Forward-Only GDELT Watermark Semantics
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Align GDELT ingestion checkpoint behavior with forward-progress semantics to avoid
cursor regression and silent coverage gaps.

**Acceptance Criteria**:
- [x] Separate pagination/query cursor movement from persisted ingestion high-water watermark semantics
- [x] Persist forward-only watermark based on max successfully processed publication timestamp/window bound
- [x] Add tests for multi-page windows and partial-page edge cases to ensure watermark monotonicity
- [x] Update ingestion docs to clarify RSS vs GDELT checkpoint rules and failure/retry behavior

---

### TASK-132: Trend-Filtered Events API De-duplication
**Priority**: P2 (Medium)
**Estimate**: 1-3 hours

Prevent duplicate event rows in `GET /events` when `trend_id` filters are used.

**Acceptance Criteria**:
- [x] Update trend-filter query to avoid duplicate `Event` rows (for example via `EXISTS`, `DISTINCT`, or grouping on `events.id`)
- [x] Preserve stable sorting + pagination semantics after query change
- [x] Add API tests covering multi-evidence-per-event scenarios to verify no duplicate rows are returned

---

### TASK-133: Preserve Evidence Lineage on Event Invalidation
**Priority**: P1 (High)
**Estimate**: 3-5 hours

Retain explainability/audit provenance when events are invalidated by feedback,
without leaving stale trend deltas applied.

**Acceptance Criteria**:
- [x] Replace hard deletion of `TrendEvidence` on invalidation with reversible lineage-preserving state/marker
- [x] Keep reversal of previously applied deltas correct and auditable after invalidation
- [x] Expose invalidated-evidence lineage in audit/reporting paths needed for replay/calibration investigations
- [x] Add migration/tests validating invalidate + reverse + audit/replay behavior

---

### TASK-134: External Assessment Backlog Intake Preservation
**Priority**: P1 (High)
**Estimate**: 1-2 hours

Preserve externally sourced backlog improvements in a dedicated task branch/PR so
planning deltas are not lost while other delivery tasks are in flight.

**Acceptance Criteria**:
- [x] Capture relevant assessment-derived planning updates in `tasks/BACKLOG.md` with clear, non-duplicate task boundaries
- [x] Keep explicit mapping to already-open human-gated tasks where overlap exists (no duplicate implementation tasks)
- [x] Preserve and publish backlog-only changes through a dedicated `TASK-134` branch/PR
- [x] Keep task-ID policy synchronized after reserving `TASK-134`

**Overlap mapping note**:
- External assessment intake produced planning tasks `TASK-135`–`TASK-142` only.
- No duplicate implementation tasks were created for already-open human-gated work; manual collector wiring remains tracked under `TASK-080` `[REQUIRES_HUMAN]`.

---

## Phase 9: External Review Feedback (2026-02)

Backlog items derived from external review of trend config quality (baselines,
indicators, weights, falsification criteria). Review assessed all 16 configs and
found ~60% of recommendations actionable. Items below capture the valid subset.

### TASK-135: Clarify baseline_probability referent in trend descriptions
**Priority**: P1 (High)
**Estimate**: 1 hour

Four trend descriptions don't explicitly state what `baseline_probability` measures.
The system mixes event-risk trends, transition trends, and process trends — the
baseline is a decay attractor in log-odds space, but descriptions should make the
conceptual referent clear for operators.

**Files**: `config/trends/fertility-decline-acceleration.yaml`,
`config/trends/ukraine-security-frontier-model.yaml`,
`config/trends/south-america-agri-supply-shift.yaml`,
`config/trends/elite-mass-polarization.yaml`

**Acceptance Criteria**:
- [x] Each of the 4 descriptions includes a standardized sentence: "Baseline probability represents the probability that [specific measurable outcome] [by time horizon / over rolling N-year window]."
- [x] `elite-mass-polarization` reframed from state description to delta/acceleration framing
- [x] All 4 configs pass Pydantic validation
- [x] No baseline probability values changed (numbers are correct)

---

### TASK-136: Add ai_safety_incident indicator to ai-control trend
**Priority**: P2 (Medium)
**Estimate**: 30 minutes

A major AI safety incident (autonomous vehicle fatality cluster, model jailbreak
enabling mass harm, AI-generated CSAM wave) is a strong escalatory signal for the
ai-control trend that is currently not captured by any indicator.

**Files**: `config/trends/ai-human-control-expansion.yaml`

**Acceptance Criteria**:
- [x] New indicator `ai_safety_incident` added: weight 0.04, escalatory, leading
- [x] Keywords: `["AI safety incident", "autonomous vehicle fatality", "model jailbreak", "AI-generated CSAM", "algorithmic harm", "AI system failure"]`
- [x] Config passes Pydantic validation
- [x] Gold set taxonomy validation still passes (`--tier1-trend-mode subset`)

---

### TASK-137: Sharpen vague falsification criteria
**Priority**: P2 (Medium)
**Estimate**: 30 minutes

Two trends have `would_invalidate_model` criteria that are too vague to
operationalize. Replace with measurable thresholds.

**Files**: `config/trends/elite-mass-polarization.yaml`,
`config/trends/fertility-decline-acceleration.yaml`

**Acceptance Criteria**:
- [x] `elite-mass-polarization` criterion replaced: "Fundamental constitutional restructuring that removes structural conditions" → "Top-decile wealth share declines 5+ percentage points across 3+ major economies for 3+ consecutive years"
- [x] `fertility-decline` criterion replaced: "Structural demographic measurement discontinuity" → "Major revision to TFR methodology by 3+ national statistics agencies rendering cross-country time-series incomparable"
- [x] Both configs pass Pydantic validation

---

### TASK-138: Improve keyword specificity for 3 vague indicators
**Priority**: P3 (Low)
**Estimate**: 30 minutes

Three indicators have keywords that are too generic for reliable classification:
`governance_capture_signals`, `mainstream_positive_framing`, `institutional_trust_collapse`.

**Files**: `config/trends/elite-mass-polarization.yaml`,
`config/trends/normative-deviance-normalization.yaml`,
`config/trends/parallel-enclaves-europe.yaml`

**Acceptance Criteria**:
- [x] `governance_capture_signals`: add keywords like "lobbying spending record", "corporate political donations", "PAC expenditure", "regulatory revolving door appointment"
- [x] `mainstream_positive_framing`: add keywords like "broadsheet editorial", "network news segment", "podcast mainstream", "prime-time documentary"
- [x] `institutional_trust_collapse`: add keywords like "Eurobarometer trust", "Gallup institutional confidence", "trust in government survey", "democratic satisfaction index"
- [x] All 3 configs pass Pydantic validation

---

### TASK-139: Embedding Input Truncation Telemetry and Guardrails
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Make embedding input length handling explicit and observable so operators can
measure when article text is truncated/chunked and verify impact on quality/cost.

**Acceptance Criteria**:
- [x] Add deterministic pre-embedding token counting for each embedding input and enforce a configurable max-input policy (`truncate` or `chunk`)
- [x] Emit structured logs whenever input is cut, including item/event id, original token count, retained token count, and strategy used
- [x] Add metrics/counters for total embedding inputs, truncated inputs, truncation ratio, and optionally dropped tail tokens
- [x] Persist per-item metadata needed for auditability (e.g., `embedding_input_tokens`, `embedding_was_truncated`, `embedding_truncation_strategy`) or equivalent reproducible evidence
- [x] Add tests covering under-limit, exact-limit, and over-limit paths with both policy modes
- [x] Document operational query/check commands to review truncation rates weekly and set alert thresholds

---

### TASK-140: In-Branch Backlog Capture Rule and Guard
**Priority**: P2 (Medium)
**Estimate**: 1-2 hours

Reduce task-tracking drift by enforcing a consistent workflow when new backlog
tasks are discovered during active implementation.

**Acceptance Criteria**:
- [x] Update `AGENTS.md` workflow guidance to explicitly require that newly discovered backlog tasks relevant to the active task are added/committed in the same task branch/PR (as a separate docs commit if needed)
- [x] Define explicit exception criteria for when backlog edits must be split to a separate branch (unrelated scope, already-merged task, or urgent blocker)
- [x] Add a lightweight guard/checklist item in task completion docs or scripts to verify backlog updates were either included in-branch or explicitly split with rationale
- [x] Add unit/script test coverage if automation/scripts are changed (not applicable: no script automation changes in this task)

---

### TASK-141: Production HTTPS Termination and Secure Ingress
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Ensure deployed API traffic is encrypted end-to-end at the edge and that
plaintext HTTP is not exposed publicly by default.

**Acceptance Criteria**:
- [x] Add a production ingress path (reverse proxy) that terminates TLS for Horadus API traffic
- [x] Document certificate provisioning/renewal workflow (managed certs or ACME automation) with failure fallback steps
- [x] Enforce HTTPS-only external access (redirect HTTP to HTTPS or disable external plain-HTTP exposure)
- [x] Add/verify security response headers at the edge (`Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options` or equivalent policy)
- [x] Update deployment runbook with validation commands proving HTTPS is active and HTTP exposure is closed

---

### TASK-142: Production Network Exposure Hardening
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Reduce attack surface by restricting service exposure and tightening access
paths for admin operations.

**Acceptance Criteria**:
- [x] Remove or gate direct public host-port exposure of internal services in production defaults (API, DB, Redis)
- [x] Define and document network boundary policy (public ingress -> proxy only, app/data services on private network)
- [x] Add operator guidance for host/network allowlisting and firewall controls for admin/API access
- [x] Add deployment verification checks to confirm only intended ports are reachable from outside the host
- [x] Update deployment/security docs with explicit "public vs private" port mapping expectations

---

## Phase 10: Runtime Concurrency + Data Integrity Hardening (2026-02)

Backlog items derived from internal review of runtime concurrency correctness,
event lifecycle accounting, and schema-level invariants.

### TASK-144: Runtime review findings backlog intake preservation
**Priority**: P1 (High)
**Estimate**: 30-60 minutes

Capture review-identified hardening items in `tasks/BACKLOG.md` with clear task
boundaries so they can be executed as one-task-per-branch follow-ups.

**Acceptance Criteria**:
- [x] Add dedicated tasks for the identified runtime issues (concurrency safety, event lifecycle accounting, schema invariants, retention, docs drift)
- [x] Avoid duplicating already-open tasks (e.g., Telegram wiring remains `TASK-080` `[REQUIRES_HUMAN]`)
- [x] Keep Task ID policy synchronized after reserving IDs

---

### TASK-145: Concurrency-safe trend log-odds updates (atomic delta apply)
**Priority**: P1 (High)
**Estimate**: 3-5 hours

`TrendEngine.apply_evidence` currently updates `Trend.current_log_odds` by
reading the value into memory and writing back `current + delta`. Under
concurrent workers this can lose updates (last write wins).

**Files**: `src/core/trend_engine.py`, `src/storage/models.py`, `tests/`

**Acceptance Criteria**:
- [x] Apply evidence delta with an atomic SQL update (`current_log_odds = current_log_odds + :delta`) or equivalent row-locking transaction
- [x] Preserve idempotency guarantees for `(trend_id, event_id, signal_type)` evidence inserts (no double-apply)
- [x] Return correct `previous_probability` and `new_probability` even under concurrency
- [x] Add a concurrency-focused test that would fail under the current read-modify-write implementation (lost update) and passes after the fix
- [x] Add structured logging for evidence apply showing whether the update path used atomic update / row lock (operator-debuggable)

---

### TASK-146: Fix event unique-source counting and lifecycle ordering on merge
**Priority**: P1 (High)
**Estimate**: 1-2 hours

`EventClusterer._merge_into_event` updates `unique_source_count` and lifecycle
before inserting the `EventItem` link for the merged item, so the just-added
source may be undercounted and lifecycle confirmation delayed.

**Files**: `src/processing/event_clusterer.py`, `src/processing/event_lifecycle.py`, `tests/`

**Acceptance Criteria**:
- [ ] Ensure the merged item is linked (`event_items`) before recomputing `unique_source_count`
- [ ] Ensure lifecycle transitions (emerging → confirmed) observe the updated `unique_source_count`
- [ ] Add a unit/integration test showing the confirmation threshold is reached on the correct mention (no off-by-one merge)
- [ ] Keep behavior correct for the “no embedding” path where events are created without similarity matching

---

### TASK-147: Enforce RawItem belongs-to-one-Event invariant at the DB layer
**Priority**: P1 (High)
**Estimate**: 2-4 hours

The schema currently allows a `RawItem` to be linked to multiple `Event`s
because `event_items` only has a composite PK `(event_id, item_id)` and no
uniqueness on `item_id`. Concurrent clustering can attach one item to multiple
events despite the invariant “belongs to exactly one event.”

**Files**: `src/storage/models.py`, `alembic/`, `src/processing/event_clusterer.py`, `tests/`

**Acceptance Criteria**:
- [ ] Add a DB-level uniqueness constraint/index enforcing one-to-one mapping: `event_items.item_id` is unique
- [ ] Add an Alembic migration that applies the constraint safely (including a defensive preflight/query for existing duplicates)
- [ ] Update clustering/linking code to treat a uniqueness violation as “already linked” and return the existing `event_id` deterministically
- [ ] Add test coverage for the uniqueness invariant (attempting to link the same item to a second event fails and is handled cleanly)

---

### TASK-148: Align event `canonical_summary` semantics with `primary_item_id`
**Priority**: P2 (Medium)
**Estimate**: 2-4 hours

Today `canonical_summary` is overwritten by the newest item on every merge,
even when `primary_item_id` points to a more credible item. This makes “primary”
designation misleading and can degrade summary quality.

**Files**: `src/processing/event_clusterer.py`, `src/storage/models.py`, `docs/DATA_MODEL.md`, `tests/`

**Acceptance Criteria**:
- [ ] Define and document canonical summary semantics (e.g., “summary of primary item” vs “latest mention summary”)
- [ ] Implement the chosen semantics (update summary only when `primary_item_id` changes, or add a separate `latest_summary` field)
- [ ] Add tests that cover both “newest mention” and “higher-credibility primary” update cases
- [ ] Update `docs/DATA_MODEL.md` so operators understand what `canonical_summary` represents

---

### TASK-149: Add retention/archival policy for raw_items, events, and trend_evidence
**Priority**: P2 (Medium)
**Estimate**: 3-6 hours

Only `trend_snapshots` has explicit Timescale retention policies. The rest of the
high-churn tables (`raw_items`, `events`, `event_items`, `trend_evidence`) have
no retention/cleanup path, risking unbounded growth in continuous ingestion.

**Files**: `src/workers/celery_app.py`, `src/workers/tasks.py`, `src/storage/models.py`, `alembic/`, `docs/DEPLOYMENT.md`, `tests/`

**Acceptance Criteria**:
- [ ] Define a safe retention policy (defaults + config knobs) that preserves auditability where required (e.g., keep evidence longer than raw text)
- [ ] Add a scheduled cleanup worker task with dry-run/logging mode and metrics (deleted rows, bytes/age buckets if feasible)
- [ ] Ensure cleanup respects foreign keys and event lifecycle (e.g., only prune `raw_items` for `noise/error` or for events in `archived` status beyond a threshold)
- [ ] Add tests for retention selection logic (what is eligible vs protected)
- [ ] Document operator workflow: how to tune retention, verify it ran, and validate DB size trends

---

### TASK-150: Close `docs/DATA_MODEL.md` drift vs runtime schema (sources/raw_items/events)
**Priority**: P2 (Medium)
**Estimate**: 1-2 hours

`docs/DATA_MODEL.md` omits several runtime columns and has at least one stale
type/length definition (e.g., `raw_items.external_id`).

**Files**: `docs/DATA_MODEL.md`, `src/storage/models.py`

**Acceptance Criteria**:
- [ ] Update `sources` table docs to include `source_tier`, `reporting_type`, `error_count`, `last_error`
- [ ] Update `raw_items` table docs to include `author` and correct `external_id` length (runtime is `String(2048)`)
- [ ] Update `events` table docs to include `unique_source_count`, `lifecycle_status`, `last_mention_at`, `confirmed_at`, contradiction fields, and any other runtime columns
- [ ] Ensure ERD is either updated to include key runtime entities or explicitly labeled as “core tables only” to avoid misleading reviewers

---

### TASK-151: Version trend definition changes for auditability
**Priority**: P3 (Low)
**Estimate**: 3-6 hours

Trend definitions are stored as a single JSON blob (`trends.definition`) without
history. If trend configs can change outside Git-managed YAML, operators lack an
audit trail for “what changed” beyond probability snapshots.

**Files**: `src/storage/models.py`, `alembic/`, `src/api/routes/trends.py`, `docs/`

**Acceptance Criteria**:
- [ ] Add a minimal append-only trend-definition version table (trend id, timestamp, definition payload, actor/context)
- [ ] Ensure API/config sync paths record a version row on material change (with deterministic diff or hash)
- [ ] Add a read endpoint or admin query guidance for inspecting definition history
- [ ] Add tests for “no-op update does not create a new version” and “material change creates a version”

---

## Phase 11: Operator Safety + Output Fidelity Hardening (2026-02)

Backlog items derived from review of highest-risk operator foot-guns, Tier-2
evidence capture correctness, async throughput hazards, and analytics-quality
constraints for categorical dimensions.

### TASK-152: Highest-risk review backlog intake preservation
**Priority**: P1 (High)
**Estimate**: 30-60 minutes

Capture review-identified hardening items in `tasks/BACKLOG.md` with clear task
boundaries so they can be executed as one-task-per-branch follow-ups.

**Acceptance Criteria**:
- [x] Add dedicated tasks for the identified issues (integration DB safety, Tier-2 multi-impact alignment, async semantic cache, categorical constraints, evidence factorization, language-aware contradiction heuristics, cost pricing config, URL normalization policy)
- [x] Avoid duplicating already-open tasks (e.g., corroboration undercount already tracked in `TASK-146`)
- [x] Keep Task ID policy synchronized after reserving IDs

---

### TASK-153: Guard integration-test DB truncation (operator safety)
**Priority**: P1 (Critical)
**Estimate**: 1-2 hours

Integration tests currently truncate all `public` tables for whatever
`DATABASE_URL` points at. This is a serious foot-gun if a developer/operator
misconfigures `DATABASE_URL` (staging/prod wipe risk).

**Files**: `tests/integration/conftest.py`, `src/core/config.py`, `tests/`

**Acceptance Criteria**:
- [ ] Add a hard fail/guard so truncation can only run against an explicitly marked test database (opt-in env var and/or DB name suffix like `_test`)
- [ ] Add a “local-only” guard (e.g., require host is localhost/127.0.0.1 unless explicit override) to reduce remote wipe risk
- [ ] Make the failure mode loud and actionable (clear error message showing the resolved DB target)
- [ ] Add unit/integration tests covering guard behavior (refuse unsafe targets, allow safe test targets)

---

### TASK-154: Allow multiple Tier-2 impacts per trend per event (trend_id + signal_type)
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Tier-2 output validation currently rejects duplicate `trend_id` entries even if
the `signal_type` differs. The DB schema and evidence recording allow multiple
signals per `(trend_id, event_id)` (unique is `(trend_id, event_id, signal_type)`).

**Files**: `src/processing/tier2_classifier.py`, `ai/prompts/tier2_classify.md`, `tests/`

**Acceptance Criteria**:
- [ ] Update Tier-2 output validation to allow repeated `trend_id` when `signal_type` differs
- [ ] Enforce uniqueness of `(trend_id, signal_type)` pairs within one Tier-2 response to prevent true duplicates
- [ ] Update prompt guidance if needed so Tier-2 can emit multiple impacts for one trend/event
- [ ] Add tests demonstrating one event can produce multiple impacts for the same trend with different signal types

---

### TASK-155: Make semantic cache non-blocking in async pipeline paths
**Priority**: P2 (Medium)
**Estimate**: 2-4 hours

The Redis-backed semantic cache uses the synchronous `redis` client and is
invoked from async Tier-1/Tier-2 classification code paths, which can block the
event loop when enabled.

**Files**: `src/processing/semantic_cache.py`, `src/processing/tier1_classifier.py`, `src/processing/tier2_classifier.py`, `tests/`

**Acceptance Criteria**:
- [ ] Use an async Redis client (`redis.asyncio`) or run sync Redis calls in a threadpool so async code paths do not block
- [ ] Preserve current cache key semantics and eviction behavior
- [ ] Add tests (or a micro-benchmark-style unit test) validating cache calls are awaitable/non-blocking when enabled
- [ ] Ensure cache remains default-disabled and safe to enable with predictable latency

---

### TASK-156: Constrain categorical “dimension” fields to prevent drift (DB-level)
**Priority**: P2 (Medium)
**Estimate**: 3-6 hours

Several categorical fields are stored as plain strings (e.g., `sources.source_tier`,
`sources.reporting_type`, `events.lifecycle_status`). Over time this can create
dirty dimensions and invalidate analytics/metrics.

**Files**: `src/storage/models.py`, `alembic/`, `src/api/`, `tests/`

**Acceptance Criteria**:
- [ ] Enforce allowed values at the DB layer (Postgres enums or CHECK constraints) for source tier/reporting type and event lifecycle status
- [ ] Add a migration that validates/backfills existing rows to legal values (or fails fast with a diagnostic query if invalids exist)
- [ ] Preserve API schemas and behavior (requests/filters continue to work)
- [ ] Add tests covering constraint enforcement and common query/filter behavior

---

### TASK-157: Persist full evidence factorization inputs for long-horizon auditability
**Priority**: P2 (Medium)
**Estimate**: 3-6 hours

`TrendEvidence` stores many factor fields but does not persist the indicator/base
weight and explicit direction (or multiplier) used at scoring time. If trend YAML
changes later, audits/replays cannot fully reconstruct the factorization inputs.

**Files**: `src/storage/models.py`, `alembic/`, `src/processing/pipeline_orchestrator.py`, `src/core/trend_engine.py`, `docs/DATA_MODEL.md`, `tests/`

**Acceptance Criteria**:
- [ ] Persist `base_weight` (indicator weight) and `direction` (or `direction_multiplier`) on `trend_evidence` rows
- [ ] Optionally persist a stable config reference (e.g., trend definition hash/version) used at scoring time for reproducibility
- [ ] Backfill behavior is defined for existing rows (nullable fields or deterministic backfill strategy)
- [ ] Update docs so operators understand which evidence fields are “scoring-time” vs “derived later”
- [ ] Add tests verifying evidence rows retain enough info to reconstruct delta inputs even after config changes

---

### TASK-158: Make claim-graph contradiction heuristics language-aware (en/uk/ru)
**Priority**: P2 (Medium)
**Estimate**: 2-5 hours

Claim-graph contradiction heuristics (stopwords/polarity markers) are currently
English-centric, but the system supports `en`, `uk`, and `ru`. This can create
misleading contradiction links and downstream corroboration penalties.

**Files**: `src/processing/tier2_classifier.py`, `ai/prompts/tier2_classify.md`, `docs/ARCHITECTURE.md`, `tests/`

**Acceptance Criteria**:
- [ ] Define a language policy for claims used in contradiction detection (e.g., force claims to English, or implement per-language stopwords/polarity markers)
- [ ] Ensure contradiction link creation is either accurate per language or safely disabled outside supported heuristics
- [ ] Add tests demonstrating correct/expected behavior for at least one non-English example (uk/ru)
- [ ] Document the policy and its limitations for operators

---

### TASK-159: Externalize token pricing to config and model/version mapping
**Priority**: P2 (Medium)
**Estimate**: 2-4 hours

LLM token pricing is currently hard-coded in code and tier-based. Provider
pricing and model versions drift; cost/budget estimates should be configurable
and mapped to (provider, model).

**Files**: `src/processing/cost_tracker.py`, `src/core/config.py`, `docs/ENVIRONMENT.md`, `tests/`

**Acceptance Criteria**:
- [ ] Move pricing table to configuration (env/YAML) with safe defaults
- [ ] Support per-model/per-provider rates, not just per tier
- [ ] Add validation and tests for pricing config parsing and cost calculation
- [ ] Keep budget enforcement behavior deterministic and fail-closed on invalid pricing config

---

### TASK-160: Improve URL normalization to avoid false-duplicate matches
**Priority**: P2 (Medium)
**Estimate**: 2-4 hours

Dedup URL normalization currently drops all query parameters. Some sites encode
content identity in query strings, so this can cause false duplicates.

**Files**: `src/processing/deduplication_service.py`, `src/core/config.py`, `docs/ARCHITECTURE.md`, `tests/`

**Acceptance Criteria**:
- [ ] Preserve content-identifying query parameters while stripping known tracking params (e.g., `utm_*`, `fbclid`, etc.)
- [ ] Ensure normalization is deterministic (e.g., stable sorting of remaining query params)
- [ ] Add tests covering URLs where query params must be preserved and where tracking params should be removed
- [ ] Document the normalization policy and provide an operator override knob for strictness if needed

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
