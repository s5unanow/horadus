# Project Status

**Last Updated**: 2026-02-12
**Current Phase**: Phase 6 - Calibration (complete)

## Progress Overview

```
Phase 0: Setup & Foundation  [████████████████████] 100%  ✅ COMPLETE
Phase 1: Data Ingestion      [████████████████████] 100%  ✅ COMPLETE
Phase 2: Processing Layer    [████████████████████] 100%  ✅ COMPLETE
Phase 3: Trend Engine        [████████████████████] 100%  ✅ COMPLETE
Phase 4: Reporting           [████████████████████] 100%  ✅ COMPLETE
Phase 5: Polish & Deploy     [████████████████████] 100%  ✅ COMPLETE
Phase 6: Calibration (NEW)   [████████████████████] 100%  ✅ COMPLETE
```

## What's Working

- [x] Project structure created (src/, tests/, docs/, config/)
- [x] Documentation framework (ARCHITECTURE, DATA_MODEL, GLOSSARY)
- [x] Task tracking system (BACKLOG, CURRENT_SPRINT, specs)
- [x] pyproject.toml with all dependencies
- [x] docker-compose.yml (PostgreSQL + TimescaleDB + Redis)
- [x] Database models (all entities including expert recommendations)
- [x] Alembic configuration
- [x] Initial Alembic migration created (schema + extensions + hypertable)
- [x] FastAPI skeleton with route stubs
- [x] Core config module (Pydantic Settings)
- [x] Trend engine core (log-odds math, evidence calculation)
- [x] EU-Russia trend config with enhanced schema
- [x] Makefile for common workflows
- [x] RSS collector foundation (config load, fetch/parse, extraction, dedup, persistence)
- [x] RSS integration test path (no external network calls)
- [x] GDELT client foundation (querying, filters, mapping, pagination, dedup, persistence)
- [x] GDELT integration test path (no external network calls)
- [x] Source management API CRUD endpoints with unit tests
- [x] Celery worker app with beat scheduling + ingestion task routing
- [x] RSS/GDELT periodic Celery tasks with retry/backoff + dead-letter capture
- [x] Telegram harvester baseline (collect, backfill, stream polling, media fallback)
- [x] Telegram integration test path (no external network calls)
- [x] Embedding service baseline (OpenAI wrapper, strict validation, batching, cache)
- [x] `raw_items.embedding` pgvector column + ivfflat index migration (`0002`)
- [x] Embedding unit test coverage (batching/cache/validation/persistence)
- [x] Deduplication service baseline (URL/hash/external-id + optional embedding similarity)
- [x] Ingestion collectors wired to shared deduplication service
- [x] Event clusterer baseline (time-window similarity create/merge)
- [x] Event metadata updates on merge (source counts, summary, primary source)
- [x] Tier 1 classifier baseline (batch scoring + strict JSON validation)
- [x] Tier 1 routing updates (`noise` vs Tier 2-ready `processing`) and usage metrics
- [x] Tier 2 classifier baseline (structured extraction + per-trend impacts)
- [x] Tier 2 strict output validation (including trend id safeguards) and usage metrics
- [x] Processing pipeline orchestrator (dedup → embed → cluster → tier1 → tier2)
- [x] Celery processing task auto-triggered by new ingested items
- [x] Pipeline run metrics and end-to-end integration coverage
- [x] Trend management API CRUD endpoints (`/api/v1/trends`)
- [x] Trend YAML sync/load path for `config/trends/*.yaml`
- [x] Trend API unit coverage for CRUD + config sync
- [x] Pipeline-to-trend orchestration for applying Tier 2 trend impacts
- [x] Trend evidence persistence wired through idempotent trend engine updates
- [x] Pipeline metrics now include trend impacts seen and trend updates applied
- [x] End-to-end tests covering trend impact application in processing pipeline
- [x] Trend evidence API endpoint (`GET /api/v1/trends/{id}/evidence`)
- [x] Evidence date-range querying (`start_at`, `end_at`) with validation
- [x] Trend evidence API unit tests for retrieval and filtering behavior
- [x] Trend snapshot worker task + beat schedule wiring (`workers.snapshot_trends`)
- [x] Trend history API endpoint (`GET /api/v1/trends/{id}/history`)
- [x] History date-range filters with interval downsampling (hourly/daily/weekly)
- [x] Unit tests for snapshot scheduling and history API responses
- [x] Trend decay worker task (`workers.apply_trend_decay`) wired into Celery
- [x] Daily decay schedule to fade stale evidence toward baseline
- [x] Decay worker metrics/logging and unit test coverage
- [x] Weekly report generation service for active trends with top-event attribution
- [x] Weekly report worker task + schedule wiring (`workers.generate_weekly_reports`)
- [x] Report API endpoints (`GET /api/v1/reports`, `/api/v1/reports/{id}`, `/api/v1/reports/latest/weekly`)
- [x] Weekly reporting prompt template and report API unit test coverage
- [x] Monthly report generation service with monthly deltas + prior-week rollups
- [x] Category/source breakdown aggregation for monthly intelligence summaries
- [x] Monthly report worker task + schedule wiring (`workers.generate_monthly_reports`)
- [x] Monthly report API endpoint (`GET /api/v1/reports/latest/monthly`)
- [x] Retrospective analysis service with pivotal-event and predictive-signal ranking
- [x] Retrospective API endpoint (`GET /api/v1/trends/{id}/retrospective`)
- [x] Retrospective narrative generation via LLM with deterministic fallback
- [x] OpenAPI docs metadata refreshed with richer tags and descriptions
- [x] API key auth scheme documented in OpenAPI (`X-API-Key`, forward-compatible)
- [x] Request/response examples added for core API models
- [x] API reference guide with endpoint examples (`docs/API.md`)
- [x] API key auth middleware with opt-in enforcement and key validation
- [x] Per-key request throttling (`429` + `Retry-After`) for API traffic
- [x] API key management endpoints (`/api/v1/auth/keys`) for list/create/revoke
- [x] Auth/rate-limit unit test coverage for middleware and key manager
- [x] Structured logging bootstrap with JSON/console output modes
- [x] Prometheus metrics endpoint (`GET /metrics`)
- [x] Observability counters for ingestion throughput, worker errors, and LLM usage
- [x] Worker instrumentation for collector and pipeline metrics
- [x] Production API container image definition (`docker/api/Dockerfile`)
- [x] Production worker/beat container image definition (`docker/worker/Dockerfile`)
- [x] Production deployment stack (`docker-compose.prod.yml`)
- [x] Deployment runbook and environment variable reference docs
- [x] Calibration service for trend outcomes and Brier scoring (`src/core/calibration.py`)
- [x] Trend outcome recording endpoint (`POST /api/v1/trends/{id}/outcomes`)
- [x] Trend calibration report endpoint (`GET /api/v1/trends/{id}/calibration`)
- [x] Calibration bucket analysis over historical predictions
- [x] Risk level mapping and confidence rating for trend presentation
- [x] Probability bands derived from evidence volume/recency/corroboration
- [x] Trend responses now include top movers for the last 7 days
- [x] Trend config schema validation for disqualifiers and falsification criteria
- [x] Indicator type validation (`leading`/`lagging`) in YAML config sync
- [x] Event lifecycle transition manager (emerging/confirmed/fading/archived)
- [x] Hourly lifecycle decay worker task (`workers.check_event_lifecycles`)
- [x] Events API now supports lifecycle filtering and event detail retrieval
- [x] Source tier/reporting multipliers applied to effective source credibility
- [x] Daily LLM budget enforcement (tier1/tier2/embedding) with usage persistence
- [x] Budget-safe pipeline behavior keeps items pending when limits are exceeded
- [x] Budget visibility endpoint (`GET /api/v1/budget`)
- [x] Contradiction detection metadata persisted on events (`has_contradictions`, `contradiction_notes`)
- [x] Events API contradiction filter (`GET /api/v1/events?contradicted=true`)
- [x] Human feedback API endpoints for events/trends (`/api/v1/events/{id}/feedback`, `/api/v1/trends/{id}/override`)
- [x] Feedback audit endpoint (`GET /api/v1/feedback`)
- [x] Event invalidation support that reverts trend contributions
- [x] Processing suppression for events marked as noise/invalidated
- [x] Calibration dashboard endpoint (`GET /api/v1/reports/calibration`)
- [x] Cross-trend reliability statements ("When we said X%, it happened Y%")
- [x] Brier score timeline series for drift visibility
- [x] `horadus trends status` CLI for quick movement checks
- [x] File-based secret loading via `*_FILE` settings for production runtimes
- [x] Explicit SQL logging safety toggle (`SQL_ECHO=false` default)
- [x] Production backup/restore scripts and `make backup-db` / `make restore-db` operations
- [x] Deployment runbook coverage for TLS proxying and backup drills
- [x] API key metadata persistence support (`API_KEYS_PERSIST_PATH`)
- [x] API key rotation endpoint (`POST /api/v1/auth/keys/{id}/rotate`)
- [x] Weekly/monthly report contradiction-resolution analytics (`contradiction_analytics`)
- [x] Calibration drift alerts with thresholded notifications (`drift_alerts`)
- [x] Calibration coverage guardrails and low-sample alerts (`coverage`)
- [x] Calibration drift webhook delivery channel with retry/backoff controls
- [x] Calibration operations runbook (triage playbook, checklist, decision tree)
- [x] Tier-1/Tier-2 LLM provider failover (429/5xx/timeout) with secondary model routing
- [x] Tier-1/Tier-2 gold-set benchmark workflow with 200-item evaluation dataset (`ai/eval/gold_set.jsonl`)
- [x] Benchmark queue-accuracy now uses runtime Tier-1 threshold + label provenance metadata
- [x] Gold-set audit workflow (`horadus eval audit`) with provenance/diversity warning gates
- [x] CI workflow aligned to uv-only dependency/tool execution (no pip install paths)
- [x] Release governance runbook (`docs/RELEASING.md`) with versioning/tagging/rollback workflow
- [x] CI integration/security gates now fail-closed (no permissive masking fallbacks)
- [x] Docs consistency cleanup for repo naming, cross-links, and freshness process
- [x] Tier-2/reporting defaults upgraded to `gpt-4.1-mini` with updated cost constants
- [x] API key storage hardened to salted memory-hard `scrypt-v1` hashes with legacy migration path
- [x] Stale processing reaper worker with timed recovery and observability metrics
- [x] Bounded embedding cache with configurable LRU eviction (`EMBEDDING_CACHE_MAX_SIZE`)
- [x] Hardened weekly/monthly/retrospective narrative prompts with anti-injection and uncertainty guardrails
- [x] Gold-set update governance policy with baseline supersession + history archival workflow
- [x] Benchmark artifacts now include dataset fingerprint metadata for comparison integrity
- [x] Benchmark runs now record per-item Tier-1/Tier-2 alignment failures without aborting entire evaluation runs
- [x] Pinned benchmark baseline artifact committed at `ai/eval/baselines/current.json`
- [x] Distributed Redis-backed API rate limiting with deterministic Retry-After semantics
- [x] Structured admin auth audit logs for key-management operations (list/create/revoke/rotate)
- [x] Atomic budget check-and-record enforcement under concurrency with denial telemetry (`llm_budget_denials_total`)
- [x] Tier1/Tier2 input safety guardrails (untrusted-content delimiters + token prechecks + safe truncation markers)
- [x] Runtime resilience guardrails (worker heartbeat health, Timescale retention/compression policy, DB pool timeout, production resource limits)
- [x] Static calibration dashboard export + hosting path (`horadus dashboard export`)
- [x] Managed cloud secret backend references (`docs/SECRETS_BACKENDS.md`)
- [x] Backup verification automation + retention enforcement (`make verify-backups`)
- [x] Counterfactual simulation API (`POST /api/v1/trends/{id}/simulate`) for side-effect-free remove/inject what-if projections
- [x] Recency-aware novelty scoring + per-indicator temporal decay with explicit trend-evidence provenance factors
- [x] Hermetic integration parity: CI now uses repo Postgres image with verified `timescaledb` + `vector`, unified integration URLs, and deterministic integration DB setup/teardown fixtures
- [x] Advisory source/source-tier reliability diagnostics in calibration dashboard output with sparse-sample confidence gating (read-only)
- [x] Historical replay champion/challenger harness with quality/cost/latency comparison artifacts and documented promotion gates
- [x] Independence-aware corroboration using claim-graph support/contradiction links and source-cluster-weighted corroboration scoring

## In Progress

- `TASK-044` Curated Human-Verified Gold Dataset `[REQUIRES_HUMAN]` (manual labeling/review pending)
- `TASK-066` Expand Trend Catalog to Multi-Trend Baseline `[REQUIRES_HUMAN]` (manual trend definition/review pending)

## Blocked

- `TASK-044` requires manual human curation/review before benchmark can be treated as true gold-set quality.
- `TASK-066` requires human-authored trend definitions and reviewer sign-off before completion.

## Next Up (Priority Order)

1. Complete `TASK-059` active-learning human review queue (autonomous)
2. Complete `TASK-058` vector retrieval quality tuning (autonomous)
3. Complete `TASK-044` human curation and reviewer sign-off for a true gold set
4. Complete `TASK-066` multi-trend baseline expansion with reviewer sign-off

## Expert Feedback Integration ✅

Based on expert review, added 9 new tasks:

| Task | Description | Priority |
|------|-------------|----------|
| TASK-028 | Risk levels + probability bands | P1 |
| TASK-029 | Enhanced trend definitions | P2 |
| TASK-030 | Event lifecycle tracking | P1 |
| TASK-031 | Source tier and reporting type | P2 |
| TASK-032 | Trend outcomes for calibration | P1 |
| TASK-033 | Contradiction detection | P2 |
| TASK-034 | Human feedback API | P2 |
| TASK-035 | Calibration dashboard | P2 |
| TASK-036 | Cost protection & budget limits | P1 |

### Key Additions
- **Risk levels**: Low / Guarded / Elevated / High / Severe
- **Event lifecycle**: emerging → confirmed → fading → archived
- **Source tiers**: primary / wire / major / regional / aggregator
- **Calibration**: Brier scores, outcome tracking
- **Cost protection**: Kill switch for API spend
- **Trend config**: disqualifiers, falsification criteria

## Milestones

| Milestone | Target Date | Status |
|-----------|-------------|--------|
| M1: Basic API + DB running | Week 1 | ✅ Complete |
| M2: RSS ingestion working | Week 2 | ✅ Complete |
| M3: GDELT integration | Week 3 | ✅ Complete |
| M3.5: Telegram integration | Week 3 | ✅ Complete |
| M4: LLM classification pipeline | Week 4 | ✅ Complete |
| M5: Trend engine operational | Week 5 | ✅ Complete |
| M6: Weekly reports generating | Week 6 | ✅ Complete |
| M7: Reporting APIs operational | Week 7 | ✅ Complete |
| M8: Full system operational | Week 8 | 🔲 Not Started |

## Known Issues

- None currently blocking autonomous engineering tasks.

## Architecture Validated ✅

Expert confirmed core design:
- ✅ Events as core unit (not articles)
- ✅ Log-odds for probability tracking
- ✅ LLM extracts signals; code computes deltas
- ✅ Two-tier LLM processing (Tier 1 → Tier 2)
- ✅ Evidence ledger with full provenance

## Recent Decisions

- Project bootstrapped with agent-friendly structure
- Using log-odds for probability tracking (ADR-003)
- Two-tier LLM processing (Tier 1 → Tier 2) (ADR-005)
- Risk levels instead of single probability numbers (expert feedback)
- Event lifecycle to reduce noise (expert feedback)
- Calibration infrastructure for long-term accuracy (expert feedback)

## Technical Debt

- None yet (fresh project)

## Notes

- MVP path: Ingest → Cluster → Score → Report (Phases 0-4)
- Calibration meaningful after 2+ months of data
- Knowledge graph deferred (PostgreSQL sufficient for MVP)
- Remember to update this file when completing milestones
