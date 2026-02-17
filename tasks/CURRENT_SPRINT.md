# Current Sprint

**Sprint Goal**: Execute Phase 8 hardening and close remaining governance gaps  
**Sprint Number**: 1  
**Sprint Dates**: 2026-02-02 to 2026-02-16

---

## Active Tasks

- `TASK-044` Curated Human-Verified Gold Dataset `[REQUIRES_HUMAN]` — Awaiting manual data curation/review
- `TASK-066` Expand Trend Catalog to Multi-Trend Baseline `[REQUIRES_HUMAN]` — Awaiting manual trend authoring/reviewer sign-off
- `TASK-070` Trend Baseline Prior Review and Sign-Off `[REQUIRES_HUMAN]` — Awaiting manual analyst baseline validation
- `TASK-077` Cost-First Pipeline Ordering `[REQUIRES_HUMAN]` — Awaiting manual human execution/approval
- `TASK-080` Telegram Collector Task Wiring `[REQUIRES_HUMAN]` — Awaiting manual human execution/approval
- `TASK-084` Production Security Default Guardrails `[REQUIRES_HUMAN]` — Awaiting manual human execution/approval
- `TASK-085` Require Explicit Admin Key for Key Management `[REQUIRES_HUMAN]` — Awaiting manual human execution/approval
- `TASK-115` Finish Partial Recovery for Tracing/Lineage/Grounding — Ready for implementation
- `TASK-117` Enforce Task Sequencing Guards End-to-End — Ready for implementation

---

## Completed This Sprint

### TASK-114: Complete Deferred Docs Freshness Gate Recovery
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Recovered docs-freshness quality gate artifacts and wired them into local/CI
quality workflows with override policy and unit coverage.

**Completed**:
- [x] Added docs freshness checker module and CLI entrypoint script
- [x] Added override policy file with schema/expiry expectations
- [x] Wired docs freshness gate into CI and Makefile quality targets
- [x] Added unit tests for conflict detection and override behavior

---

### TASK-113: Complete Deferred Eval Mode and Vector Revalidation Recovery
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Completed deferred recovery gaps for benchmark execution modes and vector
revalidation artifacts from partial `task-061` lineage.

**Completed**:
- [x] Added benchmark runtime support for `dispatch_mode` and `request_priority`
- [x] Restored vector revalidation runbook + summary persistence artifact support
- [x] Aligned eval docs/examples with implemented runtime behavior
- [x] Added/updated eval unit tests and passed targeted suites

---

### TASK-108: Working Tree Hygiene Audit and Disposition Plan
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Completed full working-tree hygiene audit and disposition plan, then isolated
non-task work into deferred stash for task-scoped extraction.

**Completed**:
- [x] Produced grouped inventory and root-cause analysis (`tasks/assessments/TASK-108-working-tree-hygiene.md`)
- [x] Assigned per-group disposition (`defer`, `drop`, `archive`) with risk flags and cleanup order
- [x] Removed local generated eval artifacts from repo working tree and archived copies under `/tmp/horadus-task108-eval-results`
- [x] Added guardrail ignore for local eval result JSON artifacts (`ai/eval/results/*.json`)

---

### TASK-116: Backlog Continuity Restoration for TASK-086..TASK-108
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Restored full backlog task specs for recovered phase-8 tasks and reintroduced
missing TASK-108 as an open, not-yet-completed item.

**Completed**:
- [x] Restored explicit backlog descriptions for `TASK-086`..`TASK-107`
- [x] Reintroduced `TASK-108` with full scope and open acceptance criteria
- [x] Preserved completion tracking in `tasks/COMPLETED.md` without marking `TASK-108` done
- [x] Updated next available task ID after reserving `TASK-116`

---

### TASK-112: Recover Stranded TASK-086..TASK-107 from `task-061`
**Status**: DONE ✓  
**Priority**: P0 (Critical)  
**Spec**: `tasks/BACKLOG.md`

Recovered committed task-061 backlog work onto `main` lineage, reconstructed
missing required modules/migrations, and documented unresolved recovery gaps as
explicit follow-up tasks.

**Completed**:
- [x] Produced deterministic per-task recovery matrix (`tasks/assessments/TASK-112-recovery-matrix.md`)
- [x] Applied recoverable committed code/docs/tests from `origin/codex/task-061-recency-decay`
- [x] Reconstructed missing adapter/tracing/lineage/grounding artifacts required for runnable recovered paths
- [x] Added deferred follow-up tasks for artifacts not fully recoverable from committed history (`TASK-113`, `TASK-114`, `TASK-115`)
- [x] Ran targeted changed-area validation (186 unit tests passing)

---

### TASK-111: Main Branch Merge-Completeness Audit
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Audited backlog completion against `main` merge reality using branch/PR ancestry
signals and produced a deterministic missing-work report.

**Completed**:
- [x] Audited remote task branches against `origin/main` and PR merge status
- [x] Verified open PR queue for `main` is empty
- [x] Confirmed no completed tasks are missing merged functionality on `main`
- [x] Identified two stale superseded branches (closed-not-merged originals for TASK-039 and TASK-054)
- [x] Published findings and cleanup recommendations in `tasks/assessments/TASK-111-main-merge-audit.md`

---

### TASK-110: Task Delivery Workflow Guardrails and Enforcement
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Implemented hard delivery guardrails spanning docs, CI, local hooks, and
repository protection defaults to prevent multi-task branch drift.

**Completed**:
- [x] Documented mandatory task start/finish workflow (`main` sync, task branch, PR+green, merge/delete, `main` resync)
- [x] Clarified unrelated-work handling to create follow-up task without auto-switching branches unless blocked/urgent
- [x] Added PR CI guard for task scope (`TASK-XXX` required and single-task constraint)
- [x] Added local pre-commit/pre-push branch-name guard and hook installation updates
- [x] Applied/enforced main-branch protection defaults (PR required, checks required, admins enforced, direct push blocked, linear history)

---

### TASK-109: Enforce Branch-Per-Task Delivery Policy
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Added explicit branch-per-task governance so implementation stays isolated per
task and PR scope.

**Completed**:
- [x] Added hard branch-per-task rule to `AGENTS.md`
- [x] Added matching task branching policy to `tasks/BACKLOG.md`
- [x] Required single-task branch scope and one PR per task branch
- [x] Required merge-only after green checks and post-merge branch deletion
- [x] Required new task + new branch for unrelated mid-task follow-up work

---

### TASK-069: Baseline Source-of-Truth Unification for Decay
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Unify decay baseline behavior around canonical DB baseline log-odds and keep definition metadata synchronized.

**Completed**:
- [x] Updated trend decay logic to use `Trend.baseline_log_odds` as the canonical baseline source
- [x] Synchronized `definition.baseline_probability` on create/update/config-sync trend mutation paths
- [x] Added one-time Alembic backfill migration to align existing `definition.baseline_probability` values with stored baseline log-odds
- [x] Added unit tests for stale/missing definition baseline metadata to confirm decay targets DB baseline
- [x] Updated data-model docs to clarify canonical baseline field and synchronized metadata behavior

---

### TASK-083: Documentation and OpenAPI Drift Cleanup
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Refresh stale architecture/ops docs and API bootstrap OpenAPI wording.

**Completed**:
- [x] Updated architecture flow docs to match current implemented processing order
- [x] Archived stale `docs/POTENTIAL_ISSUES.md` snapshot with explicit superseded-status banner
- [x] Fixed stale API auth/OpenAPI description wording in FastAPI bootstrap
- [x] Added concrete "Last Verified" timestamps in operational docs (`DEPLOYMENT`, `ENVIRONMENT`, `RELEASING`)

---

### TASK-082: Vector Index Profile Parity (Model vs Migration)
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Align ORM metadata with migration-managed IVFFlat vector index profile.

**Completed**:
- [x] Updated model metadata for `idx_raw_items_embedding` and `idx_events_embedding` to `lists=64`
- [x] Added metadata assertions for IVFFlat profile values in unit tests
- [x] Kept docs aligned with `lists=64` index profile references

---

### TASK-081: Readiness Probe HTTP Semantics Fix
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Return non-2xx readiness status when dependencies are unavailable.

**Completed**:
- [x] Updated `/health/ready` to return HTTP 503 with stable payload on failure
- [x] Kept success path HTTP 200 payload unchanged
- [x] Preserved structured warning logging on readiness failures
- [x] Added unit tests for readiness success/failure status-code semantics

---

### TASK-079: Periodic Pending Processing Schedule
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Add periodic beat scheduling for pending-item processing.

**Completed**:
- [x] Added beat schedule entry for `workers.process_pending_items`
- [x] Gated schedule by `ENABLE_PROCESSING_PIPELINE`
- [x] Added configurable cadence setting `PROCESS_PENDING_INTERVAL_MINUTES`
- [x] Added/updated unit tests for schedule composition and enable/disable behavior
- [x] Updated environment docs/template with new scheduling setting

---

### TASK-078: Tier-1 Batch Classification in Orchestrator
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Use Tier-1 batch classification path in orchestrator flow.

**Completed**:
- [x] Refactored pipeline orchestration to prepare items, run batched Tier-1 classification, then finalize Tier-2 path
- [x] Preserved deterministic item/result mapping and original output ordering
- [x] Added batch-failure fallback to per-item Tier-1 classification for partial-failure isolation
- [x] Preserved budget-exceeded handling semantics (`pending` with retry path)
- [x] Added unit coverage for batched mapping/order and partial-failure fallback behavior

---

### TASK-076: Trend Taxonomy Contract and Gold-Set Validation Gate
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/076-trend-taxonomy-validation-gate.md`

Add deterministic taxonomy-validation tooling to prevent trend-config/eval-dataset drift.

**Completed**:
- [x] Added `horadus eval validate-taxonomy` command for trend YAML + gold-set compatibility checks
- [x] Validated trend YAML loading through `TrendConfig`, with duplicate/missing trend-id detection
- [x] Added Tier-1 trend key contract modes (`strict` and documented `subset` compatibility mode)
- [x] Added Tier-2 trend-id validation and configurable signal-type mismatch handling (`strict`/`warn`)
- [x] Added unit coverage for pass path and required failure modes (duplicate/missing IDs, unknown trend ID, key mismatch, unknown signal type)
- [x] Wired taxonomy validation into local/CI eval quality path and documented strict vs transitional usage

---

### TASK-075: Container Secret Provisioning and Rotation Runbook
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/specs/075-container-secret-provisioning-rotation.md`

Standardize production secret handling for Docker deployments using mounted files and `*_FILE` variables.

**Completed**:
- [x] Added operator runbook for container secret provisioning with host-side layout, ownership, and permission checklist
- [x] Documented concrete Docker Compose mount + `*_FILE` mapping pattern for `api`, `worker`, and `beat`
- [x] Added secret rotation workflow (pre-flight validation, atomic symlink switch, controlled service recreation)
- [x] Added rollback workflow with known-good release restoration and post-rollback verification checklist
- [x] Updated deployment and environment docs to discourage plaintext production `.env` secrets and cross-link to the runbook

---

### TASK-074: Enforce Strict Alembic Check Gate by Default
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Enable strict autogenerate parity validation in default local and CI quality gates.

**Completed**:
- [x] Set strict mode (`MIGRATION_GATE_VALIDATE_AUTOGEN=true`) in CI integration workflow
- [x] Set strict mode by default in local integration path (`make test-integration`)
- [x] Kept explicit emergency bypass path (`MIGRATION_GATE_VALIDATE_AUTOGEN=false`) in script/Make targets
- [x] Updated release/deployment/environment docs with strict-gate expectations and bypass policy
- [x] Verified strict migration gate command paths pass with current baseline

---

### TASK-073: Alembic Autogenerate Baseline Drift Cleanup
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Resolve model/schema parity diffs so `alembic check` can be enforced fail-closed.

**Completed**:
- [x] Reproduced and documented baseline `alembic check` drift (API usage defaults + index metadata mismatches)
- [x] Aligned SQLAlchemy metadata with migration baseline for `api_usage` server defaults
- [x] Added model metadata for migration-managed pgvector indexes (`idx_raw_items_embedding`, `idx_events_embedding`)
- [x] Excluded TimescaleDB-managed index (`trend_snapshots_timestamp_idx`) from autogenerate comparisons
- [x] Added unit regression tests for drift-sensitive model metadata defaults/indexes
- [x] Validated `alembic check` passes after `alembic upgrade head`

---

### TASK-072: Runtime Migration Parity Health Signal
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Expose runtime schema parity in health/startup paths to prevent long-lived migration drift.

**Completed**:
- [x] Added migration parity utility service (`src/core/migration_parity.py`) comparing `alembic_version` to Alembic head
- [x] Added migration parity component to `/health` payload (`checks.migrations`)
- [x] Added strict startup behavior (`MIGRATION_PARITY_STRICT_STARTUP`) to fail boot when parity is unhealthy
- [x] Added optional runtime toggle (`MIGRATION_PARITY_CHECK_ENABLED`) for controlled rollout/testing
- [x] Added unit coverage for healthy/drifted parity states and strict startup failure behavior
- [x] Updated environment/deployment docs for runtime parity controls

---

### TASK-071: Migration Drift Quality Gates
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Add enforceable migration parity gates so schema drift fails fast in local/CI workflows.

**Completed**:
- [x] Added migration drift gate script (`scripts/check_migration_drift.sh`) that validates current revision == head
- [x] Added optional strict autogenerate parity mode (`MIGRATION_GATE_VALIDATE_AUTOGEN=true`) for `alembic check`
- [x] Added `make db-migration-gate` target for explicit operator/developer migration gating
- [x] Wired migration gate into local integration workflow (`make test-integration`)
- [x] Wired migration gate into CI integration workflow before integration tests
- [x] Updated release/deployment docs with migration gate usage

---

### TASK-058: Vector Retrieval Quality Tuning (HNSW vs IVFFlat)
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/BACKLOG.md`

Tune vector retrieval strategy selection for current small-table operating regime.

**Completed**:
- [x] Added deterministic vector retrieval benchmark harness (`horadus eval vector-benchmark`) comparing exact, IVFFlat, and HNSW
- [x] Added strategy recommendation logic using recall and latency gates (`recall_at_k >= 0.95` and >=5% latency improvement over exact)
- [x] Confirmed benchmark recommendation for current dataset profile selects IVFFlat as default ANN strategy
- [x] Added Alembic migration `0008_vector_index_strategy_profile` to apply tuned IVFFlat profile (`lists=64`) with downgrade path to legacy profile
- [x] Added vector similarity helper utilities and nearest-neighbor threshold tests for deterministic thresholded behavior
- [x] Updated data-model documentation with selected strategy and benchmark revalidation command

---

### TASK-059: Active-Learning Human Review Queue
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Prioritize analyst review with deterministic expected-information-gain ranking.

**Completed**:
- [x] Added `GET /api/v1/review-queue` endpoint for ranked analyst candidates
- [x] Implemented ranking formula `uncertainty_score x projected_delta x contradiction_risk`
- [x] Added triage payload fields for reviewer context and label-provenance follow-up (`feedback_count`, `feedback_actions`, `requires_human_verification`)
- [x] Added filters for `trend_id`, `days`, and `unreviewed_only` to support queue slicing
- [x] Added unit tests for deterministic ranking order and filter behavior

---

### TASK-065: Independence-Aware Corroboration and Claim Graph
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/BACKLOG.md`

Reduce false confidence from derivative coverage by introducing claim-graph structure and independent-source corroboration scoring.

**Completed**:
- [x] Added normalized claim representation on events via `extracted_claims.claim_graph` (`nodes` + `support`/`contradict` links)
- [x] Reworked pipeline corroboration scoring to use independent source clusters instead of raw source counts
- [x] Added derivative-coverage penalties through reporting-type weighting in corroboration scoring
- [x] Added contradiction-aware corroboration penalties driven by claim-graph contradiction links
- [x] Extended unit coverage for derivative overcount prevention and contradiction-aware corroboration behavior
- [x] Updated data-model documentation for claim graph and effective corroboration formula semantics

---

### TASK-064: Historical Replay and Champion/Challenger Harness
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/BACKLOG.md`

Add a deterministic replay workflow for side-by-side release decisions on historical windows.

**Completed**:
- [x] Added historical replay runner (`horadus eval replay`) over shared time-window inputs with optional trend scoping
- [x] Added champion/challenger policy profiles and side-by-side comparison artifact generation (`replay-*.json`)
- [x] Included replay dataset counts for historical `raw_items`, `events`, `trend_evidence`, `trend_snapshots`, and `trend_outcomes`
- [x] Added quality/cost/latency comparison outputs and automated promotion assessment gates
- [x] Documented champion/challenger promotion criteria in `docs/PROMPT_EVAL_POLICY.md`
- [x] Added unit coverage for replay metrics, promotion assessment, artifact writing, and CLI replay command parsing

---

### TASK-063: Source Reliability Diagnostics (Read-Only)
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/BACKLOG.md`

Add source and source-tier reliability visibility to calibration reporting without automatic weighting changes.

**Completed**:
- [x] Added `source_reliability` and `source_tier_reliability` diagnostics to calibration dashboard service and API response payloads
- [x] Implemented read-only advisory diagnostics derived from resolved outcomes and linked source evidence (no automatic source-weight mutations)
- [x] Added sample-size confidence gating (`insufficient`/`low`/`medium`/`high`) and explicit sparse-sample advisory notes
- [x] Added unit tests for reliability aggregation correctness and sparse-data guardrail behavior
- [x] Updated API documentation to describe new advisory diagnostics fields and confidence gating

---

### TASK-062: Hermetic Integration Test Environment Parity
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Align local and CI integration environments to eliminate config drift and silent failures.

**Completed**:
- [x] Switched CI integration Postgres to the same repo Docker image (`docker/postgres/Dockerfile`) used locally, guaranteeing `timescaledb` and `vector` extension availability
- [x] Added explicit CI extension verification to fail fast when required database capabilities are missing
- [x] Unified integration DB/Redis URLs via shared CI env variables and mirrored local defaults in `Makefile` (`INTEGRATION_DATABASE_URL`, `INTEGRATION_REDIS_URL`)
- [x] Removed split migration/test execution pattern in CI by running migrations and integration tests in a single strict shell step (`set -euo pipefail`)
- [x] Added deterministic integration DB setup/teardown fixture (`tests/integration/conftest.py`) that truncates public tables before and after each integration test

---

### TASK-061: Recency-Aware Novelty + Per-Indicator Decay
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Improve evidence weighting realism using continuous novelty and indicator-specific temporal decay.

**Completed**:
- [x] Replaced binary novelty with continuous recency-aware novelty scoring derived from latest prior evidence timestamp
- [x] Added optional per-indicator `decay_half_life_days` support in trend config schema and pipeline weighting
- [x] Extended evidence factor provenance with temporal fields (`evidence_age_days`, `temporal_decay_multiplier`) and persisted them to `trend_evidence`
- [x] Added Alembic migration `0007_evidence_decay_fields` for new `trend_evidence` provenance columns
- [x] Added unit coverage for recency novelty behavior, indicator decay weighting, and persisted provenance fields

---

### TASK-060: Counterfactual Simulation API
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/BACKLOG.md`

Provide non-persistent what-if probability projections using deterministic trend math.

**Completed**:
- [x] Added `POST /api/v1/trends/{trend_id}/simulate` with mode `remove_event_impact` (reverse historical event deltas without DB mutation)
- [x] Added mode `inject_hypothetical_signal` using deterministic `calculate_evidence_delta` factor math
- [x] Returned projected probability, probability delta, log-odds delta, and factor breakdown for both modes
- [x] Added unit tests for both simulation modes and explicit side-effect-free behavior (no session mutation calls)

---

### TASK-047: Pinned Evaluation Baseline Artifact
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Create and maintain a committed benchmark baseline artifact for prompt/model comparisons.

**Completed**:
- [x] Updated benchmark execution to tolerate per-item Tier-1/Tier-2 output alignment `ValueError`s and record failures in metrics instead of aborting full runs
- [x] Added benchmark unit coverage for Tier-1 and Tier-2 per-item failure handling paths
- [x] Generated benchmark artifact from current accepted configuration (`baseline`) and pinned it at `ai/eval/baselines/current.json`
- [x] Confirmed pinned artifact includes run context metadata (`generated_at`, model config, `dataset_scope`, `queue_threshold`, dataset fingerprints)
- [x] Confirmed baseline process docs remain aligned with committed path and promotion procedure

---

### TASK-057: Runtime Resilience Guardrails
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Strengthen runtime safety for production operations and health visibility.

**Completed**:
- [x] Added CPU/memory resource limits and reservations for `api`, `worker`, `beat`, `postgres`, and `redis` in `docker-compose.prod.yml`
- [x] Added worker activity heartbeat publishing in worker task entrypoints and exposed worker heartbeat health in `/health`
- [x] Added Timescale retention/compression Alembic migration for `trend_snapshots` (`0006_snapshot_retention`)
- [x] Added configurable DB pool timeout (`DATABASE_POOL_TIMEOUT_SECONDS`) and wired it into SQLAlchemy engine creation
- [x] Added unit coverage for health worker component, worker heartbeat wrappers, and DB pool-timeout engine configuration

---

### TASK-054: LLM Input Safety Guardrails (Injection + Token Precheck)
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Harden Tier1/Tier2 input handling against malicious prompt content and context-window overruns.

**Completed**:
- [x] Added explicit untrusted-content delimiters in Tier1/Tier2 payloads (`UNTRUSTED_ARTICLE_CONTENT`, `UNTRUSTED_EVENT_CONTEXT`)
- [x] Added token-estimation safety helpers and deterministic truncation markers (`[TRUNCATED]`)
- [x] Added Tier1 pre-call token budget checks with automatic batch splitting for oversized payloads
- [x] Added Tier2 payload budget enforcement with context-chunk reduction before LLM calls
- [x] Added unit tests covering adversarial instruction-like content and token-budget truncation behavior
- [x] Updated Tier1/Tier2 prompt contracts to explicitly ignore instruction-like strings inside untrusted content blocks

---

### TASK-053: Atomic Budget Enforcement Under Concurrency
**Status**: DONE ✓  
**Priority**: P1 (Critical)  
**Spec**: `tasks/BACKLOG.md`

Eliminate race windows between budget checks and usage recording across concurrent workers.

**Completed**:
- [x] Reworked `CostTracker.record_usage` to enforce check+record atomically in one transactional path with row locking
- [x] Prevented call/cost counter overshoot under concurrent execution by validating projected totals before write
- [x] Added structured denial logging and Prometheus metric (`llm_budget_denials_total`) for budget enforcement denials
- [x] Added concurrency integration tests for call-limit and cost-limit overshoot scenarios

---

### TASK-052: Distributed Rate Limiting + Admin Audit Trail
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Move API key rate limiting out of process memory and add traceability for privileged auth operations.

**Completed**:
- [x] Added Redis-backed per-key rate limiting with TTL window buckets shared across API instances
- [x] Preserved deterministic `Retry-After` behavior using window-end calculations
- [x] Added structured audit logging for admin key-management actions (`list/create/revoke/rotate`) including denied/not-found outcomes
- [x] Added tests for distributed multi-manager consistency and rate-limit edge behavior near window boundaries

---

### TASK-068: Gold-Set Change Governance and Baseline Supersession
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Define and implement process controls for baseline handling when gold-set content/labels change.

**Completed**:
- [x] Added backlog governance task for dataset-version supersession policy
- [x] Added benchmark dataset fingerprint metadata (`gold_set_fingerprint_sha256`, `gold_set_item_ids_sha256`, `dataset_scope`)
- [x] Added test coverage for dataset metadata in benchmark output
- [x] Updated prompt-eval policy with explicit supersession and baseline-history archival rules
- [x] Updated eval/baseline docs with operational checklist for dataset-version transitions

---

### TASK-051: API Key Hash Hardening and Migration
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Harden API key hash storage/verification and support legacy migration on successful auth.

**Completed**:
- [x] Replaced plain SHA-256 hashes with salted memory-hard `scrypt` hashes (`scrypt-v1`)
- [x] Added explicit `hash_version` metadata to persisted key records
- [x] Switched key verification to constant-time compare via `secrets.compare_digest`
- [x] Added backward-compatible legacy SHA-256 verification and on-auth migration to `scrypt-v1`
- [x] Added unit tests for legacy compatibility + migration behavior

---

### TASK-067: Report Narrative Prompt Hardening
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/BACKLOG.md`

Harden weekly/monthly/retrospective narrative prompts and deterministic fallback behavior.

**Completed**:
- [x] Expanded report/retrospective prompt contracts with audience, uncertainty, contradiction, and anti-injection guidance
- [x] Added explicit guardrails to avoid unsupported entities/events outside provided structured payloads
- [x] Improved deterministic fallback narratives to include confidence cues tied to evidence/coverage
- [x] Added unit tests for fallback narrative confidence/output-shape behavior

---

### TASK-056: Bounded Embedding Cache
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/BACKLOG.md`

Replace unbounded embedding cache behavior with bounded LRU semantics.

**Completed**:
- [x] Replaced in-memory embedding cache with LRU behavior (`OrderedDict` + recency touch on reads)
- [x] Added configurable `EMBEDDING_CACHE_MAX_SIZE` setting with default `2048`
- [x] Preserved cache-hit behavior and embedding output correctness paths
- [x] Added unit test coverage for LRU eviction and cache hit/miss accounting

---

### TASK-055: Stuck Processing Reaper Worker
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Recover items stranded in `processing` after worker crashes/abnormal exits.

**Completed**:
- [x] Added `processing_started_at` tracking on `raw_items` with Alembic migration `0005_add_processing_started_at`
- [x] Added `workers.reap_stale_processing_items` task to reset stale processing rows back to `pending`
- [x] Added stale timeout/interval settings (`PROCESSING_STALE_TIMEOUT_MINUTES`, `PROCESSING_REAPER_INTERVAL_MINUTES`)
- [x] Added structured logs + Prometheus counter for reset counts and affected item IDs
- [x] Added unit tests covering reset and no-op reaper scenarios plus schedule/route wiring

### TASK-050: Upgrade Tier 2 LLM Defaults to gpt-4.1-mini
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/BACKLOG.md`

Upgrade Tier-2/reporting defaults and cost constants to the 2026-02 reviewed model configuration.

**Completed**:
- [x] Updated `LLM_TIER2_MODEL`, `LLM_REPORT_MODEL`, and `LLM_RETROSPECTIVE_MODEL` defaults to `gpt-4.1-mini`
- [x] Updated Tier-2 cost constants in cost tracker to `$0.40/$1.60` per 1M tokens
- [x] Added `gpt-4.1-mini` pricing in classifier model-price maps
- [x] Updated `.env.example` with Tier-2 DeepSeek failover recommendation comments
- [x] Added `2026-02 Review` decision update to `docs/adr/002-llm-provider.md`

---

### TASK-049: Documentation Drift and Consistency Cleanup
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/BACKLOG.md`

Reconcile docs with repository reality and add explicit freshness process.

**Completed**:
- [x] Corrected project path naming in `README.md` (`horadus` vs legacy path)
- [x] Added missing cross-links for release and evaluation policy docs
- [x] Removed stale reference to absent `docker-compose.prod.secrets.yml` from status tracking
- [x] Added lightweight documentation freshness process (owner + update timing)

---

### TASK-048: CI Gate Hardening for Integration and Security
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Enforce integration and security checks as fail-closed CI gates.

**Completed**:
- [x] Removed migration fallback that masked integration environment failures
- [x] Removed integration test fallback that masked test job failures
- [x] Removed Bandit fallback that masked security findings
- [x] Kept lockfile, lint, typecheck, and unit jobs intact
- [x] Documented CI gate failure remediation path in release runbook

---

### TASK-046: Release Process Runbook
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Add formal release/versioning/tagging/rollback governance.

**Completed**:
- [x] Added `docs/RELEASING.md` with pre-release, tagging, rollout, verification, and rollback checklists
- [x] Documented semantic version tagging and release-note policy
- [x] Included quality gates (tests/lint/mypy/migrations/eval policy checks)
- [x] Linked release runbook from README and deployment documentation

---

### TASK-045: Gold-Set Quality Audit Tooling
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Add automated audit checks for evaluation dataset quality before benchmark runs.

**Completed**:
- [x] Added `horadus eval audit` command for provenance/diversity/coverage quality analysis
- [x] Added timestamped audit artifacts under `ai/eval/results/audit-*.json`
- [x] Added warning rules for missing `human_verified` labels and duplicated content patterns
- [x] Added `--fail-on-warnings` mode for gate-style non-zero exits
- [x] Added unit tests for both warning-heavy and pass-quality audit datasets
- [x] Added `make audit-eval` operational command and updated eval docs

---

### TASK-043: Eval Threshold Alignment + Label Provenance
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Align benchmark routing metrics with runtime threshold settings and add label provenance support.

**Completed**:
- [x] Replaced hardcoded queue cutoff with `TIER1_RELEVANCE_THRESHOLD` in benchmark queue-accuracy scoring
- [x] Added `label_verification` support to gold-set row parsing and benchmark output metadata
- [x] Added `--require-human-verified` CLI flag to evaluate only human-reviewed labels
- [x] Added benchmark output fields for `queue_threshold`, `require_human_verified`, and label provenance counts
- [x] Added unit tests for human-only filtering and threshold-aware benchmark metadata

---

### TASK-042: CI uv Toolchain Alignment
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Align CI workflows with the repo-wide uv-only package/tooling policy.

**Completed**:
- [x] Migrated GitHub Actions jobs from legacy installer flows to `uv sync --frozen`
- [x] Switched lint/typecheck/test/integration commands to `uv run --no-sync`
- [x] Switched build/package checks to `uvx` (`build`, `twine`)
- [x] Removed residual legacy-installer references from CI workflow definitions
- [x] Kept CI security checks and lockfile validation in place under uv workflow

---

### TASK-041: Model Evaluation Gold Set
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `tasks/BACKLOG.md`

Add a reusable gold-set benchmark workflow for Tier-1/Tier-2 model comparison.

**Completed**:
- [x] Added `ai/eval/gold_set.jsonl` with 200 labeled benchmark items
- [x] Added benchmark runner (`horadus eval benchmark`) with timestamped JSON outputs under `ai/eval/results/`
- [x] Added default model-pair comparison configs (`baseline` vs `alternative`)
- [x] Added benchmark metrics for relevance/route accuracy, extraction accuracy, and estimated cost-per-item
- [x] Added unit tests for gold-set parsing and benchmark output generation
- [x] Updated evaluation docs and Make target (`make benchmark-eval`) for operator workflow

---

### TASK-040: LLM Provider Fallback
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `tasks/BACKLOG.md`

Add primary/secondary failover routing for Tier 1 and Tier 2 LLM calls.

**Completed**:
- [x] Added optional secondary provider/model settings for Tier 1 and Tier 2 failover
- [x] Added failover routing helper for retryable errors (429/5xx/timeouts)
- [x] Added structured failover switch logging (reason + provider/model route)
- [x] Preserved strict JSON schema validation across failover route execution
- [x] Added unit tests covering retryable failover and non-retryable behavior
- [x] Updated `.env.example` and environment docs with failover configuration controls

---

### TASK-039: Calibration Ops Runbook Tightening
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `PROJECT_STATUS.md` (Next Up)

Add a practical operator runbook for handling calibration alerts.

**Completed**:
- [x] Added calibration operations runbook with alert triage playbook (`docs/CALIBRATION_RUNBOOK.md`)
- [x] Added weekly calibration review checklist for ongoing alert hygiene
- [x] Added remediation decision tree for coverage and drift escalation paths
- [x] Linked calibration runbook from deployment and API docs

---

### TASK-038: Drift Alert Delivery Channels
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `PROJECT_STATUS.md` (Next Up)

Add webhook delivery channel support for calibration drift alerts.

**Completed**:
- [x] Added optional webhook sink for calibration drift/coverage alert payload delivery
- [x] Added retry/backoff behavior for transient webhook errors (429/5xx/network)
- [x] Added bounded webhook failure logging to avoid alert fanout noise
- [x] Added environment controls for webhook URL, timeout, retries, and backoff
- [x] Wired dashboard drift alert emission to notifier delivery path
- [x] Added unit tests for webhook success, transient retry, and permanent failure scenarios

---

### TASK-037: Calibration Coverage Guardrails
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `PROJECT_STATUS.md` (Next Up)

Add calibration coverage SLO metrics and low-sample guardrails to dashboard reporting.

**Completed**:
- [x] Added coverage metrics for resolved outcomes by trend in calibration dashboard output
- [x] Added low-sample coverage alerts when trends fall below configured thresholds
- [x] Added configurable coverage guardrail settings for minimum resolved count and ratio
- [x] Extended calibration reports API response schema with coverage summary fields
- [x] Added unit tests for coverage summary, low-sample alerts, API response, and dashboard export
- [x] Updated environment/API docs and `.env.example` for new calibration coverage controls

---

### TASK-027 Follow-up: Backup Verification & Retention Enforcement
**Status**: DONE ✓  
**Priority**: P1 (High)  
**Spec**: `PROJECT_STATUS.md` (Next Up)

Harden backup operations with automated verification and retention policies.

**Completed**:
- [x] Added backup verification script (`scripts/verify_backups.sh`) for freshness/integrity checks
- [x] Added retention enforcement in backup script (`BACKUP_RETENTION_DAYS`, `BACKUP_RETENTION_COUNT`)
- [x] Added checksum generation and size/integrity verification for created backups
- [x] Added `make verify-backups` operational target
- [x] Updated deployment/environment docs and `.env.example` backup controls

---

### TASK-027 Follow-up: Cloud Secret Backend References
**Status**: DONE ✓  
**Priority**: P2 (Medium)  
**Spec**: `PROJECT_STATUS.md` (Next Up)

Document managed secret-store integration patterns for production environments.

**Completed**:
- [x] Added managed secret backend reference guide (`docs/SECRETS_BACKENDS.md`)
- [x] Added backend mapping guidance for AWS/GCP/Azure/Vault using Horadus `*_FILE` settings
- [x] Linked guide from deployment and environment docs
- [x] Added README references for secret backend integration docs

---

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
