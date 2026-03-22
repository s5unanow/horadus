# Backlog

Open task definitions only. Completed task history lives in `tasks/COMPLETED.md`, and detailed historical planning ledgers live under `archive/`.

---

## Task ID Policy

- Task IDs are global and never reused.
- Completed IDs are reserved permanently and tracked in `tasks/COMPLETED.md`.
- Next available task IDs start at `TASK-360`.
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

### TASK-354: Centralize repo-owned secret-scan policy and exclude rules
**Priority**: P2 (Medium)
**Estimate**: 2-3 hours

`TASK-352` added a repo-owned server-side secret scan, but the effective policy
still lives in more than one place. The filename excludes and scan semantics are
currently duplicated across pre-commit and the repo-owned baseline-check helper,
which creates drift risk and makes review catch policy mismatches that local
verification should have prevented. Move the secret-scan policy to one
authoritative repo-owned source so local hooks, CI, and workflow helpers apply
the same contract by construction.

**Planning Gates**: Required — shared workflow/security policy contract change
**Files**: `.pre-commit-config.yaml`, `scripts/check_secret_baseline.py`, `scripts/run_secret_scan.sh`, `tests/unit/scripts/`, `tests/workflow/`, `docs/AGENT_RUNBOOK.md`

**Acceptance Criteria**:
- [ ] Define one authoritative repo-owned source for secret-scan excludes and any shared scan-mode semantics that must stay aligned across hook and CI paths
- [ ] Update the pre-commit hook and server-side secret-scan helper to consume that shared policy instead of duplicating regexes or behavior in multiple files
- [ ] Preserve the current documented repo policy for excluded low-risk/high-churn surfaces unless a narrower or broader scope is explicitly justified
- [ ] Add regression coverage that fails when hook-side and server-side secret-scan policy drift apart
- [ ] Document the canonical ownership point so future secret-scan changes do not require parallel manual edits in multiple workflow surfaces

---

### TASK-343: Add caller-aware validation packs for shared helper changes
**Priority**: P1 (High)
**Estimate**: 3-5 hours

`TASK-231` exposed a repeated failure mode where a seemingly small helper change
was locally validated against one direct caller, but later broke adjacent
surfaces that shared the same helper. Cross-surface helpers need a canonical,
repo-owned way to map a code change to the minimum dependent regression suites
and type checks before the first push.

**Files**: `tools/horadus/python/horadus_cli/`, `tools/horadus/python/horadus_workflow/`, `docs/AGENT_RUNBOOK.md`, `AGENTS.md`, `tests/horadus_cli/`, `tests/workflow/`

**Acceptance Criteria**:
- [ ] Define a repo-owned validation-pack contract for high-fanout helper changes instead of relying on ad hoc per-task judgment
- [ ] `horadus tasks context-pack` or an equivalent workflow surface can recommend dependent suites when a change touches shared helpers used across multiple surfaces
- [ ] The contract explicitly includes full-repo type checking when shared Python helpers or domain math are modified
- [ ] Tests cover at least one shared-helper case where the suggested validation set includes more than the most obvious direct caller

---

### TASK-344: Surface review-gate wait state and deadlines in `horadus tasks finish`
**Priority**: P1 (High)
**Estimate**: 2-4 hours

The `horadus tasks finish` review gate currently looks idle for long stretches
while it is actually waiting on a current-head review window. That makes it too
hard to distinguish “working as designed” from “hung on stale state” and slows
down recovery when a task is in the expensive PR/merge loop.

**Files**: `tools/horadus/python/horadus_workflow/task_workflow_finish/`, `tools/horadus/python/horadus_cli/`, `docs/AGENT_RUNBOOK.md`, `tests/workflow/`

**Acceptance Criteria**:
- [ ] `horadus tasks finish` prints explicit status when it is waiting on the review gate rather than appearing silent
- [ ] The wait output includes the current PR head, the reviewer identity, and the review-window deadline or remaining time
- [ ] The finish output distinguishes review-gate waiting from CI waiting and from stale-state refresh work
- [ ] Tests cover at least one review-window wait path and assert the new operator-facing status text

---

### TASK-345: Preflight stale review state before entering the finish review window
**Priority**: P1 (High)
**Estimate**: 2-4 hours

`TASK-231` lost time to unresolved or stale review-thread state that only became
obvious deep inside the finish loop. The finish workflow should detect and
surface current-head review blockers and outdated-thread cleanup work before it
starts the full review wait, not after the operator has already spent minutes
waiting.

**Files**: `tools/horadus/python/horadus_workflow/task_workflow_finish/`, `tools/horadus/python/horadus_cli/`, `tests/workflow/`

**Acceptance Criteria**:
- [ ] The finish workflow enumerates current-head unresolved review blockers before entering the review wait
- [ ] Outdated review threads that can be auto-resolved are handled up front instead of only after a timeout or head refresh
- [ ] Operator-facing output clearly separates current-head actionable blockers from stale or outdated review artifacts
- [ ] Tests cover current-head unresolved-thread blocking and stale-thread auto-resolution paths

---

### TASK-334: Align Gemini local-review approval-mode flags with installed CLI
**Priority**: P3 (Low)
**Estimate**: <1h

The current Gemini local-review wrapper passes `--approval-mode plan`, but the
installed Gemini CLI warns that this mode requires an experimental flag and
falls back to the default approval mode. Normalize the wrapper to the installed
CLI contract so local-review avoids unnecessary compatibility noise.

**Planning Gates**: Not Required — narrow local-review compatibility follow-up
**Files**: `tools/horadus/python/horadus_workflow/_task_workflow_local_review_provider.py`, `tests/horadus_cli/v2/test_task_local_review.py`

**Acceptance Criteria**:
- [ ] Reproduce the current Gemini approval-mode warning against the installed CLI
- [ ] Update the Gemini local-review wrapper to avoid unsupported approval-mode flags on the installed CLI
- [ ] Keep Claude and Codex local-review provider behavior unchanged

---

### TASK-189: Restrict `/health` and `/metrics` exposure outside development [REQUIRES_HUMAN]
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Reduce unauthenticated reconnaissance risk by restricting detailed health and
metrics endpoints outside development environments, while preserving a minimal
unauthenticated liveness endpoint.

**Assessment-Ref**:
- `artifacts/assessments/security/daily/2026-03-02.md` (`FINDING-2026-03-02-security-public-health-metrics`)

**Dependency Note**:
- Reuse the privileged-route policy from `TASK-200` rather than defining a
  second standalone authorization model for operational endpoints.

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

**Scope Note**:
- The GDELT half is independently actionable now.
- The Telegram half remains bounded by `TASK-080` and the current
  launch-scope exclusion; if that continues to block implementation, split the
  Telegram follow-up into a separate task instead of stalling the GDELT fix.

**Assessment-Ref**:
- User review intake 2026-03-05, Reviewer 3 finding 3

**Files**: `src/ingestion/gdelt_client.py`, `src/ingestion/telegram_harvester.py`, `src/storage/models.py`, `alembic/`, `docs/ARCHITECTURE.md`, `tests/`

**Acceptance Criteria**:
- [ ] Look up or persist GDELT/Telegram sources by stable provider identifier (for example query id / query fingerprint and channel handle) instead of mutable display name
- [ ] Preserve existing watermarks, error counters, and fetch history across harmless config renames
- [ ] Add tests covering rename/no-reset behavior for both collectors

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

**Files**: `tools/horadus/python/horadus_cli/triage_commands.py`, `tools/horadus/python/horadus_workflow/triage.py`, `tools/horadus/python/horadus_workflow/task_repo.py`, `tests/horadus_cli/`, `tests/workflow/`

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

**Files**: `tools/horadus/python/horadus_cli/triage_commands.py`, `tools/horadus/python/horadus_workflow/triage.py`, `tests/horadus_cli/`, `tests/workflow/`

**Acceptance Criteria**:
- [ ] Group recent assessments by role with counts and latest artifact metadata
- [ ] Add an option to bound or summarize assessment lists for agent-oriented JSON output
- [ ] Keep full path enumeration available when explicitly requested
- [ ] Keep text output concise while still indicating assessment coverage
- [ ] Add regression tests for grouped summaries and explicit full-list mode

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
- [ ] Make the coverage view distinguish at least seen, processable, processed, deferred, and skipped-by-language volume so operators can tell "no signal" from "not processed"
- [ ] Persist or export coverage artifacts suitable for operational review and release-gate inputs
- [ ] Expose a read-only API/report path for recent coverage health distinct from collector freshness
- [ ] Add metrics/logs that make sudden coverage drops visible even when collectors remain healthy
- [ ] Add regression coverage for low-coverage and balanced-coverage cases

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
- [ ] Replace catch-all operator actions with a typed, append-only adjudication model that distinguishes review state, override intent, and resulting state effect
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
- [ ] Reserve bounded budget/fairness for late-arriving or lower-volume high-impact items so early noisy traffic cannot consume the entire day
- [ ] Keep the scheduling policy explainable by surfacing the main factors behind Tier-2 prioritization decisions in logs, metrics, or debug responses
- [ ] Preserve current behavior as a safe fallback when value-of-information inputs are unavailable
- [ ] Add regression coverage for high-impact ambiguity-first prioritization, low-value deprioritization, and bounded fairness behavior

---

### TASK-338: Separate Provisional and Canonical Extraction State in Degraded Mode
**Priority**: P1 (High)
**Estimate**: 4-6 hours

Degraded mode correctly holds trend deltas, but event extraction can still
populate user-visible fields while primary-quality Tier-2 behavior is
unavailable. Separate provisional extraction from canonical extraction so
degraded outputs do not silently become the long-lived event/report truth.

**Assessment-Ref**:
- User-provided external architecture evaluation on 2026-03-06

**Files**: `src/storage/models.py`, `src/processing/pipeline_orchestrator.py`, `src/processing/tier2_classifier.py`, `src/core/report_generator.py`, `src/api/routes/events.py`, `src/api/routes/reports.py`, `docs/ARCHITECTURE.md`, `docs/adr/008-degraded-llm-mode.md`, `tests/`, `alembic/`

**Acceptance Criteria**:
- [ ] Persist extraction status that distinguishes provisional degraded-mode output from canonical promoted output
- [ ] Prevent provisional extraction fields from overwriting canonical event summaries/categories or feeding normal report-generation paths without explicit promotion semantics
- [ ] Define how primary-route replay promotes, supersedes, or discards prior provisional extraction so event history remains explainable
- [ ] Expose provisional/canonical status in operator-facing event or report debug responses
- [ ] Add regression coverage for degraded provisional write, post-recovery promotion, and report-path exclusion of provisional-only data

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

The repo now has explicit lifecycle checks, a canonical `local-gate`, and
agent-facing workflow guidance, but the remaining completion contract is still
partly social. Tighten the post-task path around the gaps that are not already
mechanically enforced: required validation selection, docs update expectations,
and explicit N/A handling when a task legitimately skips a normal gate.

**Files**: `AGENTS.md`, `Makefile`, `scripts/finish_task_pr.sh`, `tools/horadus/python/horadus_cli/`, `tools/horadus/python/horadus_workflow/`, `docs/AGENT_RUNBOOK.md`, `tests/unit/`, `tests/workflow/`

**Acceptance Criteria**:
- [ ] The remaining implicit completion rules are enumerated explicitly, separating already-enforced requirements from still-social expectations
- [ ] Task-finish guidance or tooling requires relevant tests for code changes unless a documented N/A condition applies
- [ ] Task-finish guidance or tooling keeps `horadus tasks local-gate --full` as the canonical post-task local gate without reintroducing duplicate gate commands
- [ ] Task-finish guidance or tooling explicitly requires the local integration gate where the task touches integration-covered paths or push/PR workflow requires it
- [ ] Task-finish guidance or tooling calls out documentation updates when behavior, workflow, or operator-facing contracts changed
- [ ] `horadus tasks context-pack` suggested validation commands stay aligned with the effective completion contract when that contract changes
- [ ] Tests cover the intended pass path plus at least one documented N/A or blocker path so the contract does not regress back into implicit policy

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

### TASK-288: Convert RFC-001 Context Retrieval Plan Into Approved Implementation Queue [REQUIRES_HUMAN]
**Priority**: P1 (High)
**Estimate**: 1-2 hours
**Spec**: `tasks/specs/288-rfc-001-implementation-breakdown.md`

Convert `docs/rfc/001-agent-context-retrieval.md` into an approved set of
implementation tasks with clear sequencing, but require explicit human review
before finalizing that execution queue. This task is human-gated because it
decides how the RFC becomes actual repo work and may change scope boundaries,
priorities, and rollout order.

**Files**: `tasks/BACKLOG.md`, `tasks/CURRENT_SPRINT.md`, `tasks/specs/288-rfc-001-implementation-breakdown.md`, `docs/rfc/001-agent-context-retrieval.md`

**Acceptance Criteria**:
- [ ] RFC-001 is decomposed into concrete implementation-task candidates with clear scope boundaries
- [ ] The proposed breakdown identifies any human decisions needed for sequencing or scope cuts
- [ ] The task stops for human review/approval before finalizing the follow-up execution queue

---

## Future Ideas (Not Scheduled)

- [ ] Archive `tasks/specs/` or `tasks/exec_plans/` only if Sprint 4 still shows measurable context pressure after the live-ledger reset.
