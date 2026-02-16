# Potential Issues & Technical Debt

**Last Updated**: 2026-02-16
**Status**: Archived historical snapshot (superseded)

> This document is retained for historical context from early scaffolding.
> Many items below are resolved. Use `tasks/CURRENT_SPRINT.md`,
> `tasks/BACKLOG.md`, and `PROJECT_STATUS.md` as the authoritative current
> status/risk trackers.

This document tracks identified issues, vulnerabilities, and technical debt that require attention before production readiness.

---

## How To Read This

- **Risk items** are things that can cause security incidents, data corruption, or runaway cost once the system is exposed or running continuously.
- **Roadmap gaps** are expected “not built yet” items; they should be tracked primarily in `tasks/` rather than treated as defects.
- Severity is assessed **at the point of non-local deployment** (anything beyond localhost / private dev use).

---

## Summary (Current Snapshot)

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| Security | 1 | 2 | 1 | 0 | 4 |
| Implementation Gap | 0 | 4 | 1 | 0 | 5 |
| Architecture | 0 | 2 | 2 | 0 | 4 |
| Code Quality | 0 | 0 | 2 | 2 | 4 |
| Documentation | 0 | 0 | 0 | 2 | 2 |
| **Total** | **1** | **8** | **6** | **4** | **19** |

---

## Deployment-Critical Risks (Before Any Non-Local Exposure)

These should be addressed before exposing the API publicly or running ingestion/processing continuously.

| ID | Area | Severity | Track |
|----|------|----------|-------|
| SEC-001 | SECRET_KEY handling | Critical | `tasks/BACKLOG.md` → `TASK-025` |
| SEC-002 | API authentication/authorization | High | `tasks/BACKLOG.md` → `TASK-025` |
| IMPL-004 | Cost protection enforcement | High | `tasks/BACKLOG.md` → `TASK-036` |
| ARCH-002 | Transaction boundaries (auto-commit) | Medium | `tasks/CURRENT_SPRINT.md` → `TASK-004` |

---

## Security

### SEC-001: Weak Default SECRET_KEY
**Severity**: CRITICAL
**File**: `src/core/config.py` (`Settings.SECRET_KEY`)
**Status**: Open
**Track**: `tasks/BACKLOG.md` → `TASK-025`

```python
SECRET_KEY: str = Field(
    default="dev-secret-key-change-in-production",
    ...
)
```

**Risk**: If used for signing (tokens/cookies/etc) and deployed without override, signatures become guessable.

**Remediation**:
- Prefer: make required in production (fail fast), keep a dev-only default for local usage.
- Alternative: generate a cryptographically secure ephemeral key on startup with a loud warning (breaks restarts).

---

### SEC-002: No API Authentication/Authorization
**Severity**: HIGH
**Files**: `src/api/routes/*.py`
**Status**: Open
**Track**: `tasks/BACKLOG.md` → `TASK-025`

All API endpoints have no authentication checks. The `API_KEY` setting in config (`src/core/config.py`) is defined but never enforced.

**Affected Endpoints**:
- `POST /api/v1/sources` - creates sources
- `PATCH /api/v1/sources/{id}` - modifies sources
- `DELETE /api/v1/sources/{id}` - deletes sources
- All read endpoints (trends, events, reports)

**Risk**: Anyone with network access can read all data and modify source configurations.

**Remediation**:
- Implement API key middleware in `src/api/deps.py`
- Add `Depends(verify_api_key)` to protected routes

---

### SEC-003: CORS Origins Hardcoded for Development
**Severity**: MEDIUM
**File**: `src/core/config.py` (`Settings.CORS_ORIGINS`)
**Track**: `tasks/BACKLOG.md` → `TASK-027`

```python
CORS_ORIGINS: list[str] = Field(
    default=["http://localhost:3000", "http://localhost:8080"],
    ...
)
```

**Risk**: Low immediate risk (localhost only), but pattern encourages forgetting to configure in production.

**Remediation**:
- Document CORS configuration requirement in deployment guide
- Consider requiring explicit configuration in production environment

---

### SEC-004: SQL Echo Enabled in Development Mode
**Severity**: HIGH
**File**: `src/storage/database.py` (`create_engine`)
**Track**: `tasks/CURRENT_SPRINT.md` → `TASK-004`

```python
if settings.is_development:
    return create_async_engine(
        settings.DATABASE_URL,
        echo=True,  # Logs all SQL
        ...
    )
```

**Risk**: If `ENVIRONMENT` misconfigured, production logs may contain sensitive query data.

**Remediation**:
- Add explicit `SQL_ECHO` setting defaulting to `False`
- Only enable echo when both `is_development=True` AND explicit opt-in

---

## Roadmap Gaps (Expected “Not Implemented Yet”)

These are expected given the current phase; track progress in `tasks/` rather than treating them as defects.

### IMPL-001: Empty Ingestion Layer
**Severity**: HIGH
**File**: `src/ingestion/__init__.py`
**Status**: Expected (Phase 1 work)
**Track**: `tasks/BACKLOG.md` → `TASK-006`, `TASK-007`, `TASK-009`

Directory exists but contains no collectors. Per architecture:
- `RSSCollector` - not implemented
- `GDELTClient` - not implemented
- `TelegramHarvester` - not implemented

**Blocked By**: Phase 0 completion (Docker, migrations, API skeleton)

---

### IMPL-002: Empty Processing Layer
**Severity**: HIGH
**File**: `src/processing/__init__.py`
**Status**: Expected (Phase 2 work)
**Track**: `tasks/BACKLOG.md` → `TASK-010` .. `TASK-015`

Directory exists but contains no processors:
- `Tier1Filter` - not implemented
- `Tier2Classifier` - not implemented
- `EmbeddingService` - not implemented
- `EventClusterer` - not implemented
- `Deduplicator` - not implemented

**Blocked By**: Phase 1 completion

---

### IMPL-003: Empty Workers Layer
**Severity**: HIGH
**File**: `src/workers/__init__.py`
**Status**: Expected (Phase 1-2 work)
**Track**: `tasks/BACKLOG.md` → `TASK-008`, `TASK-015`, `TASK-020` .. `TASK-023`

No Celery task definitions exist:
- `collect_rss` - not implemented
- `process_item` - not implemented
- `generate_report` - not implemented
- `snapshot_trends` - not implemented
- `apply_decay` - not implemented

**Blocked By**: Ingestion and processing layers

---

### IMPL-004: Cost Protection Not Implemented
**Severity**: HIGH
**File**: `src/core/config.py` (budget settings)
**Related Task**: TASK-036
**Track**: `tasks/BACKLOG.md` → `TASK-036`

Config defines budget limits but they're never enforced:

```python
TIER1_MAX_DAILY_CALLS: int = Field(default=1000, ...)
TIER2_MAX_DAILY_CALLS: int = Field(default=200, ...)
DAILY_COST_LIMIT_USD: float = Field(default=5.0, ...)
```

**Risk**: Ingestion spikes (breaking news) could cause uncontrolled LLM spending.

**Remediation**:
- Implement call counter (Redis-backed)
- Add pre-call budget check in LLM wrapper
- Implement kill switch mechanism

---

### IMPL-005: Redis Health Check Inefficient
**Severity**: MEDIUM
**File**: `src/api/routes/health.py` (`check_redis`)
**Track**: `tasks/BACKLOG.md` → `TASK-026`

```python
async def check_redis() -> dict[str, Any]:
    client = redis.from_url(settings.REDIS_URL)  # New connection each time
    await client.ping()
    await client.close()
```

**Impact**: Unnecessary connection overhead on every health check.

**Remediation**:
- Use shared Redis connection pool
- Inject pool via dependency

---

## Architecture / Correctness Risks

### ARCH-001: All API Routes Return 501
**Severity**: HIGH
**Files**:
- `src/api/routes/trends.py` (4 endpoints)
- `src/api/routes/events.py` (2 endpoints)
- `src/api/routes/sources.py` (5 endpoints)
- `src/api/routes/reports.py` (3 endpoints)

All 14 endpoints raise `HTTPException(501, "Not yet implemented")` (expected while scaffolding).

**Track**: `tasks/CURRENT_SPRINT.md` → `TASK-004` (plus subsequent `TASK-005`, `TASK-016`, etc.)

---

### ARCH-002: Database Session Always Commits
**Severity**: MEDIUM
**File**: `src/storage/database.py` (`get_session`)
**Track**: `tasks/CURRENT_SPRINT.md` → `TASK-004`

```python
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()  # Always commits
        except Exception:
            await session.rollback()
            raise
```

**Issue**: Routes cannot implement business-logic rollbacks.

**Remediation**:
- Let routes control commit explicitly
- Or use unit-of-work pattern with explicit commit call

---

### ARCH-003: Trend YAML Fields Not Stored in Model
**Severity**: MEDIUM
**Files**:
- `config/trends/eu-russia.yaml` (lines 23-55)
- `src/storage/models.py` (Trend model)

YAML includes fields not persisted to database:
- `disqualifiers` - conditions that would falsify the trend
- `falsification_criteria` - specific falsifying events
- `type` per indicator - not preserved in JSONB

**Impact**: Critical metadata for model evaluation is lost.

**Remediation**:
- Store full YAML as `definition` JSONB (current approach)
- Ensure trend engine reads these fields from `definition`

---

### ARCH-004: Missing Initial Alembic Migration & DB-Specific Setup
**Severity**: HIGH
**Status**: Open
**Track**: `tasks/CURRENT_SPRINT.md` → `TASK-003`

Still missing:
- Initial migration script under `alembic/versions/`
- pgvector extension enable in migration (or ensured via init SQL + verified in migration expectations)
- TimescaleDB hypertable setup for `trend_snapshots`

**Tracked By**: TASK-003

---

## Code Quality

### QUAL-001: Missing Type Annotations
**Severity**: LOW
**File**: `src/core/trend_engine.py` (`TrendUpdate.direction`, `get_direction`)
**Track**: Opportunistic (no dedicated task)

```python
@dataclass
class TrendUpdate:
    direction: str  # Should be Literal["up", "down", "unchanged"]
```

Similarly `get_direction()` return type at line 632.

**Remediation**: Use `Literal` or `StrEnum` for direction values

---

### QUAL-002: No LLM Call Logging/Tracking
**Severity**: MEDIUM
**Status**: Open
**Track**: `tasks/BACKLOG.md` → `TASK-036` and `TASK-026`

No implementation exists to:
- Count LLM calls per tier
- Track cost per call
- Log usage for billing reconciliation
- Alert when approaching budget threshold

**Related To**: IMPL-004 (Cost Protection)

---

### QUAL-003: Trend Definition Not Validated on Load
**Severity**: MEDIUM
**File**: `src/core/trend_engine.py` (`apply_decay` baseline_probability read)
**Track**: `tasks/BACKLOG.md` → `TASK-029` (Enhanced Trend Definitions)

```python
baseline_prob = trend.definition.get(
    "baseline_probability",
    DEFAULT_BASELINE_PROBABILITY,
)
```

If `baseline_probability` is malformed (string, negative, >1), code silently uses default.

**Remediation**:
- Create Pydantic model for TrendDefinition
- Validate on trend load/creation

---

### QUAL-004: Test Coverage Gaps
**Severity**: LOW
**Status**: Expected (routes are stubs)

No tests for:
- `src/api/routes/*.py` - all stubs
- `src/storage/database.py` - no integration tests
- `src/api/main.py` - no tests

**Note**: `tests/unit/core/test_trend_engine.py` has strong coverage for the probability engine (39 tests currently).

---

## Documentation

### DOC-001: ADR-004 Missing
**Severity**: LOW
**File**: `docs/adr/` directory
**Track**: Documentation hygiene (no dedicated task)

ARCHITECTURE.md references "ADR-004: Events > Articles" decision.

**Status**: Resolved
**Resolution**: Added `docs/adr/004-events-over-articles.md`

---

### DOC-002: Development Workflow Incomplete
**Severity**: LOW
**File**: `AGENTS.md`
**Track**: Documentation hygiene (no dedicated task)

Documented commands assume infrastructure exists:
- `pytest tests/` - works if your venv is active; otherwise use `.venv/bin/python -m pytest`
- `uvicorn src.api.main:app` - works but routes return 501 (use `.venv/bin/uvicorn` or `make run`)
- `alembic upgrade head` - configured, but will fail until `TASK-003` creates an initial migration and DB is running
- `docker-compose up` - works once Docker is installed and running

**Blocked By**: TASK-002, TASK-003

---

## Priority Matrix

### Immediate (Before Any Deployment)
1. SEC-001: Fix SECRET_KEY default
2. SEC-002: Implement API authentication
3. ARCH-004: Complete Alembic setup

### Before Phase 1
1. IMPL-004: Implement cost protection
2. ARCH-001: Wire up basic read endpoints
3. QUAL-003: Add trend definition validation

### Before Production
1. SEC-003: Document CORS configuration
2. SEC-004: Fix SQL echo behavior
3. IMPL-005: Fix Redis health check
4. ARCH-002: Review session commit behavior

### Backlog (Quality Improvements)
1. QUAL-001: Add type annotations
2. QUAL-002: Implement LLM call tracking
3. DOC-001: Create ADR-004
4. DOC-002: Update workflow docs

---

## Resolved Issues

| ID | Description | Resolution Date | Notes |
|----|-------------|-----------------|-------|
| - | `datetime.utcnow()` deprecated | 2026-01-04 | Replaced with `datetime.now(UTC)` |
| - | Race condition in `apply_evidence()` | 2026-01-04 | Added idempotency checks |
| - | Evidence factor mapping incorrect | 2026-01-04 | Fixed `severity_score` assignment |
| - | `.env.example` inconsistent with config | 2026-01-04 | Aligned variable names |
| - | ADR-005 missing | 2026-01-04 | Created two-tier LLM ADR |
| - | Indicator weight validation missing | 2026-01-04 | Added in `seed_trends.py` |
