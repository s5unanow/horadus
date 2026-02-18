# Data Model

## Entity Relationship Diagram

This ERD is a core-table orientation view, not an exhaustive per-column schema reference.
Use the table definitions below as the runtime-authoritative column inventory.

```
┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
│     sources     │          │    raw_items    │          │     events      │
├─────────────────┤          ├─────────────────┤          ├─────────────────┤
│ id (PK)         │◄────────┐│ id (PK)         │     ┌───▶│ id (PK)         │
│ type            │         ││ source_id (FK)  │─────┘    │ canonical_summ. │
│ name            │         │└─────────────────┤          │ embedding       │
│ url             │         │  external_id     │          │ extracted_*     │
│ credibility     │         │  url             │          │ categories[]    │
│ config (JSON)   │         │  title           │          │ source_count    │
│ is_active       │         │  published_at    │          │ first_seen_at   │
│ last_fetched_at │         │  raw_content     │          │ primary_item_id │
│ created_at      │         │  content_hash    │          │ created_at      │
│ updated_at      │         │  processing_stat │          └────────┬────────┘
└─────────────────┘         │  created_at      │                   │
                            └──────────┬───────┘                   │
                                       │                           │
                                       │      ┌────────────────────┘
                                       │      │
                                       ▼      ▼
                            ┌─────────────────────┐
                            │    event_items      │
                            ├─────────────────────┤
                            │ event_id (PK, FK)   │
                            │ item_id (PK, FK)    │
                            │ added_at            │
                            └─────────────────────┘


┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
│     trends      │          │ trend_evidence  │          │ trend_snapshots │
├─────────────────┤          ├─────────────────┤          ├─────────────────┤
│ id (PK)         │◄────────┐│ id (PK)         │          │ trend_id (PK,FK)│
│ name            │         ││ trend_id (FK)   │─────────▶│ timestamp (PK)  │
│ description     │         ││ event_id (FK)   │          │ log_odds        │
│ definition      │         │├─────────────────┤          │ event_count_24h │
│ baseline_lo     │         ││ signal_type     │          └─────────────────┘
│ current_lo      │         ││ credibility     │               TimescaleDB
│ indicators      │         ││ corroboration   │               Hypertable
│ decay_half_life │         ││ novelty         │
│ is_active       │         ││ severity        │
│ created_at      │         ││ delta_log_odds  │
│ updated_at      │         ││ reasoning       │
└─────────────────┘         ││ created_at      │
                            │└─────────────────┘
                            │         │
                            │         ▼
                            │  ┌─────────────────┐
                            └──│     events      │
                               └─────────────────┘
```

## Table Definitions

### sources

Stores configuration for data sources (RSS feeds, Telegram channels, etc.)

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| type | VARCHAR(50) | No | | Source type: rss, telegram, gdelt, api |
| name | VARCHAR(255) | No | | Human-readable name |
| url | TEXT | Yes | | Source URL (for RSS/API) |
| credibility_score | DECIMAL(3,2) | No | 0.50 | Reliability score (0.00-1.00) |
| source_tier | VARCHAR(20) | No | 'regional' | Source tier: primary, wire, major, regional, aggregator |
| reporting_type | VARCHAR(20) | No | 'secondary' | Reporting type: firsthand, secondary, aggregator |
| config | JSONB | No | {} | Source-specific configuration |
| is_active | BOOLEAN | No | true | Whether to collect from this source |
| last_fetched_at | TIMESTAMPTZ | Yes | | Last successful fetch time |
| ingestion_window_end_at | TIMESTAMPTZ | Yes | | Per-source ingestion high-water timestamp for overlap-aware next windows |
| error_count | INTEGER | No | 0 | Consecutive collection error count |
| last_error | TEXT | Yes | | Most recent collection error message |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |
| updated_at | TIMESTAMPTZ | No | NOW() | Last update time |

**Indexes:**
- Primary key: `id`
- Index: `is_active`
- Index: `type`
- Index: `source_tier`
- Index: `ingestion_window_end_at`

**Example config values:**
```json
// RSS
{"check_interval_minutes": 30, "max_articles_per_fetch": 50}

// Telegram
{"channel_id": -1001234567890, "include_media": false}

// GDELT
{"themes": ["TAX_FNCACT", "MILITARY"], "countries": ["RS", "UA"]}
```

---

### raw_items

Individual articles/posts collected from sources.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| source_id | UUID | No | | Foreign key to sources |
| external_id | VARCHAR(2048) | No | | Original ID (URL for RSS, message_id for Telegram) |
| url | TEXT | Yes | | Full article URL |
| title | TEXT | Yes | | Article title |
| author | VARCHAR(255) | Yes | | Source author/byline when available |
| published_at | TIMESTAMPTZ | Yes | | Original publication time |
| fetched_at | TIMESTAMPTZ | No | NOW() | When we fetched it |
| raw_content | TEXT | No | | Extracted text content |
| embedding | vector(1536) | Yes | | Text embedding for similarity and clustering |
| embedding_model | VARCHAR(255) | Yes | | Model identifier for current embedding vector |
| embedding_generated_at | TIMESTAMPTZ | Yes | | Timestamp when current embedding vector was generated |
| embedding_input_tokens | INTEGER | Yes | | Approximate token count before embedding input guardrail policy |
| embedding_retained_tokens | INTEGER | Yes | | Approximate token count retained after guardrail handling |
| embedding_was_truncated | BOOLEAN | No | false | True when truncate policy dropped tail tokens for this embedding |
| embedding_truncation_strategy | VARCHAR(20) | Yes | | Guardrail strategy used when input exceeded limit (`truncate`/`chunk`) |
| content_hash | VARCHAR(64) | No | | SHA256 hash for dedup |
| language | VARCHAR(10) | Yes | | Detected language (ISO 639-1) |
| processing_status | VARCHAR(20) | No | 'pending' | Status: pending, processing, classified, noise, error |
| processing_started_at | TIMESTAMPTZ | Yes | | Timestamp when item entered `processing` (used by stale-item reaper) |
| error_message | TEXT | Yes | | Error details if status=error |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |

**Indexes:**
- Primary key: `id`
- Unique: `(source_id, external_id)`
- Index: `processing_status`
- Index: `processing_started_at`
- Index: `content_hash`
- Index: `fetched_at DESC`
- IVFFlat: `embedding` (vector_cosine_ops, lists=64)

Strategy note:
- Default ANN profile is IVFFlat (`lists=64`) for current small-table regime.
- Re-run strategy selection with `horadus eval vector-benchmark` before changing index type/params.
- Follow `docs/VECTOR_REVALIDATION.md` for cadence triggers, promotion criteria, and operator checklist.
- Similarity comparisons are performed only for matching `embedding_model` values.

**Processing status flow:**
```
pending → processing → classified
                    → noise
                    → error
processing (stale timeout) → pending
```

---

### events

Clustered news events (multiple raw_items about the same story).

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| canonical_summary | TEXT | No | | Canonical summary of the current `primary_item_id` (most credible item), not simply the latest mention |
| embedding | vector(1536) | Yes | | Text embedding for similarity |
| embedding_model | VARCHAR(255) | Yes | | Model identifier for current embedding vector |
| embedding_generated_at | TIMESTAMPTZ | Yes | | Timestamp when current embedding vector was generated |
| embedding_input_tokens | INTEGER | Yes | | Approximate token count before embedding input guardrail policy |
| embedding_retained_tokens | INTEGER | Yes | | Approximate token count retained after guardrail handling |
| embedding_was_truncated | BOOLEAN | No | false | True when truncate policy dropped tail tokens for this embedding |
| embedding_truncation_strategy | VARCHAR(20) | Yes | | Guardrail strategy used when input exceeded limit (`truncate`/`chunk`) |
| extracted_who | TEXT[] | Yes | | Entities: people/organizations |
| extracted_what | TEXT | Yes | | What happened |
| extracted_where | TEXT | Yes | | Location |
| extracted_when | TIMESTAMPTZ | Yes | | When it happened |
| extracted_claims | JSONB | Yes | | Structured claims + normalized claim graph (`nodes`/`links`) |
| categories | TEXT[] | Yes | | Classification categories |
| source_count | INTEGER | No | 1 | Number of sources reporting this |
| unique_source_count | INTEGER | No | 1 | Number of distinct sources represented in the event |
| lifecycle_status | VARCHAR(20) | No | 'emerging' | Event lifecycle state: emerging, confirmed, fading, archived |
| first_seen_at | TIMESTAMPTZ | No | NOW() | First time we saw this event |
| last_mention_at | TIMESTAMPTZ | No | NOW() | Most recent mention timestamp used for lifecycle transitions |
| last_updated_at | TIMESTAMPTZ | No | NOW() | Last time event was updated |
| confirmed_at | TIMESTAMPTZ | Yes | | Timestamp when event reached confirmed lifecycle threshold |
| primary_item_id | UUID | Yes | | Most credible source item |
| has_contradictions | BOOLEAN | No | false | Whether contradictory claims were detected across linked items |
| contradiction_notes | TEXT | Yes | | Optional contradiction analysis notes |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |

**Indexes:**
- Primary key: `id`
- IVFFlat: `embedding` (vector_cosine_ops, lists=64)
- GIN: `categories`
- Index: `first_seen_at DESC`
- Index: `(lifecycle_status, last_mention_at)`

**Vector search example:**
```sql
-- Find similar events (cosine similarity > 0.88)
SELECT id, canonical_summary,
       1 - (embedding <=> $1) as similarity
FROM events
WHERE first_seen_at > NOW() - INTERVAL '48 hours'
  AND embedding <=> $1 < 0.12  -- 1 - 0.88 = 0.12
ORDER BY embedding <=> $1
LIMIT 5;
```

Operational note:
- Use `uv run horadus eval embedding-lineage` to detect mixed model populations and estimate re-embed scope.
- Follow `docs/EMBEDDING_MODEL_UPGRADE.md` for cutover/backfill/rollback workflow.

---

### event_items

Junction table linking events to their source items.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| event_id | UUID | No | | Foreign key to events |
| item_id | UUID | No | | Foreign key to raw_items |
| added_at | TIMESTAMPTZ | No | NOW() | When item was added to event |

**Indexes:**
- Primary key: `(event_id, item_id)`
- Unique: `item_id` (enforces one RawItem belongs to exactly one Event)
- Foreign keys cascade on delete

---

### trends

Trend definitions and current probability state.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| name | VARCHAR(255) | No | | Unique trend name |
| description | TEXT | Yes | | Human-readable description |
| definition | JSONB | No | | Full trend configuration |
| baseline_log_odds | DECIMAL(10,6) | No | | Prior probability (log-odds) |
| current_log_odds | DECIMAL(10,6) | No | | Current probability (log-odds) |
| indicators | JSONB | No | | Signal types and weights |
| decay_half_life_days | INTEGER | No | 30 | Days for probability to decay 50% |
| is_active | BOOLEAN | No | true | Whether trend is being tracked |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |
| updated_at | TIMESTAMPTZ | No | NOW() | Last update time |

**Indexes:**
- Primary key: `id`
- Unique: `name`

**Probability conversion:**
```python
import math

def logodds_to_prob(lo: float) -> float:
    return 1.0 / (1.0 + math.exp(-lo))

def prob_to_logodds(p: float) -> float:
    return math.log(p / (1.0 - p))

# Example: 8% baseline
baseline_prob = 0.08
baseline_log_odds = prob_to_logodds(0.08)  # -2.44
```

**Baseline source-of-truth note:**
- Canonical decay baseline is `trends.baseline_log_odds`.
- `trends.definition.baseline_probability` is synchronized metadata for operator visibility and config parity.

**Example indicators:**
```json
{
  "military_movement": {
    "weight": 0.04,
    "direction": "escalatory",
    "keywords": ["troops", "deployment", "mobilization"]
  },
  "de_escalation": {
    "weight": 0.03,
    "direction": "de_escalatory",
    "keywords": ["talks", "ceasefire", "agreement"]
  }
}
```

---

### trend_definition_versions

Append-only history of trend definition payloads for auditability.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| trend_id | UUID | No | | FK to `trends` (`CASCADE` on delete) |
| definition_hash | VARCHAR(64) | No | | SHA256 hash of canonicalized definition JSON |
| definition | JSONB | No | | Full definition payload captured at write time |
| actor | VARCHAR(255) | Yes | | Actor identity or channel (`api`, `system`, etc.) |
| context | VARCHAR(255) | Yes | | Write context (`create_trend`, `update_trend`, `config_sync:<file>`) |
| recorded_at | TIMESTAMPTZ | No | NOW() | Timestamp version row was recorded |

**Indexes:**
- Primary key: `id`
- Index: `(trend_id, recorded_at DESC)`
- Index: `definition_hash`

**Inspection paths:**
- API: `GET /api/v1/trends/{trend_id}/definition-history?limit=100`
- SQL:
  ```sql
  SELECT recorded_at, actor, context, definition_hash
  FROM trend_definition_versions
  WHERE trend_id = $1
  ORDER BY recorded_at DESC
  LIMIT 100;
  ```

---

### trend_evidence

Audit trail of all probability updates.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| trend_id | UUID | No | | Foreign key to trends |
| event_id | UUID | No | | Foreign key to events |
| signal_type | VARCHAR(100) | No | | Type of signal detected |
| credibility_score | DECIMAL(3,2) | Yes | | Source credibility (0.00-1.00) |
| corroboration_factor | DECIMAL(5,2) | Yes | | sqrt(effective_independent_corroboration)/3 |
| novelty_score | DECIMAL(3,2) | Yes | | Continuous recency-aware novelty (0.30-1.00) |
| evidence_age_days | DECIMAL(6,2) | Yes | | Event age in days at scoring time |
| temporal_decay_factor | DECIMAL(5,4) | Yes | | Indicator temporal decay multiplier |
| severity_score | DECIMAL(3,2) | Yes | | Event severity |
| confidence_score | DECIMAL(3,2) | Yes | | LLM confidence |
| delta_log_odds | DECIMAL(10,6) | No | | Probability change |
| reasoning | TEXT | Yes | | LLM explanation |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |
| is_invalidated | BOOLEAN | No | FALSE | Whether this evidence row was invalidated by human feedback |
| invalidated_at | TIMESTAMPTZ | Yes | | Timestamp when invalidation was recorded |
| invalidation_feedback_id | UUID | Yes | | Optional FK to `human_feedback.id` that performed invalidation |

**Indexes:**
- Primary key: `id`
- Unique: `(trend_id, event_id, signal_type)`
- Index: `(trend_id, created_at DESC)`
- Index: `event_id`
- Index: `(event_id, is_invalidated)`

**Invalidation lineage semantics:**
- Event invalidation no longer deletes evidence rows.
- Instead, evidence is marked `is_invalidated=true` and linked to the originating `human_feedback` record.
- Operational analytics/reporting queries use only active (`is_invalidated=false`) evidence by default.
- Audit/replay paths can include invalidated lineage explicitly when needed.

**Delta calculation:**
```
delta = weight × credibility × corroboration × novelty × temporal_decay × direction × severity × confidence

where:
  corroboration = sqrt(effective_independent_corroboration_score) / 3
  effective_independent_corroboration_score = sum(independent source-cluster weights) × contradiction_penalty
  contradiction_penalty = 1.0 normally, reduced when claim-graph contradiction links exist
  novelty = recency-aware continuous score for prior (trend_id, signal_type) evidence
  temporal_decay = 0.5^(evidence_age_days / decay_half_life_days)
  direction = +1 (escalatory) or -1 (de_escalatory)
```

---

### taxonomy_gaps

Runtime triage queue for skipped Tier-2 trend impacts caused by taxonomy mismatch.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| event_id | UUID | Yes | | Optional FK to `events` (`SET NULL` on delete) |
| trend_id | VARCHAR(255) | No | | Trend identifier emitted by Tier-2 payload |
| signal_type | VARCHAR(255) | No | | Indicator key emitted by Tier-2 payload |
| reason | ENUM | No | | `unknown_trend_id` or `unknown_signal_type` |
| source | VARCHAR(50) | No | `pipeline` | Runtime source that recorded the gap |
| details | JSONB | No | `{}` | Structured context (`direction`, `severity`, `confidence`, etc.) |
| status | ENUM | No | `open` | Analyst triage status (`open`, `resolved`, `rejected`) |
| resolution_notes | TEXT | Yes | | Analyst notes for resolution decision |
| resolved_by | VARCHAR(255) | Yes | | Reviewer identity |
| resolved_at | TIMESTAMPTZ | Yes | | Resolution timestamp |
| observed_at | TIMESTAMPTZ | No | NOW() | First capture timestamp |

**Indexes:**
- Primary key: `id`
- Index: `observed_at DESC`
- Index: `(status, observed_at DESC)`
- Index: `reason`
- Index: `(trend_id, signal_type)`

**Operational intent:**
- Unknown taxonomy impacts are never scored into trend deltas.
- Every skipped impact is persisted here for analyst triage and closure tracking.
- API triage path: `GET /api/v1/taxonomy-gaps`, `PATCH /api/v1/taxonomy-gaps/{id}`.

---

### trend_snapshots

Time-series of trend probabilities (TimescaleDB hypertable).

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| trend_id | UUID | No | | Foreign key to trends |
| timestamp | TIMESTAMPTZ | No | | Snapshot time |
| log_odds | DECIMAL(10,6) | No | | Probability at this time |
| event_count_24h | INTEGER | Yes | | Events affecting trend in last 24h |

**Indexes:**
- Primary key: `(trend_id, timestamp)`
- TimescaleDB hypertable on `timestamp`

**Time-series queries:**
```sql
-- Get trend history for last 30 days
SELECT
    timestamp,
    1.0 / (1.0 + exp(-log_odds)) as probability
FROM trend_snapshots
WHERE trend_id = $1
  AND timestamp > NOW() - INTERVAL '30 days'
ORDER BY timestamp;

-- Get daily average (TimescaleDB)
SELECT
    time_bucket('1 day', timestamp) as day,
    AVG(1.0 / (1.0 + exp(-log_odds))) as avg_probability
FROM trend_snapshots
WHERE trend_id = $1
  AND timestamp > NOW() - INTERVAL '90 days'
GROUP BY day
ORDER BY day;
```

---

### reports

Generated intelligence reports (weekly/monthly/retrospective).

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| report_type | VARCHAR(50) | No | | Report type (`weekly`, `monthly`, `retrospective`) |
| period_start | TIMESTAMPTZ | No | | Report period start |
| period_end | TIMESTAMPTZ | No | | Report period end |
| trend_id | UUID | Yes | | Optional FK to `trends` (trend-specific reports) |
| statistics | JSONB | No | | Deterministic report stats payload |
| narrative | TEXT | Yes | | Generated narrative |
| grounding_status | VARCHAR(20) | No | `not_checked` | Grounding validation status |
| grounding_violation_count | INTEGER | No | `0` | Number of grounding violations |
| grounding_references | JSONB | Yes | | Grounding evidence metadata |
| top_events | JSONB | Yes | | Top contributing events |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |

**Indexes:**
- Primary key: `id`
- Index: `(report_type, period_end)`
- Index: `trend_id`

---

### api_usage

Daily usage counters for budget enforcement.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| date | DATE | No | | Usage day (mapped from `usage_date` in SQLAlchemy model) |
| tier | VARCHAR(20) | No | | LLM tier (`embedding`, `tier1`, `tier2`, `reporting`) |
| call_count | INTEGER | No | `0` | API calls for the day/tier |
| input_tokens | INTEGER | No | `0` | Input token count |
| output_tokens | INTEGER | No | `0` | Output token count |
| estimated_cost_usd | DECIMAL(10,4) | No | `0` | Estimated USD spend |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |
| updated_at | TIMESTAMPTZ | No | NOW() | Last update time |

**Indexes/Constraints:**
- Primary key: `id`
- Unique: `(date, tier)`
- Index: `date`

---

### trend_outcomes

Resolved outcomes for calibration scoring (prediction vs reality).

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| trend_id | UUID | No | | FK to `trends` |
| prediction_date | TIMESTAMPTZ | No | | Timestamp of recorded prediction |
| predicted_probability | DECIMAL(5,4) | No | | Probability at prediction time |
| predicted_risk_level | VARCHAR(20) | No | | Risk label at prediction time |
| probability_band_low | DECIMAL(5,4) | No | | Lower confidence band |
| probability_band_high | DECIMAL(5,4) | No | | Upper confidence band |
| outcome_date | TIMESTAMPTZ | Yes | | Resolution timestamp |
| outcome | VARCHAR(20) | Yes | | Outcome classification |
| outcome_notes | TEXT | Yes | | Analyst notes |
| outcome_evidence | JSONB | Yes | | Supporting resolution evidence |
| brier_score | DECIMAL(10,6) | Yes | | Calibration error value |
| recorded_by | VARCHAR(100) | Yes | | Operator identifier |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |
| updated_at | TIMESTAMPTZ | No | NOW() | Last update time |

**Indexes:**
- Primary key: `id`
- Index: `(trend_id, prediction_date)`
- Index: `outcome`

---

### human_feedback

Manual corrections/annotations used for governance and evaluation.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| target_type | VARCHAR(50) | No | | Annotation target type (`event`, `trend_evidence`, `classification`) |
| target_id | UUID | No | | Target entity ID |
| action | VARCHAR(50) | No | | Feedback action (`pin`, `mark_noise`, `override_delta`, `correct_category`) |
| original_value | JSONB | Yes | | Original value snapshot |
| corrected_value | JSONB | Yes | | Corrected value payload |
| notes | TEXT | Yes | | Analyst explanation |
| created_by | VARCHAR(100) | Yes | | Reviewer/analyst identifier |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |

**Indexes:**
- Primary key: `id`
- Index: `(target_type, target_id)`
- Index: `action`

---

## Model Verification Notes (2026-02-17)

The sections above were cross-checked against SQLAlchemy runtime model declarations:

- `trend_definition_versions` table: `src/storage/models.py:593`
- `reports` table: `src/storage/models.py:660`
- `api_usage` table: `src/storage/models.py:719`
- `trend_outcomes` table: `src/storage/models.py:791`
- `human_feedback` table: `src/storage/models.py:866`

---

## Common Queries

### Get all trends with current probability

```sql
SELECT
    id,
    name,
    1.0 / (1.0 + exp(-current_log_odds)) as probability,
    updated_at
FROM trends
WHERE is_active = true
ORDER BY probability DESC;
```

### Get recent events for a category

```sql
SELECT
    e.id,
    e.canonical_summary,
    e.source_count,
    e.first_seen_at
FROM events e
WHERE 'military' = ANY(e.categories)
  AND e.first_seen_at > NOW() - INTERVAL '7 days'
ORDER BY e.first_seen_at DESC
LIMIT 20;
```

### Get top evidence for a trend

```sql
SELECT
    te.signal_type,
    te.delta_log_odds,
    te.reasoning,
    e.canonical_summary,
    te.created_at
FROM trend_evidence te
JOIN events e ON te.event_id = e.id
WHERE te.trend_id = $1
  AND te.created_at > NOW() - INTERVAL '7 days'
ORDER BY ABS(te.delta_log_odds) DESC
LIMIT 10;
```

### Calculate probability change over time

```sql
WITH current AS (
    SELECT log_odds FROM trend_snapshots
    WHERE trend_id = $1
    ORDER BY timestamp DESC
    LIMIT 1
),
week_ago AS (
    SELECT log_odds FROM trend_snapshots
    WHERE trend_id = $1
      AND timestamp < NOW() - INTERVAL '7 days'
    ORDER BY timestamp DESC
    LIMIT 1
)
SELECT
    1.0 / (1.0 + exp(-c.log_odds)) as current_prob,
    1.0 / (1.0 + exp(-w.log_odds)) as week_ago_prob,
    (1.0 / (1.0 + exp(-c.log_odds))) - (1.0 / (1.0 + exp(-w.log_odds))) as change
FROM current c, week_ago w;
```

### Find similar events (vector search)

```sql
SELECT
    id,
    canonical_summary,
    1 - (embedding <=> $1) as similarity
FROM events
WHERE first_seen_at > NOW() - INTERVAL '48 hours'
ORDER BY embedding <=> $1
LIMIT 5;
```

## Migrations

Migrations are managed with Alembic. Key files:

- `alembic.ini` - Configuration
- `alembic/env.py` - Migration environment
- `alembic/versions/` - Migration scripts

### Running Migrations

```bash
# Apply all migrations
make db-upgrade

# Rollback one step
make db-downgrade

# Generate new migration
make db-migrate msg="description"

# Show current version
make db-current

# Show migration history
make db-history
```
