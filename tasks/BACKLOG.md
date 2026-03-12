# Backlog

Open task definitions only. Completed task history lives in `tasks/COMPLETED.md`, and detailed historical planning ledgers live under `archive/`.

---

## Task ID Policy

- Task IDs are global and never reused.
- Completed IDs are reserved permanently and tracked in `tasks/COMPLETED.md`.
- Next available task IDs start at `TASK-307`.
- Checklist boxes in this file are planning snapshots; canonical completion status lives in `tasks/CURRENT_SPRINT.md` and `tasks/COMPLETED.md`.

## Task Labels

- `[REQUIRES_HUMAN]`: task includes a mandatory manual step and must not be auto-completed by an agent.
- For `[REQUIRES_HUMAN]` tasks, agents may prepare instructions/checklists only and must stop for human completion.

## Task Spec Contract

- New implementation specs should state: problem statement, inputs, outputs, non-goals, and acceptance criteria.
- Canonical lightweight spec template: `tasks/specs/TEMPLATE.md`
- Use the template as a default shape, then keep individual specs only as detailed as the task complexity requires.

## Task Branching Policy (Hard Rule)

- Treat `AGENTS.md` as the canonical workflow-policy owner; keep this ledger focused on open task definitions.
- Every implementation task must run on a dedicated task branch created from `main`, with one `TASK-XXX` per branch/PR.
- Start task work with the canonical guarded flow:
  - `uv run --no-sync horadus tasks preflight`
  - `uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name`
- `make task-preflight`, `make task-start`, and `make agent-safe-start` remain compatibility wrappers only.
- Every task PR body must include exactly one canonical metadata line: `Primary-Task: TASK-XXX`.
- Do not claim a task is complete, done, or finished until `uv run --no-sync horadus tasks lifecycle TASK-XXX --strict` passes or `horadus tasks finish TASK-XXX` completes successfully.
- Keep backlog entries concise and task-shaped; detailed implementation boundaries, migration strategy, risks, and validation belong in the exec plan when one exists.

---

## Open Task Ledger

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

### TASK-189: Restrict `/health` and `/metrics` exposure outside development [REQUIRES_HUMAN]
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Reduce unauthenticated reconnaissance risk by restricting detailed health and
metrics endpoints outside development environments, while preserving a minimal
unauthenticated liveness endpoint.

**Assessment-Ref**:
- `artifacts/assessments/security/daily/2026-03-02.md` (`FINDING-2026-03-02-security-public-health-metrics`)

**Exec Plan**: Required (`tasks/exec_plans/README.md`)
**Files**: `src/api/middleware/auth.py`, `src/api/routes/health.py`, `src/api/routes/metrics.py`, `docs/DEPLOYMENT.md`, `tests/`

**Acceptance Criteria**:
- [ ] `/health` and `/metrics` are not publicly accessible in non-development environments (policy: admin-auth or explicit private-network-only)
- [ ] `/health/live` remains minimal and unauthenticated (coarse “up” only)
- [ ] Externally reachable health responses do not include raw exception strings or dependency internals
- [ ] Tests cover status codes and payload shapes for dev vs production-like profiles
- [ ] Human sign-off recorded before merge

---

### TASK-190: Harden admin-key compare + API key store file permissions [REQUIRES_HUMAN]
**Priority**: P2 (Medium)
**Estimate**: 1-2 hours

Eliminate timing side-channel risk in admin-key checks and ensure persisted API
key store files are written with restrictive permissions regardless of host
umask.

**Assessment-Ref**:
- `artifacts/assessments/security/daily/2026-03-02.md` (`FINDING-2026-03-02-security-admin-key-compare`)
- `artifacts/assessments/security/daily/2026-03-02.md` (`FINDING-2026-03-02-security-api-key-store-permissions`)

**Files**: `src/api/routes/auth.py`, `src/core/api_key_manager.py`, `docs/OPERATIONS.md`, `tests/`

**Acceptance Criteria**:
- [ ] Replace direct string equality with `secrets.compare_digest(...)` for admin key comparisons
- [ ] Enforce `0600` permissions on persisted key store temp + final files (best-effort cross-platform)
- [ ] Validate parent directory permissions (`0700`) where feasible and fail closed (or emit a high-severity warning) when hardening cannot be applied
- [ ] Tests cover: compare primitive, permission enforcement behavior, and failure/warn paths
- [ ] Human sign-off recorded before merge

---

### TASK-199: Harden trend config sync against write-on-read and arbitrary path access
**Priority**: P1 (High)
**Estimate**: 2-4 hours

`GET /api/v1/trends?sync_from_config=true` still performs writes from a read
route, and `POST /api/v1/trends/sync-config` still accepts arbitrary
server-local directories. Any authenticated client can currently trigger config
reloads and point the server at unexpected YAML paths.

**Assessment-Ref**:
- User review intake 2026-03-05, Reviewer 1 finding 1

**Files**: `src/api/routes/trends.py`, `src/core/trend_config.py`, `docs/API.md`, `tests/`

**Acceptance Criteria**:
- [ ] Remove write side effects from `GET /api/v1/trends` (`sync_from_config` is removed, rejected, or made read-only)
- [ ] Restrict config sync to an explicit allowlisted repo-owned trend-config root and reject path traversal / symlink escape cases
- [ ] Gate config-sync execution behind privileged authorization rather than any valid client key
- [ ] Add tests covering rejected arbitrary paths and no-write behavior on GET

---

### TASK-200: Add authorization boundaries for privileged API mutations
**Priority**: P0 (Critical)
**Estimate**: 1-2 days

The runtime auth layer currently distinguishes only “valid API key” vs
“invalid API key”. Most write/control routes remain effectively admin-capable
for any authenticated client, which violates least privilege.

**Assessment-Ref**:
- User review intake 2026-03-05, Reviewer 1 finding 1
- User review intake 2026-03-05, Reviewer 2 finding 1

**Exec Plan**: Required (`tasks/exec_plans/README.md`)
**Files**: `src/api/middleware/auth.py`, `src/api/routes/sources.py`, `src/api/routes/trends.py`, `src/api/routes/feedback.py`, `docs/API.md`, `docs/DEPLOYMENT.md`, `tests/`

**Acceptance Criteria**:
- [ ] Define an explicit authorization model for privileged routes (for example admin-scoped keys, role-bearing keys, or equivalent fail-closed policy)
- [ ] Apply the policy to mutation/control endpoints including source CRUD, trend create/update/delete/sync, and feedback/invalidation/override routes
- [ ] Return deterministic authorization failures (`401`/`403`) with audit logs that identify denied privileged actions
- [ ] Add tests covering least-privilege behavior for valid non-admin keys vs privileged credentials

---

### TASK-201: Preserve audited, atomic manual trend overrides
**Priority**: P1 (High)
**Estimate**: 2-4 hours

`PATCH /api/v1/trends/{id}` still accepts `current_probability` and writes
`current_log_odds` directly, bypassing the atomic delta path and the
`HumanFeedback` audit trail used by the dedicated override endpoint.

**Assessment-Ref**:
- User review intake 2026-03-05, Reviewer 1 finding 2
- User review intake 2026-03-05, Reviewer 2 finding 3

**Files**: `src/api/routes/trends.py`, `src/api/routes/feedback.py`, `src/core/trend_engine.py`, `tests/`

**Acceptance Criteria**:
- [ ] `PATCH /api/v1/trends/{id}` can no longer mutate live probability state outside the audited override flow
- [ ] All manual probability changes use the atomic delta path and emit `HumanFeedback` lineage, or the generic patch route rejects such writes explicitly
- [ ] Add tests covering unauthorized direct probability rewrites and preserved audit/atomicity behavior

---

### TASK-202: Make degraded replay queue retryable instead of fail-once terminal
**Priority**: P1 (High)
**Estimate**: 3-5 hours

Degraded-mode replay currently drains only `pending` rows, increments attempts,
and converts any exception into terminal `error` with no retry/backoff path.
Transient model/provider/DB failures can strand held deltas permanently.

**Assessment-Ref**:
- User review intake 2026-03-05, Reviewer 1 finding 3

**Files**: `src/workers/tasks.py`, `src/storage/models.py`, `docs/ARCHITECTURE.md`, `tests/`

**Acceptance Criteria**:
- [ ] Replay queue distinguishes retryable failures from terminal/manual-review failures
- [ ] Retryable replay failures re-enter a bounded retry/backoff path automatically instead of becoming unrecoverable `error` rows on first failure
- [ ] Exhausted or non-retryable failures remain auditable with clear terminal status and last-error context
- [ ] Add tests covering transient replay failure -> retry -> success and exhausted retry behavior

---

### TASK-203: Enforce validated, unique runtime trend identifiers across config and API
**Priority**: P0 (Critical)
**Estimate**: 1 day

Runtime trend routing still keys on `definition.id`, but API create/update
paths do not fully validate the taxonomy contract and the database still does
not enforce uniqueness for that runtime identifier. One bad write can silently
shadow another active trend in Tier-2 routing.

**Assessment-Ref**:
- User review intake 2026-03-05, Reviewer 1 finding 4
- User review intake 2026-03-05, Reviewer 2 finding 4

**Exec Plan**: Required (`tasks/exec_plans/README.md`)
**Files**: `src/core/trend_config.py`, `src/api/routes/trends.py`, `src/processing/pipeline_orchestrator.py`, `src/storage/models.py`, `alembic/`, `tests/`

**Acceptance Criteria**:
- [ ] API create/update paths validate trend payloads against the same contract used by config sync (or an explicitly shared schema)
- [ ] Enforce uniqueness for the runtime trend identifier used by Tier-2 matching (`definition.id` or a dedicated normalized column), with migration-time duplicate detection
- [ ] Fail closed on duplicate/ambiguous runtime identifiers instead of silently overwriting dict entries in orchestration
- [ ] Add tests covering duplicate identifier rejection and config/API validation parity

---

### TASK-204: Recompute applied trend evidence when Tier-2 impacts change
**Priority**: P0 (Critical)
**Estimate**: 1-2 days

Tier-2 reclassification still overwrites `event.extracted_claims["trend_impacts"]`
without reconciling already-applied `TrendEvidence`. When severity, direction,
or impacted trends change, the stored delta remains stale.

**Assessment-Ref**:
- User review intake 2026-03-05, Reviewer 2 finding 2

**Exec Plan**: Required (`tasks/exec_plans/README.md`)
**Files**: `src/processing/tier2_classifier.py`, `src/processing/pipeline_orchestrator.py`, `src/core/trend_engine.py`, `src/storage/models.py`, `docs/ARCHITECTURE.md`, `tests/`

**Acceptance Criteria**:
- [ ] Detect differences between previously applied impacts and newly classified impacts for the same event
- [ ] Reverse, replace, or otherwise reconcile stale `TrendEvidence` rows and trend deltas when impact payloads change
- [ ] Preserve an auditable lineage showing which evidence was superseded by reclassification
- [ ] Add tests covering severity/direction changes and event merges that alter impact application

---

### TASK-205: Requeue retryable pipeline failures instead of permanently erroring items
**Priority**: P0 (Critical)
**Estimate**: 1 day

The processing pipeline still catches broad exceptions inside per-item stages and
marks items `ERROR`, which prevents Celery-level retries from handling transient
LLM/provider/network failures. Retryable failures can therefore become permanent
item failures after partial side effects.

**Assessment-Ref**:
- User review intake 2026-03-05, Reviewer 3 finding 1

**Exec Plan**: Required (`tasks/exec_plans/README.md`)
**Files**: `src/processing/pipeline_orchestrator.py`, `src/workers/tasks.py`, `docs/ARCHITECTURE.md`, `tests/`

**Acceptance Criteria**:
- [ ] Classify retryable exceptions distinctly from terminal data/validation failures across prepare, Tier-1, embedding, clustering, and Tier-2 stages
- [ ] Retryable failures leave items in a safe retryable state and allow task-level retry/backoff to execute
- [ ] Partial side effects remain idempotent or are explicitly rolled back so reprocessing is safe
- [ ] Add tests covering transient provider failures that eventually succeed without leaving items stranded in `ERROR`

---

### TASK-206: Keep event recency monotonic under late and backfilled mentions
**Priority**: P1 (High)
**Estimate**: 1-2 hours

`last_mention_at` is still overwritten with the incoming item timestamp during
merge and lifecycle handling. Late or backfilled items can therefore move event
recency backwards and distort clustering/lifecycle behavior.

**Assessment-Ref**:
- User review intake 2026-03-05, Reviewer 3 finding 2

**Files**: `src/processing/event_clusterer.py`, `src/processing/event_lifecycle.py`, `tests/`

**Acceptance Criteria**:
- [ ] Update recency with `max(existing_last_mention_at, incoming_mention_time)` semantics
- [ ] Keep lifecycle transitions and clustering windows based on monotonic recency
- [ ] Add tests covering older backfill arriving after newer mentions

---

### TASK-207: Use stable source identity keys for GDELT and Telegram watermarks
**Priority**: P2 (Medium)
**Estimate**: 2-4 hours

GDELT and Telegram source lookup still keys on mutable display names. Renaming a
configured source can create a new `sources` row and reset watermarks, fetch
history, and failure tracking.

**Assessment-Ref**:
- User review intake 2026-03-05, Reviewer 3 finding 3

**Files**: `src/ingestion/gdelt_client.py`, `src/ingestion/telegram_harvester.py`, `src/storage/models.py`, `alembic/`, `docs/ARCHITECTURE.md`, `tests/`

**Acceptance Criteria**:
- [ ] Look up or persist GDELT/Telegram sources by stable provider identifier (for example query id / query fingerprint and channel handle) instead of mutable display name
- [ ] Preserve existing watermarks, error counters, and fetch history across harmless config renames
- [ ] Add tests covering rename/no-reset behavior for both collectors

---

### TASK-208: Restrict API docs and schema exposure outside development
**Priority**: P2 (Medium)
**Estimate**: 1-2 hours

`/docs`, `/redoc`, and `/openapi.json` are still exempt from auth even when API
auth is enabled. That leaves the full route inventory and request schema visible
to unauthenticated clients in non-development environments.

**Assessment-Ref**:
- User review intake 2026-03-05, Reviewer 3 finding 4

**Files**: `src/api/middleware/auth.py`, `src/api/main.py`, `src/cli.py`, `docs/DEPLOYMENT.md`, `tests/`

**Acceptance Criteria**:
- [ ] Restrict or disable `/docs`, `/redoc`, and `/openapi.json` outside development by explicit environment policy
- [ ] Preserve a documented development/test workflow for local schema/docs access
- [ ] Update smoke/doctor tooling if they currently assume unauthenticated `/openapi.json`
- [ ] Add tests covering docs/schema visibility across development vs non-development profiles

---

### TASK-209: Restore `canonical_summary` alignment with `primary_item_id` after Tier-2
**Priority**: P1 (High)
**Estimate**: 2-4 hours

`TASK-148` aligned `canonical_summary` with `primary_item_id`, but Tier-2 still
overwrites `canonical_summary` with a synthesized event summary on every
classification. That reintroduces the semantic drift the earlier task removed.

**Assessment-Ref**:
- User review intake 2026-03-05, Reviewer 1 finding 5

**Files**: `src/processing/event_clusterer.py`, `src/processing/tier2_classifier.py`, `docs/DATA_MODEL.md`, `tests/`

**Acceptance Criteria**:
- [ ] Preserve `canonical_summary` as the summary of the current `primary_item_id`, or explicitly rename/split fields if event-level synthesized summary is still required
- [ ] Ensure Tier-2 writes do not silently violate the documented `primary_item_id` semantics
- [ ] Add regression tests covering cluster merge plus Tier-2 classification on the same event
- [ ] Update docs to reflect the final semantics unambiguously

---

### TASK-225: Make `horadus triage collect` Return Task-Aware Search Hits
**Priority**: P2 (Medium)
**Estimate**: 1-2 hours

Replace raw line-grep style search hits in triage bundles with deduplicated,
task-aware matches that are directly useful to agents during backlog review.

**Files**: `src/horadus_cli/v2/triage_commands.py`, `tools/horadus/python/horadus_workflow/triage.py`, `tools/horadus/python/horadus_workflow/task_repo.py`, `tests/horadus_cli/`, `tests/workflow/`

**Acceptance Criteria**:
- [ ] Convert keyword/path/proposal search hits into task-aware records with `task_id`, title, status, and matched fields
- [ ] Deduplicate multiple matching lines from the same task while preserving enough context to explain the hit
- [ ] Keep raw line-level details optional rather than the default payload
- [ ] Preserve JSON stability for agent consumption and concise text summaries for humans
- [ ] Add regression tests covering keyword, path, and proposal matching

---

### TASK-226: Add Compact Assessment Summaries to `horadus triage collect`
**Priority**: P2 (Medium)
**Estimate**: 1-2 hours

The current triage bundle returns long flat assessment path lists. Replace that
with compact summaries that preserve recent-signal value without flooding agent
contexts.

**Files**: `src/horadus_cli/v2/triage_commands.py`, `tools/horadus/python/horadus_workflow/triage.py`, `tests/horadus_cli/`, `tests/workflow/`

**Acceptance Criteria**:
- [ ] Group recent assessments by role with counts and latest artifact metadata
- [ ] Add an option to bound or summarize assessment lists for agent-oriented JSON output
- [ ] Keep full path enumeration available when explicitly requested
- [ ] Keep text output concise while still indicating assessment coverage
- [ ] Add regression tests for grouped summaries and explicit full-list mode

---

### TASK-227: Make Corroboration Provenance-Aware Instead of Source-Count-Aware
**Priority**: P1 (High)
**Estimate**: 6-8 hours

The current pipeline already avoids raw item-count inflation, but corroboration
is still too easily overstated by syndicated, copied, or tightly coupled
reporting ecosystems. Extend the existing claim-graph/corroboration work so
trend scoring uses conservative independent-evidence groups instead of treating
distinct outlets as sufficient proof of independence.

This is a follow-up hardening task, not a replacement for completed
`TASK-065` and `TASK-128`.

**Assessment-Ref**:
- User-provided external architecture evaluation on 2026-03-06

**Files**: `src/processing/pipeline_orchestrator.py`, `src/storage/models.py`, `src/ingestion/`, `src/api/routes/events.py`, `src/api/routes/trends.py`, `tests/`, `alembic/`

**Acceptance Criteria**:
- [ ] Derive and persist bounded provenance signals needed to group event evidence by likely independent origin (for example source family, syndication lineage, or near-duplicate reporting clusters)
- [ ] Update corroboration scoring to prefer independent-evidence group counts over raw/distinct source counts when provenance metadata is available
- [ ] Keep scoring fail-safe by falling back to the current conservative path when provenance grouping is incomplete or ambiguous
- [ ] Expose enough runtime/debug visibility to compare raw source counts versus independent-evidence counts on events and/or evidence responses
- [ ] Preserve existing invalidation, replay, and idempotency semantics under the new corroboration model
- [ ] Add regression coverage for syndicated wire copy, reposted channel content, and genuinely independent multi-source corroboration cases

---

### TASK-228: Harden Trend Forecast Contracts with Explicit Horizon and Resolution Semantics
**Priority**: P1 (High)
**Estimate**: 4-6 hours

Trend probabilities are only semantically honest when each trend has a clearly
defined forecast object. Extend trend definitions and runtime validation so each
active trend explicitly states the forecast horizon, measurable resolution
criteria, and closure semantics instead of relying on descriptive prose alone.

This is a follow-up hardening task that builds on existing baseline and
falsification-criteria work.

**Assessment-Ref**:
- User-provided external architecture evaluation on 2026-03-06

**Files**: `src/core/trend_config.py`, `src/api/routes/trends.py`, `config/trends/`, `tests/`, `docs/`

**Acceptance Criteria**:
- [ ] Extend trend definition schema with explicit forecast-contract fields such as horizon, measurable resolution basis, and closure rule
- [ ] Fail config sync and API writes when required forecast-contract fields are missing or internally inconsistent
- [ ] Surface forecast-contract metadata in trend API responses so operators can inspect what the probability actually refers to
- [ ] Add migration/backfill guidance for existing trend YAMLs without breaking current trend IDs
- [ ] Add regression coverage for missing-horizon, ambiguous-resolution, and valid-contract cases

---

### TASK-229: Add a Novelty Lane Outside the Active Trend List
**Priority**: P1 (High)
**Estimate**: 6-8 hours

Tier-1 routing against only the active trend catalog is cost-efficient but can
create tunnel vision. Add a bounded side channel that surfaces persistent novel
clusters and near-miss items that do not map cleanly to current tracked trends.

**Assessment-Ref**:
- User-provided external architecture evaluation on 2026-03-06

**Files**: `src/processing/`, `src/storage/models.py`, `src/api/routes/feedback.py`, `tests/`, `alembic/`

**Acceptance Criteria**:
- [ ] Persist bounded novelty candidates derived from unscored or low-confidence items/events without applying trend deltas
- [ ] Rank novelty candidates using stable signals such as recurrence, unusual actor/location combinations, or repeated near-threshold relevance
- [ ] Keep the novelty lane budget-safe and independent from the normal active-trend scoring path
- [ ] Expose novelty candidates in an operator-facing API or review queue endpoint
- [ ] Add regression coverage showing that novel persistent signals surface even when they do not map to active trends

---

### TASK-230: Add Coverage Observability Beyond Source Freshness
**Priority**: P1 (High)
**Estimate**: 4-6 hours

Fresh collectors do not guarantee adequate coverage. Add coverage observability
so operators can distinguish "no signal" from "no coverage" across geography,
language, source family, and topical dimensions.

**Assessment-Ref**:
- User-provided external architecture evaluation on 2026-03-06

**Files**: `src/core/observability.py`, `src/workers/tasks.py`, `src/api/routes/reports.py`, `src/storage/models.py`, `tests/`

**Acceptance Criteria**:
- [ ] Compute bounded coverage summaries segmented by language, source family/tier, and configured topical dimensions
- [ ] Persist or export coverage artifacts suitable for operational review and release-gate inputs
- [ ] Expose a read-only API/report path for recent coverage health distinct from collector freshness
- [ ] Add metrics/logs that make sudden coverage drops visible even when collectors remain healthy
- [ ] Add regression coverage for low-coverage and balanced-coverage cases

---

### TASK-231: Extend Event Invalidation into a Compensating Restatement Ledger
**Priority**: P1 (High)
**Estimate**: 6-8 hours

The system already preserves invalidation lineage, but it still lacks a richer
restatement model for material reinterpretation, partial retraction, and
analyst-issued compensating corrections. Extend invalidation into an explicit
ledger of restatement actions without destroying audit history.

**Assessment-Ref**:
- User-provided external architecture evaluation on 2026-03-06

**Files**: `src/storage/models.py`, `src/api/routes/feedback.py`, `src/core/trend_engine.py`, `src/processing/pipeline_orchestrator.py`, `tests/`, `alembic/`

**Acceptance Criteria**:
- [ ] Introduce explicit compensating-restatement records that distinguish full invalidation from partial reinterpretation/manual correction
- [ ] Preserve append-only auditability while allowing later corrections to adjust prior probability effects honestly
- [ ] Keep replay, decay, and idempotency semantics correct under compensating restatement flows
- [ ] Expose lineage so operators can inspect original evidence, restatement action, and resulting net effect
- [ ] Add regression coverage for invalidate, partial restate, and manual compensating-delta scenarios

---

### TASK-232: Strengthen Operator Adjudication Workflow for High-Risk Events
**Priority**: P2 (Medium)
**Estimate**: 4-6 hours

The backend already exposes review-oriented primitives, but high-risk event
handling still needs a more explicit adjudication workflow. Harden the operator
path for contradiction-heavy, high-delta, low-confidence, and taxonomy-gap
cases so review is first-class rather than ad hoc.

This task should build on `TASK-231` for any persisted `restate` semantics so
the operator workflow reuses one canonical compensating-restatement model.

**Assessment-Ref**:
- User-provided external architecture evaluation on 2026-03-06

**Files**: `src/api/routes/feedback.py`, `src/api/routes/events.py`, `src/storage/models.py`, `tests/`

**Acceptance Criteria**:
- [ ] Extend review-queue ranking and filtering for high-delta low-confidence, contradiction-heavy, and taxonomy-gap-linked events
- [ ] Persist operator workflow state needed to track review status beyond simple feedback rows
- [ ] Support explicit adjudication outcomes such as confirm, suppress, restate, and escalate-for-taxonomy-review
- [ ] Expose enough queue metadata for a future UI without coupling the backend to a frontend implementation
- [ ] Add regression coverage for ranking, status transitions, and adjudication outcome effects

---

### TASK-233: Support Multi-Horizon Trend Variants for the Same Underlying Theme
**Priority**: P2 (Medium)
**Estimate**: 6-8 hours

Many forecast subjects behave differently across 7-day, 30-day, and 90-day
horizons. Add bounded support for multi-horizon trend variants so the system
can represent short-, medium-, and longer-horizon probabilities without
pretending they are interchangeable.

**Assessment-Ref**:
- User-provided external architecture evaluation on 2026-03-06

**Files**: `src/core/trend_config.py`, `src/api/routes/trends.py`, `src/storage/models.py`, `config/trends/`, `tests/`, `alembic/`

**Acceptance Criteria**:
- [ ] Extend trend definitions so related horizon variants can be modeled explicitly without overloading one trend record
- [ ] Keep scoring, decay, outcomes, and calibration paths horizon-aware
- [ ] Preserve backward compatibility for existing single-horizon trends
- [ ] Expose horizon metadata clearly in APIs and reporting outputs
- [ ] Add regression coverage for multiple horizon variants under the same theme

---

### TASK-234: Make Uncertainty and Momentum First-Class Trend State
**Priority**: P2 (Medium)
**Estimate**: 4-6 hours

Probability alone is too compressive for operator-facing interpretation. Promote
uncertainty and recent directional momentum from derived presentation details to
first-class tracked trend state and reporting context.

**Assessment-Ref**:
- User-provided external architecture evaluation on 2026-03-06

**Files**: `src/core/risk.py`, `src/api/routes/trends.py`, `src/core/report_generator.py`, `src/storage/models.py`, `tests/`, `alembic/`

**Acceptance Criteria**:
- [ ] Define bounded, explainable representations for trend uncertainty and recent momentum that do not duplicate raw probability
- [ ] Persist or deterministically derive these fields in a way that is stable across API and report paths
- [ ] Expose them directly in trend APIs and report statistics
- [ ] Keep historical interpretation possible by tying momentum to recent snapshot/evidence windows
- [ ] Add regression coverage for stable, accelerating, and highly uncertain trend cases

---

### TASK-235: Add Event Split/Merge Lineage for Evolving Stories
**Priority**: P1 (High)
**Estimate**: 6-8 hours

Similarity-plus-time-window clustering is a good baseline, but evolving stories
need explicit lineage when one event later proves to contain multiple subevents
or when separate clusters converge into the same story. Add event split/merge
lineage so clustering corrections remain auditable.

**Assessment-Ref**:
- User-provided external architecture evaluation on 2026-03-06

**Files**: `src/processing/event_clusterer.py`, `src/storage/models.py`, `src/api/routes/events.py`, `tests/`, `alembic/`

**Acceptance Criteria**:
- [ ] Add explicit event-lineage records for split and merge operations
- [ ] Preserve raw-item linkage auditability when events are corrected after initial clustering
- [ ] Keep downstream evidence/reporting paths consistent when lineage changes occur
- [ ] Expose lineage metadata in event detail responses for operator debugging
- [ ] Add regression coverage for split, merge, and no-op lineage cases

---

### TASK-236: Add Canonical Entity Registry for Actors, Organizations, and Locations
**Priority**: P2 (Medium)
**Estimate**: 8-12 hours

Event extraction currently stores useful text fields, but the system lacks a
canonical entity layer for actors, organizations, locations, facilities, and
aliases. Add a bounded entity registry to improve clustering quality, review
workflow clarity, and future causal/precursor analysis.

**Assessment-Ref**:
- User-provided external architecture evaluation on 2026-03-06

**Files**: `src/storage/models.py`, `src/processing/tier2_classifier.py`, `src/api/routes/events.py`, `tests/`, `alembic/`

**Acceptance Criteria**:
- [ ] Introduce canonical entity records with alias support for at least people/organizations/locations
- [ ] Link extracted event entities to canonical entities without blocking the pipeline on perfect resolution
- [ ] Keep the entity-matching path bounded and safe under multilingual/alias ambiguity
- [ ] Expose canonical entity references in event detail responses
- [ ] Add regression coverage for alias resolution, unresolved entities, and mixed-language cases

---

### TASK-237: Add Dynamic Reliability Diagnostics and Time-Varying Source Credibility
**Priority**: P2 (Medium)
**Estimate**: 6-8 hours

Static source credibility tiers are useful as a baseline, but they are too
blunt to fully represent topic-specific, region-specific, and time-varying
source behavior. Extend the existing reliability diagnostics so the system can
surface empirical source reliability patterns and optionally derive bounded
advisory adjustments without replacing the operator-controlled base ratings.

**Assessment-Ref**:
- User-provided external architecture evaluation on 2026-03-06

**Files**: `src/core/calibration_dashboard.py`, `src/core/source_credibility.py`, `src/api/routes/reports.py`, `src/storage/models.py`, `tests/`, `docs/`

**Acceptance Criteria**:
- [ ] Extend reliability diagnostics to segment outcome-linked source behavior by bounded dimensions such as source, source tier, topic family, or geography where data is available
- [ ] Define a conservative time-varying reliability signal or advisory adjustment layer that never silently overrides configured base credibility
- [ ] Keep sparse-data handling fail-safe by suppressing or flagging low-sample diagnostics instead of producing misleading precision
- [ ] Expose source-reliability diagnostics in an operator-facing API/report path with enough context to distinguish configured credibility from empirical advisory signals
- [ ] Add regression coverage for stable, drifting, and low-sample reliability cases

---

### TASK-238: Prioritize Tier-2 Budget with Value-of-Information Scheduling
**Priority**: P2 (Medium)
**Estimate**: 5-7 hours

Tier-2 budget is bounded, so queue order should favor items that are most likely
to reduce uncertainty or materially change tracked forecasts. Add a bounded
value-of-information scheduler for Tier-2 processing so scarce model budget is
spent on the most decision-relevant work first.

**Assessment-Ref**:
- User-provided external architecture evaluation on 2026-03-06

**Files**: `src/processing/pipeline_orchestrator.py`, `src/processing/tier1_classifier.py`, `src/processing/cost_tracker.py`, `src/storage/models.py`, `tests/`, `docs/`

**Acceptance Criteria**:
- [ ] Define a deterministic Tier-2 prioritization score using bounded inputs such as expected delta magnitude, uncertainty, contradiction risk, novelty, and trend relevance
- [ ] Reorder or batch Tier-2 candidate processing by this score when budget pressure exists, without breaking idempotency or starvation safety
- [ ] Keep the scheduling policy explainable by surfacing the main factors behind Tier-2 prioritization decisions in logs, metrics, or debug responses
- [ ] Preserve current behavior as a safe fallback when value-of-information inputs are unavailable
- [ ] Add regression coverage for high-impact ambiguity-first prioritization, low-value deprioritization, and bounded fairness behavior

---

### TASK-251: Normalize Task Specs Around Explicit Input/Output Contracts
**Priority**: P2 (Medium)
**Estimate**: 2-4 hours

Current backlog items already have acceptance criteria, but spec quality still
depends too much on author judgment. Tighten the task/spec template so new work
is consistently framed in terms of inputs, outputs, non-goals, and acceptance
criteria that an agent can execute against without inflating scope.

**Canonical Example**: `tasks/specs/275-finish-review-gate-timeout.md`

**Files**: `tasks/BACKLOG.md`, `tasks/specs/`, `tasks/exec_plans/TEMPLATE.md`, `docs/AGENT_RUNBOOK.md`, `src/horadus_cli/`, `tests/unit/`

**Scope Boundary**:
- `TASK-251` owns the baseline task/spec contract:
  problem statement, inputs, outputs, non-goals, acceptance criteria, and one
  canonical repo-owned example/reference for that baseline structure.
- `TASK-298` owns the added Phase -1 planning gates, Gate Outcomes / Waivers,
  applicability rules, warn-only planning validation, and any `context-pack` /
  runbook surfacing specific to those gates, including any gate-specific
  example overlays built on top of the same baseline example rather than a
  second canonical example.

**Acceptance Criteria**:
- [ ] Define a canonical task/spec shape for new implementation work: problem statement, inputs, outputs, non-goals, and acceptance criteria
- [ ] Add a concrete repo artifact for that shape, such as `tasks/specs/TEMPLATE.md` or one canonical example spec referenced from workflow docs
- [ ] Update the repo templates or documented examples so future specs follow the same structure by default
- [ ] Keep the contract lightweight enough for small tasks while still being explicit for complex tasks
- [ ] Surface the structure in task-context tooling or docs so agents see it without reading the full backlog

---

### TASK-252: Add a Canonical Post-Task Local Gate Without Overloading `make agent-check`
**Priority**: P1 (High)
**Estimate**: 2-4 hours

The repo already has a fast local iteration gate in `make agent-check`. Preserve
that fast path and add a separate canonical post-task local gate so agents have
one command for “done with this task locally” checks without blurring the
current fast/full split.

**Files**: `Makefile`, `scripts/run_with_backpressure.sh`, `docs/AGENT_RUNBOOK.md`, `README.md`, `src/horadus_cli/`, `tests/unit/`

**Acceptance Criteria**:
- [ ] Keep `make agent-check` positioned as the fast local iteration gate
- [ ] Add a separate canonical post-task local gate command (for example `make local-gate` or `make task-gate`)
- [ ] The new gate runs the intended post-task checks in one documented sequence without replacing the fast gate
- [ ] `horadus tasks context-pack` suggested validation commands are updated to reflect the new canonical post-task gate rather than the old validation flow
- [ ] Output remains backpressure-friendly and clearly identifies which sub-step failed
- [ ] Docs explain when to use the fast gate versus the new post-task gate

---

### TASK-254: Refine and Unify Agent-Facing Context Entry Points
**Priority**: P2 (Medium)
**Estimate**: 1-2 hours

Agents benefit from a short routing document, but a second full-project
`README_AI.md` would duplicate existing truth in `AGENTS.md`, architecture docs,
runtime code, and existing runbook/context-pack entry points. Refine those
entrypoints into a more coherent agent-facing navigation layer without creating
another canonical project summary to keep in sync.

**Files**: `AGENTS.md`, `docs/AGENT_RUNBOOK.md`, `README.md`, `src/horadus_cli/v2/`, `tools/horadus/python/horadus_workflow/docs_freshness.py`, `scripts/check_docs_freshness.py`, `tests/workflow/`, `tests/horadus_cli/`

**Acceptance Criteria**:
- [ ] Refine or unify the existing agent-facing entrypoints (`AGENTS.md`, runbook, context-pack guidance) into a clearer navigation path
- [ ] Define one short agent-facing entrypoint/index that links to the current runtime, sprint, architecture, data model, and workflow sources of truth
- [ ] Explicitly state that runtime code/tests remain authoritative over the agent-facing index
- [ ] Avoid duplicating detailed architecture, schema, or ops content that already lives elsewhere
- [ ] `horadus tasks context-pack` remains aligned with the unified agent-facing navigation rather than pointing to stale or divergent workflow guidance
- [ ] Add or extend drift checks only if needed to keep the index’s core pointers accurate

---

### TASK-255: Add a Targeted Docstring Quality Gate for High-Value Surfaces
**Priority**: P2 (Medium)
**Estimate**: 3-5 hours

Detailed code explanations are valuable in complex domain logic, but blanket
“document every function exhaustively” rules would create noise and stale prose.
Add an automated docstring policy for the parts of the codebase where it
actually improves agent and human comprehension.

**Files**: `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`, `src/core/`, `src/processing/`, `src/workers/`, `docs/AGENT_RUNBOOK.md`, `tests/`

**Acceptance Criteria**:
- [ ] Define a scoped docstring policy covering module docs, public APIs, and complex algorithms/invariants in selected high-value paths
- [ ] Add an automated check for that scoped policy in local and/or CI quality gates
- [ ] Avoid forcing exhaustive comments for trivial private helpers where names and types are already sufficient
- [ ] Document when to prefer docstrings versus short inline comments versus no extra prose

---

### TASK-256: Enforce the Task Completion Contract for Tests, Docs, and Gate Re-Runs
**Priority**: P1 (High)
**Estimate**: 2-4 hours

The repo already expects tests and docs updates, but the completion contract is
still partly social. Make the “task is done” rules more explicit in tooling so
agents reliably add tests, rerun local gates, and update docs when behavior or
workflow changes.

**Files**: `AGENTS.md`, `Makefile`, `scripts/finish_task_pr.sh`, `src/horadus_cli/`, `docs/AGENT_RUNBOOK.md`, `tests/unit/`

**Acceptance Criteria**:
- [ ] Task-finish guidance or tooling explicitly requires relevant tests for code changes unless a documented N/A condition applies
- [ ] Task-finish guidance or tooling explicitly requires rerunning the canonical post-task local gate before merge
- [ ] Task-finish guidance or tooling explicitly requires the local integration gate where the task touches integration-covered paths or push/PR workflow requires it
- [ ] Task-finish guidance or tooling calls out documentation updates when behavior, workflow, or operator-facing contracts changed
- [ ] `horadus tasks context-pack` suggested validation commands stay aligned with the effective completion contract when that contract changes
- [ ] The resulting contract is visible in agent-facing workflow docs, not just implicit in scattered instructions

---

### TASK-267: Add a Thin Repo Workflow Skill Routed to AGENTS and Horadus
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Agents benefit from a short procedural workflow aid, but the repo already
defines `AGENTS.md` as the authoritative workflow policy and expects
agent-facing materials to route to canonical sources rather than redefine them.
Add a thin repo workflow skill that helps agents execute the canonical flow
while staying anchored to `AGENTS.md` and the `horadus` CLI.

**Files**: `ops/skills/repo-workflow/SKILL.md`, `ops/skills/repo-workflow/references/`, `AGENTS.md`, `docs/AGENT_RUNBOOK.md`, `ops/skills/horadus-cli/SKILL.md`, `tests/workflow/test_docs_freshness.py`, `scripts/`

**Acceptance Criteria**:
- [ ] Add a dedicated repo workflow skill that provides short procedural guidance for the canonical task lifecycle
- [ ] The skill explicitly states that `AGENTS.md` remains the authoritative workflow policy and `horadus` remains the canonical executable workflow surface
- [ ] The skill routes agents to existing canonical commands and policy sections instead of restating the full workflow contract in independent prose
- [ ] The skill explains when to use `horadus`, when wrapper commands such as `make` are acceptable, and when raw `git`/`gh` is still necessary as an escape hatch
- [ ] The skill covers start flow, local validation flow, completion flow, and blocker escalation only at the level needed to steer agents to the correct canonical commands/docs
- [ ] The skill stays aligned with `docs/AGENT_RUNBOOK.md` and `ops/skills/horadus-cli/SKILL.md` without creating a second standalone workflow spec
- [ ] Add or extend a drift check so the workflow skill cannot silently diverge from canonical workflow guidance

---

### TASK-272: Keep Active Reasoning Metadata Consistent Across Mixed-Route Runs
**Priority**: P2 (Medium)
**Estimate**: 1-3 hours

Run-level usage metadata should not report an `active_reasoning_effort` from an
earlier GPT-5 call after provider/model have moved to a later route that has no
reasoning setting. Make mixed-route aggregation internally consistent across
Tier-1 and Tier-2 telemetry and benchmark artifacts.

**Files**: `src/processing/tier1_classifier.py`, `src/processing/tier2_classifier.py`, `src/processing/pipeline_orchestrator.py`, `src/eval/benchmark.py`, `tests/unit/processing/test_tier1_classifier.py`, `tests/unit/processing/test_tier2_classifier.py`, `tests/unit/processing/test_pipeline_orchestrator_additional.py`

**Acceptance Criteria**:
- [ ] Mixed-route Tier-1 aggregation cannot report a later provider/model with a stale reasoning effort from an earlier route
- [ ] Mixed-route Tier-2 aggregation cannot report a later provider/model with a stale reasoning effort from an earlier route
- [ ] The chosen contract for aggregated reasoning metadata is explicit and internally consistent across runtime telemetry and eval artifacts
- [ ] Existing metadata consumers continue to receive a stable shape even if the reasoning field is reset to `null`
- [ ] Tests cover transitions from reasoning-enabled routes to routes with no reasoning metadata

---

### TASK-274: Standardize Task PR Titles on `TASK-XXX: ...`
**Priority**: P2 (Medium)
**Estimate**: 1-3 hours

Recent task PRs mix task-prefixed titles and conventional-commit titles even
though task branches, PR body metadata, and squash-merge history are all task-
oriented surfaces. Standardize the PR title convention on
`TASK-XXX: short summary` and add enforcement so branch/task scope, PR body
metadata, and PR title stay aligned.

**Files**: `AGENTS.md`, `README.md`, `.github/pull_request_template.md`, `docs/AGENT_RUNBOOK.md`, `src/horadus_cli/`, `scripts/`, `tests/unit/`

**Acceptance Criteria**:
- [ ] Canonical repo workflow docs explicitly require task PR titles in the form `TASK-XXX: short summary`
- [ ] PR templates and agent-facing guidance show the same task-title convention instead of leaving title format implicit
- [ ] Local and/or CI workflow validation fails when a task PR title does not match the branch task id or required `TASK-XXX:` prefix
- [ ] The rule coexists cleanly with conventional-commit commit messages instead of replacing commit-level naming policy
- [ ] Task-completion workflow output and examples no longer suggest mixed PR-title conventions
- [ ] Tests cover valid task PR titles and representative invalid cases such as `feat(scope): ...` on a task branch

---

### TASK-286: Add Local Pre-Push Review via Codex CLI `[REQUIRES_HUMAN]`
**Priority**: P2 (Medium)
**Estimate**: 2-4 hours

The repo currently relies on local gates plus remote PR review, but there is
no first-class repo workflow step for running a separate Codex review against
local branch changes before push. Add a repo-owned pre-push review command
that wraps the local Codex CLI review flow so agents and humans can request a
local review against unpushed branch diffs without relying on GitHub PR state.
Implement this on the canonical `horadus tasks ...` workflow surface after
`TASK-299` lands the isolated `v2` implementation behind that command, rather
than reopening the frozen legacy `v1` task CLI files directly.

**Files**: `src/horadus_cli/`, `Makefile`, `docs/AGENT_RUNBOOK.md`, `ops/skills/horadus-cli/SKILL.md`, `ops/skills/horadus-cli/references/commands.md`, `tests/unit/`

**Acceptance Criteria**:
- [ ] The repo exposes a canonical command for local pre-push review via Codex
  CLI under `horadus tasks ...`, with clear failure behavior when `codex` is
  unavailable
- [ ] The command can review the current branch diff against a configured base branch without requiring a remote PR
- [ ] Agent-facing docs and skill surfaces describe when to use the local Codex review step versus remote PR review
- [ ] Tests cover the happy path plus the missing-`codex` or invalid-context blocker path

---

### TASK-288: Convert RFC-001 Context Retrieval Plan Into Approved Implementation Queue [REQUIRES_HUMAN]
**Priority**: P1 (High)
**Estimate**: 1-2 hours
**Spec**: `tasks/specs/288-rfc-001-implementation-breakdown.md`

Convert `docs/rfc/001-agent-context-retrieval.md` into an approved set of
implementation tasks with clear sequencing, but require explicit human review
before finalizing that execution queue. This task is human-gated because it
decides how the RFC becomes actual repo work and may change scope boundaries,
priorities, and rollout order.

**Files**: `tasks/BACKLOG.md`, `tasks/CURRENT_SPRINT.md`, `PROJECT_STATUS.md`, `tasks/specs/288-rfc-001-implementation-breakdown.md`, `docs/rfc/001-agent-context-retrieval.md`

**Acceptance Criteria**:
- [ ] RFC-001 is decomposed into concrete implementation-task candidates with clear scope boundaries
- [ ] The proposed breakdown identifies any human decisions needed for sequencing or scope cuts
- [ ] The task stops for human review/approval before finalizing the follow-up execution queue

---

### TASK-289: Make `horadus tasks finish` Resume or Fail Cleanly When Branch Context Drifts
**Priority**: P1 (High)
**Estimate**: 2-4 hours
**Status**: Behavior already shipped; preserve during `TASK-299`

The current `horadus tasks finish` implementation already supports rerunning
from `main` with an explicit task id. Keep that behavior as part of the
canonical baseline while `TASK-300` / `TASK-299` migrate the implementation
onto the versioned shell and isolated `v2` modules.

---

### TASK-291: Make `horadus tasks finish` Exit When the PR Has Already Merged
**Priority**: P1 (High)
**Estimate**: 2-4 hours
**Status**: Behavior already shipped; preserve during `TASK-299`

The current `horadus tasks finish` implementation already converges when the
PR has reached `MERGED`. Keep that behavior as part of the canonical baseline
while `TASK-300` / `TASK-299` migrate the implementation onto the versioned
shell and isolated `v2` modules.

---

### TASK-306: Unblock Canonical Finish When Only Outdated Review Threads Remain
**Priority**: P1 (High)
**Estimate**: 2-4 hours
**Exec Plan**: Required (`tasks/exec_plans/README.md`)

`horadus tasks finish` can currently reach the green auto-merge stage and still
leave the PR blocked when GitHub treats an outdated unresolved review thread as
a merge blocker. Fix the canonical finish flow so it handles that stale-thread
state without requiring a manual GraphQL thread-resolution fallback.

**Files**: `tools/horadus/python/horadus_workflow/`, `scripts/check_pr_review_gate.py`, `tests/horadus_cli/`, `tests/unit/scripts/`, `docs/AGENT_RUNBOOK.md`, `AGENTS.md`

**Acceptance Criteria**:
- [ ] `horadus tasks finish` handles outdated unresolved review threads on the current PR head without requiring manual thread resolution when the current head is otherwise green
- [ ] Actionable current-head review feedback still blocks completion normally
- [ ] The canonical docs describe the final stale-thread behavior accurately
- [ ] Regression coverage includes at least one outdated-thread pass path and one current-head actionable-thread blocker path

---

## Future Ideas (Not Scheduled)

- [ ] Archive `tasks/specs/` or `tasks/exec_plans/` only if Sprint 4 still shows measurable context pressure after the live-ledger reset.
