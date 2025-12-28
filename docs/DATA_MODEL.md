# Data Model

## Entity Relationship Diagram

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
| config | JSONB | No | {} | Source-specific configuration |
| is_active | BOOLEAN | No | true | Whether to collect from this source |
| last_fetched_at | TIMESTAMPTZ | Yes | | Last successful fetch time |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |
| updated_at | TIMESTAMPTZ | No | NOW() | Last update time |

**Indexes:**
- Primary key: `id`

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
| external_id | VARCHAR(512) | No | | Original ID (URL for RSS, message_id for Telegram) |
| url | TEXT | Yes | | Full article URL |
| title | TEXT | Yes | | Article title |
| published_at | TIMESTAMPTZ | Yes | | Original publication time |
| fetched_at | TIMESTAMPTZ | No | NOW() | When we fetched it |
| raw_content | TEXT | No | | Extracted text content |
| content_hash | VARCHAR(64) | No | | SHA256 hash for dedup |
| language | VARCHAR(10) | Yes | | Detected language (ISO 639-1) |
| processing_status | VARCHAR(20) | No | 'pending' | Status: pending, processing, classified, noise, error |
| error_message | TEXT | Yes | | Error details if status=error |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |

**Indexes:**
- Primary key: `id`
- Unique: `(source_id, external_id)`
- Index: `processing_status`
- Index: `content_hash`
- Index: `fetched_at DESC`

**Processing status flow:**
```
pending → processing → classified
                    → noise
                    → error
```

---

### events

Clustered news events (multiple raw_items about the same story).

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| canonical_summary | TEXT | No | | Representative summary |
| embedding | vector(1536) | Yes | | Text embedding for similarity |
| extracted_who | TEXT[] | Yes | | Entities: people/organizations |
| extracted_what | TEXT | Yes | | What happened |
| extracted_where | TEXT | Yes | | Location |
| extracted_when | TIMESTAMPTZ | Yes | | When it happened |
| extracted_claims | JSONB | Yes | | Structured claims/facts |
| categories | TEXT[] | Yes | | Classification categories |
| source_count | INTEGER | No | 1 | Number of sources reporting this |
| first_seen_at | TIMESTAMPTZ | No | NOW() | First time we saw this event |
| last_updated_at | TIMESTAMPTZ | No | NOW() | Last time event was updated |
| primary_item_id | UUID | Yes | | Most credible source item |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |

**Indexes:**
- Primary key: `id`
- IVFFlat: `embedding` (vector_cosine_ops, lists=100)
- GIN: `categories`
- Index: `first_seen_at DESC`

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

### trend_evidence

Audit trail of all probability updates.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| trend_id | UUID | No | | Foreign key to trends |
| event_id | UUID | No | | Foreign key to events |
| signal_type | VARCHAR(100) | No | | Type of signal detected |
| credibility_score | DECIMAL(3,2) | Yes | | Source credibility (0.00-1.00) |
| corroboration_factor | DECIMAL(5,2) | Yes | | sqrt(sources)/3 |
| novelty_score | DECIMAL(3,2) | Yes | | 1.0 new, 0.3 repeat |
| severity_score | DECIMAL(3,2) | Yes | | Event severity |
| delta_log_odds | DECIMAL(10,6) | No | | Probability change |
| reasoning | TEXT | Yes | | LLM explanation |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |

**Indexes:**
- Primary key: `id`
- Unique: `(trend_id, event_id, signal_type)`
- Index: `(trend_id, created_at DESC)`
- Index: `event_id`

**Delta calculation:**
```
delta = weight × credibility × corroboration × novelty × direction

where direction = +1 (escalatory) or -1 (de_escalatory)
```

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
alembic upgrade head

# Rollback one step
alembic downgrade -1

# Generate new migration
alembic revision --autogenerate -m "description"

# Show current version
alembic current

# Show migration history
alembic history
```
