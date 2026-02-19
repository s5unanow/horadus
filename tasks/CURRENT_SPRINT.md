# Current Sprint

**Sprint Goal**: Launch-readiness hardening and guidance/doc consistency cleanup  
**Sprint Number**: 2  
**Sprint Dates**: 2026-02-17 to 2026-03-03
**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`

---

## Active Tasks

- `TASK-080` Telegram Collector Task Wiring `[REQUIRES_HUMAN]` — Awaiting manual human execution/approval

---

## Completed This Sprint

- `TASK-162` Agent debugging runtime profile (low-noise, fail-fast, single-request) — DONE ✓
- `TASK-161` Formalize environment semantics (dev/staging/prod) and defaults — DONE ✓
- `TASK-160` Improve URL normalization to avoid false-duplicate matches — DONE ✓
- `TASK-159` Externalize token pricing to config and model/version mapping — DONE ✓
- `TASK-158` Make claim-graph contradiction heuristics language-aware (en/uk/ru) — DONE ✓
- `TASK-157` Persist full evidence factorization inputs for long-horizon auditability — DONE ✓
- `TASK-156` Constrain categorical “dimension” fields to prevent drift (DB-level) — DONE ✓
- `TASK-155` Make semantic cache non-blocking in async pipeline paths — DONE ✓
- `TASK-154` Allow multiple Tier-2 impacts per trend per event (trend_id + signal_type) — DONE ✓
- `TASK-153` Guard integration-test DB truncation (operator safety) — DONE ✓
- `TASK-151` Version trend definition changes for auditability — DONE ✓
- `TASK-150` Close `docs/DATA_MODEL.md` drift vs runtime schema (sources/raw_items/events) — DONE ✓
- `TASK-149` Add retention/archival policy for raw_items, events, and trend_evidence — DONE ✓
- `TASK-148` Align event canonical_summary semantics with primary_item_id — DONE ✓
- `TASK-147` Enforce RawItem belongs-to-one-Event invariant at the DB layer — DONE ✓
- `TASK-146` Fix event unique-source counting and lifecycle ordering on merge — DONE ✓
- `TASK-145` Concurrency-safe trend log-odds updates (atomic delta apply) — DONE ✓
- `TASK-142` Production Network Exposure Hardening — DONE ✓
- `TASK-141` Production HTTPS Termination and Secure Ingress — DONE ✓
- `TASK-139` Embedding Input Truncation Telemetry and Guardrails — DONE ✓
- `TASK-138` Improve keyword specificity for 3 vague indicators — DONE ✓
- `TASK-137` Sharpen vague falsification criteria — DONE ✓
- `TASK-136` Add ai_safety_incident indicator to ai-control trend — DONE ✓
- `TASK-135` Clarify baseline_probability referent in trend descriptions — DONE ✓
- `TASK-134` External Assessment Backlog Intake Preservation — DONE ✓
- `TASK-133` Preserve Evidence Lineage on Event Invalidation — DONE ✓
- `TASK-132` Trend-Filtered Events API De-duplication — DONE ✓
- `TASK-131` Forward-Only GDELT Watermark Semantics — DONE ✓
- `TASK-130` Suppression-First Event Lifecycle Guard — DONE ✓
- `TASK-129` Atomic Trend Delta Updates Under Concurrency — DONE ✓
- `TASK-128` Corroboration Row-Parsing Runtime Fix — DONE ✓
- `TASK-126` Taxonomy Drift Guardrails (Runtime Gap Queue + Benchmark Alignment) — DONE ✓
- `TASK-127` Cross-Ledger Drift Reconciliation and Dependency Hygiene — DONE ✓
- `TASK-085` Require Explicit Admin Key for Key Management `[REQUIRES_HUMAN]` — DONE ✓ (human sign-off recorded 2026-02-18; Decision=`Approved`)
- `TASK-140` In-Branch Backlog Capture Rule and Guard — DONE ✓
- `TASK-084` Production Security Default Guardrails `[REQUIRES_HUMAN]` — DONE ✓ (human sign-off recorded 2026-02-18; Decision=`Approved`)
- `TASK-077` Cost-First Pipeline Ordering `[REQUIRES_HUMAN]` — DONE ✓ (human sign-off recorded 2026-02-18; Decision=`Approved`)
- `TASK-070` Trend Baseline Prior Review and Sign-Off — DONE ✓ (human sign-off recorded 2026-02-18; Decision=`Approved`)
- `TASK-118` Launch Readiness and Guidance Drift Assessment — DONE ✓ (human sign-off recorded 2026-02-18; Decision=`Approved`; Launch=`No-Go`)
- `TASK-044` Curated Human-Verified Gold Dataset — DONE ✓ (human sign-off recorded 2026-02-18; `human_verified=325`)
- `TASK-066` Expand Trend Catalog to Multi-Trend Baseline — DONE ✓ (human sign-off recorded 2026-02-17)
- `TASK-125` Delivery Lifecycle Clarification and PR Scope Guard Hardening — DONE ✓
- `TASK-123` Current Sprint File Right-Sizing and Sprint Archive Split — DONE ✓
- `TASK-124` Status Ledger Reconciliation and Active Queue Cleanup — DONE ✓
- `TASK-119` Guidance Hierarchy and AGENTS Router Tightening — DONE ✓
- `TASK-120` Documentation Drift Fixes (ADR References + Data Model Coverage) — DONE ✓
- `TASK-121` Docs Freshness Gate Expansion (Integrity + Coverage Rules) — DONE ✓
- `TASK-122` Launch-Critical Production Guardrails Hardening — DONE ✓

---

## Sprint Archive

- `tasks/sprints/SPRINT_001.md` — Historical Sprint 1 ledger (detailed completed-task history)

---

## Sprint Notes

- `tasks/CURRENT_SPRINT.md` is now the operational execution file and should remain concise.
- Detailed completed-task history belongs in `tasks/sprints/SPRINT_XXX.md` archive files.
- `TASK-044` reviewer checklist: `tasks/assessments/TASK-044-human-curation-checklist-2026-02-17.md`.
- `TASK-044` sign-off record: Reviewer=`s5una`; Date=`2026-02-18`; Decision=`Approved`; human_verified=`325`; Notes=`Manual curation completed; audit/taxonomy gates pass with no warnings.`
- `TASK-066` reviewer checklist: `tasks/assessments/TASK-066-human-signoff-checklist-2026-02-17.md`.
- `TASK-066` sign-off record: Reviewer=`s5una`; Date=`2026-02-17`; Decision=`Approved`; Notes=`All 15 added trends approved via human review; taxonomy validation passes with non-blocking legacy gold-set warnings.`
- `TASK-118` assessment artifact: `tasks/assessments/TASK-118-launch-readiness-assessment-2026-02-18.md`.
- `TASK-118` sign-off record: Reviewer=`s5una`; Date=`2026-02-18`; Decision=`Approved`; Launch=`No-Go`; Notes=`Open launch-readiness backlog must be completed before go-live.`
- `TASK-070` reviewer checklist: `tasks/assessments/TASK-070-baseline-prior-signoff-checklist-2026-02-18.md`.
- `TASK-070` sign-off record: Reviewer=`s5una`; Date=`2026-02-18`; Decision=`Approved`; Notes=`All active trend baseline priors approved in human review; local DB parity command failed with postgres auth mismatch and was accepted as local-environment verification waiver.`
- `TASK-077` reviewer checklist: `tasks/assessments/TASK-077-cost-first-pipeline-checklist-2026-02-18.md`.
- `TASK-077` sign-off record: Reviewer=`s5una`; Date=`2026-02-18`; Decision=`Approved`; Notes=`Tier-1 now runs before embedding/clustering; unit/lint/type checks passed; integration test execution blocked locally by postgres auth mismatch.`
- `TASK-084` reviewer checklist: `tasks/assessments/TASK-084-production-security-guardrails-checklist-2026-02-18.md`.
- `TASK-084` sign-off record: Reviewer=`s5una`; Date=`2026-02-18`; Decision=`Approved`; Notes=`Production startup now rejects weak/short SECRET_KEY values; auth guardrails preserved; core unit/lint/type checks passed.`
- `TASK-140` completion note: `AGENTS.md` now codifies human-gated sequence and in-branch backlog-capture rule with exception criteria.
- `TASK-127` completion note: docs-freshness checks now enforce cross-ledger parity for active sprint tasks vs `PROJECT_STATUS` (in-progress + blocked for `[REQUIRES_HUMAN]`) and detect in-progress/completed dual-listing.
- `TASK-129` completion note: trend log-odds delta paths now use atomic SQL increments, decay uses row-lock serialization, and feedback invalidation/override routes share the same concurrency-safe update path with new integration race tests.
- `TASK-130` completion note: clusterer now checks suppression before merge/lifecycle updates, suppressed-event merges are skipped, and suppression metrics/logging now emit from both clusterer and pipeline stages.
- `TASK-131` completion note: GDELT collection now separates backward pagination cursors from a forward-only persisted source watermark, with monotonic multi-page/partial-page regression coverage and clarified checkpoint docs.
- `TASK-132` completion note: `/events` trend filtering now uses a correlated `EXISTS` predicate to avoid `trend_evidence` join fan-out duplicates, with unit + integration coverage for multi-evidence event de-duplication and order/limit stability.
- `TASK-133` completion note: event invalidation now marks `trend_evidence` lineage (`is_invalidated`, `invalidated_at`, `invalidation_feedback_id`) instead of deleting rows, reverses only active evidence deltas, and exposes invalidated lineage through trend evidence API while operational analytics filter to active evidence by default.
- `TASK-134` completion note: external assessment planning intake is now explicitly preserved in `tasks/BACKLOG.md` with checked governance criteria and overlap mapping to human-gated `TASK-080` (no duplicate implementation tasks created).
- `TASK-135` completion note: baseline referent sentences were standardized across the four targeted trend descriptions, with `elite-mass-polarization` reframed to acceleration/delta semantics and baseline probability values preserved.
- `TASK-136` completion note: `ai-human-control-expansion` now includes `ai_safety_incident` as an escalatory leading indicator (`weight=0.04`) with specified keywords, and taxonomy validation remains green in subset mode.
- `TASK-137` completion note: vague `would_invalidate_model` criteria were replaced with measurable thresholds in `elite-mass-polarization` and `fertility-decline-acceleration`, with both configs validated via `TrendConfig`.
- `TASK-138` completion note: keyword specificity was improved for `governance_capture_signals`, `mainstream_positive_framing`, and `institutional_trust_collapse` with targeted measurement/media/survey terms, and all updated configs pass `TrendConfig` validation.
- `TASK-139` completion note: embedding guardrails now enforce deterministic pre-counted token limits with configurable `truncate`/`chunk` policy, emit structured cut-input logs and truncation metrics, persist embedding input audit metadata on `raw_items`/`events`, and include unit coverage plus weekly ops query guidance for truncation-rate alerting.
- `TASK-141` completion note: production compose defaults now route public `80/443` through Caddy TLS ingress (`docker/caddy/Caddyfile`) with HTTP→HTTPS redirect, required edge security headers, API host-port unexposed by default, and deployment runbook certificate lifecycle/fallback + HTTPS validation commands.
- `TASK-142` completion note: production compose networking now enforces `horadus-edge` vs internal-only `horadus-private` segmentation, keeps API/DB/Redis host-port exposure disabled by default, and updates deployment runbook with explicit public/private port policy plus firewall/allowlisting and outside-host reachability checks.
- `TASK-145` completion note: audit confirmed existing `TASK-129` runtime coverage already satisfies atomic SQL log-odds updates, idempotent evidence insertion, concurrency regression tests, and structured update-strategy logging; backlog/ledger state was reconciled accordingly.
- `TASK-146` completion note: merge path now inserts `event_items` link before metadata/lifecycle recalculation, preventing off-by-one unique-source confirmation drift; regression tests cover threshold confirmation ordering and link-race skip behavior while preserving no-embedding create-path behavior.
- `TASK-147` completion note: `event_items.item_id` is now uniqueness-constrained via migration preflight guard, and clusterer link-conflict handling now resolves to the already-linked `event_id` deterministically without applying conflicting merge metadata updates.
- `TASK-148` completion note: canonical-summary semantics are now explicitly tied to `primary_item_id`; merge path updates `canonical_summary` only when primary changes, preserving primary-aligned summaries across non-primary newest mentions with targeted regression coverage.
- `TASK-149` completion note: added retention cleanup policy/config knobs plus scheduled `workers.run_data_retention_cleanup` with dry-run defaults, per-table cleanup metrics, lifecycle/FK-safe selection rules (noise/error raw items, archived-event windows, evidence-before-event deletion), and deployment runbook workflow for tuning/verification/DB-size trend checks.
- `TASK-150` completion note: `docs/DATA_MODEL.md` now matches runtime schema for `sources`/`raw_items`/`events` (including source tier/reporting/error fields, raw-item `author`, `external_id` length `2048`, event lifecycle/contradiction columns), and ERD scope is explicitly labeled as core-table oriented to prevent misleading completeness assumptions.
- `TASK-151` completion note: added append-only `trend_definition_versions` audit table + migration with deterministic definition hashing, wired create/update/config-sync paths to append rows only on material definition changes, exposed `GET /api/v1/trends/{trend_id}/definition-history`, and added no-op/material-change regression tests.
- `TASK-153` completion note: integration fixture truncation now hard-fails unsafe DB targets unless explicitly test-scoped (or override-enabled), enforces localhost-only truncation by default with explicit remote override, emits actionable refusal messages with resolved target details, and includes unit tests for safe/unsafe target permutations.
- `TASK-154` completion note: Tier-2 output validation now allows multiple impacts for one trend when `signal_type` differs, rejects duplicate `(trend_id, signal_type)` pairs, and prompt/test coverage now codifies multi-signal-per-trend response behavior.
- `TASK-155` completion note: Tier-1/Tier-2 async paths now offload semantic-cache `get/set` calls to a threadpool (`asyncio.to_thread`) so Redis/cache I/O cannot block the event loop, while preserving existing cache key/TTL/eviction semantics and default-disabled behavior.
- `TASK-156` completion note: added DB-level CHECK constraints for `sources.source_tier`, `sources.reporting_type`, and `events.lifecycle_status` in model metadata + migration (`0018`) with fail-fast invalid-value diagnostics before constraint creation; added metadata and integration coverage for constraint enforcement and lifecycle filter behavior.
- `TASK-157` completion note: `trend_evidence` now persists scoring-time `base_weight`, `direction_multiplier`, and `trend_definition_hash` (migration `0019` with legacy-row-safe nullability + deterministic `direction_multiplier` backfill); docs now distinguish scoring-time provenance fields and tests cover reconstruction resilience under later trend-definition changes.
- `TASK-158` completion note: Tier-2 claim-graph heuristics now apply per-language stopwords/negation markers for `en`/`uk`/`ru`, only link same-language supported claim pairs, safely skip mixed/unsupported language pairs, and document prompt/runtime policy limitations with new non-English regression coverage.
- `TASK-159` completion note: token pricing is now configurable via `LLM_TOKEN_PRICING_USD_PER_1M` keyed by `provider:model` with defaults, Tier-1/Tier-2/Embedding budget checks now validate pricing coverage before calls (fail-closed), and usage accounting records model/provider-aware rates with config/cost-policy regression coverage.
- `TASK-160` completion note: URL normalization now preserves non-tracking query params by default (deterministically sorted), strips configured tracking params/prefixes, exposes strictness/strip lists via `DEDUP_URL_QUERY_MODE` + tracking env knobs, and unifies RSS/GDELT normalization through `DeduplicationService` with new URL-policy regression coverage.
- `TASK-161` completion note: `ENVIRONMENT` is now validated to `development|staging|production` with explicit fail-fast errors, production-like guardrails apply to both staging and production via `is_production_like`, staging DB runtime behavior is explicitly pooled, and docs now include environment boundary semantics, staging run guidance, `.env.staging.example`, and ADR `007`.
- `TASK-162` completion note: added independent agent runtime profile controls (`RUNTIME_PROFILE`/`AGENT_MODE`) with production-refusal + loopback guardrails, request-count and unhandled-error shutdown signaling middleware, low-noise effective logging defaults, and deterministic `horadus agent smoke` checks with non-zero failure exits plus profile/middleware/CLI unit coverage.
- `TASK-128` completion note: corroboration scoring now handles SQLAlchemy `Row` mappings safely, emits fallback-path observability metric/log entries, and includes row-shape regression tests.
- `TASK-126` completion note: runtime now records unknown trend/signal taxonomy gaps to `taxonomy_gaps` with triage API + observability metrics, and benchmark taxonomy now loads from `config/trends` with strict preflight fail-fast.
- `TASK-085` reviewer checklist: `tasks/assessments/TASK-085-explicit-admin-key-checklist-2026-02-18.md`.
- `TASK-085` sign-off record: Reviewer=`s5una`; Date=`2026-02-18`; Decision=`Approved`; Notes=`Explicit admin key requirement verified; no authenticated-key fallback remains for key-management endpoints.`
