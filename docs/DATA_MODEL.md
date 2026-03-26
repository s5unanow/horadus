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
| provider_source_key | VARCHAR(255) | Yes | | Stable provider identity key used to preserve source state across harmless renames |
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
- Unique partial index: `(type, provider_source_key)` when `provider_source_key IS NOT NULL`
- Index: `is_active`
- Index: `type`
- Index: `source_tier`
- Index: `ingestion_window_end_at`

**Example config values:**
```json
// RSS
{"check_interval_minutes": 30, "max_articles_per_fetch": 50}

// Telegram
{"channel": "@example_channel", "include_media": false}

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
| event_summary | TEXT | Yes | | Canonical synthesized event-level summary used for API/reporting/Tier-2 carry-forward; falls back to `canonical_summary` until canonical Tier-2 writes one |
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
| independent_evidence_count | INTEGER | No | 1 | Number of likely independent evidence groups after provenance-aware grouping |
| corroboration_score | DECIMAL(5,2) | No | 1.00 | Weighted corroboration score used for trend math before contradiction penalty |
| corroboration_mode | VARCHAR(20) | No | 'fallback' | Whether corroboration currently comes from legacy fallback counts or provenance-aware grouping |
| provenance_summary | JSONB | No | {} | Bounded debug summary of source families, syndication/duplicate groups, and raw-vs-independent counts |
| extraction_provenance | JSONB | No | {} | Current Tier-2 extraction/runtime provenance basis (model, prompt hash, schema hash, overrides, replay/cache derivation) |
| extraction_status | VARCHAR(20) | No | 'none' | Current extraction durability state: none, canonical, provisional |
| provisional_extraction | JSONB | No | {} | Bounded provisional degraded-mode extraction payload kept out of normal report/API summary paths until superseded or promoted |
| epistemic_state | VARCHAR(20) | No | 'emerging' | Evidence/support axis: emerging, confirmed, contested, retracted |
| activity_state | VARCHAR(20) | No | 'active' | Recency/activity axis: active, dormant, closed |
| lifecycle_status | VARCHAR(20) | No | 'emerging' | Deprecated compatibility projection derived from the split axes |
| first_seen_at | TIMESTAMPTZ | No | NOW() | First time we saw this event |
| last_mention_at | TIMESTAMPTZ | No | NOW() | Most recent mention timestamp used for lifecycle transitions |
| last_updated_at | TIMESTAMPTZ | No | NOW() | Last time event was updated |
| confirmed_at | TIMESTAMPTZ | Yes | | Timestamp when event reached confirmed lifecycle threshold |
| primary_item_id | UUID | Yes | | Most credible source item |
| has_contradictions | BOOLEAN | No | false | Whether contradictory claims were detected across linked items |
| contradiction_notes | TEXT | Yes | | Optional contradiction analysis notes |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |

Notes:
- Canonical Tier-2 persists its synthesized structured-output `summary` into `events.event_summary`.
- Degraded-mode Tier-2 writes into `events.provisional_extraction` and marks `events.extraction_status = 'provisional'` instead of overwriting canonical report/event fields.
- Persisted `events.canonical_summary` remains the summary of the current `primary_item_id`.
- Exact-match entity resolution now persists typed event mentions into `event_entities`
  and links them to `canonical_entities` when an exact unique alias match exists
  or when Tier-2 safely seeds a new canonical row.

**Indexes:**
- Primary key: `id`
- IVFFlat: `embedding` (vector_cosine_ops, lists=64)
- GIN: `categories`
- Index: `first_seen_at DESC`
- Index: `(activity_state, last_mention_at)`
- Index: `(lifecycle_status, last_mention_at)`

**Vector search example:**
```sql
-- Find similar events (cosine similarity > 0.88)
SELECT id,
       COALESCE(event_summary, canonical_summary) AS summary,
       1 - (embedding <=> $1) as similarity
FROM events
WHERE first_seen_at > NOW() - INTERVAL '48 hours'
  AND embedding <=> $1 < 0.12  -- 1 - 0.88 = 0.12
ORDER BY embedding <=> $1
LIMIT 5;
```

Operational note:
- Use `uv run horadus eval embedding-lineage` to detect mixed model populations and estimate re-embed scope.
- `provenance_summary.cluster_health` now carries bounded merge-audit diagnostics
  (`cluster_cohesion_score`, `split_risk_score`) for operator review.

---

### canonical_entities

Durable canonical entity registry for event actors and locations.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| entity_type | VARCHAR(20) | No | | `person`, `organization`, or `location` |
| canonical_name | TEXT | No | | Durable display name for the canonical entity |
| normalized_name | VARCHAR(255) | No | | Exact-match lookup key after bounded normalization |
| entity_metadata | JSONB | No | {} | Bounded metadata such as seed provenance |
| is_auto_seeded | BOOLEAN | No | false | Whether the row was seeded automatically from Tier-2 output |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |
| updated_at | TIMESTAMPTZ | No | NOW() | Last update time |

**Indexes / uniqueness:**
- Primary key: `id`
- Unique: `(entity_type, normalized_name)`
- Index: `(entity_type, normalized_name)`

---

### canonical_entity_aliases

Exact alias rows used for bounded canonical-entity matching.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| canonical_entity_id | UUID | No | | Foreign key to `canonical_entities` |
| alias | TEXT | No | | Stored alias text |
| normalized_alias | VARCHAR(255) | No | | Exact-match lookup key for the alias |
| language | VARCHAR(16) | Yes | | Optional language/locale hint for the alias |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |

**Indexes / uniqueness:**
- Primary key: `id`
- Unique: `(canonical_entity_id, normalized_alias)`
- Index: `normalized_alias`

---

### event_entities

Typed entity mentions extracted from one event and linked to canonical rows when
resolution is safe.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| event_id | UUID | No | | Foreign key to `events` |
| entity_role | VARCHAR(20) | No | | Mention role: `actor` or `location` |
| entity_type | VARCHAR(20) | No | | Mention type: `person`, `organization`, or `location` |
| mention_text | TEXT | No | | Canonical English mention text from Tier-2 |
| mention_normalized | VARCHAR(255) | No | | Exact-match normalized lookup key |
| canonical_entity_id | UUID | Yes | | Optional FK to `canonical_entities` when resolution succeeds |
| resolution_status | VARCHAR(20) | No | | `resolved`, `ambiguous`, or `unresolved` |
| resolution_reason | VARCHAR(40) | Yes | | Deterministic reason such as `exact_alias`, `seeded_new_canonical`, or `ambiguous_alias` |
| resolution_details | JSONB | No | {} | Bounded debug payload for ambiguous matches |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |
| updated_at | TIMESTAMPTZ | No | NOW() | Last update time |

**Indexes / uniqueness:**
- Primary key: `id`
- Unique: `(event_id, entity_role, entity_type, mention_normalized)`
- Index: `(event_id, entity_role)`
- Index: `canonical_entity_id`

---

### event_lineage

Append-only split/merge repair ledger for mutable event clusters.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| lineage_kind | VARCHAR(20) | No | | Repair type: `split` or `merge` |
| source_event_id | UUID | Yes | | Historical source event reference |
| target_event_id | UUID | Yes | | Historical target/new event reference |
| details | JSONB | No | {} | Audit payload: moved item ids/count, invalidated evidence ids, replay queue linkage |
| created_by | VARCHAR(100) | Yes | | Optional operator identity |
| notes | TEXT | Yes | | Optional analyst notes |
| created_at | TIMESTAMPTZ | No | NOW() | Ledger timestamp |

**Indexes:**
- Index: `(source_event_id, created_at)`
- Index: `(target_event_id, created_at)`
- Follow `docs/EMBEDDING_MODEL_UPGRADE.md` for cutover/backfill/rollback workflow.
- Event confirmation now keys off `independent_evidence_count` when provenance metadata is present; fallback rows continue to use conservative legacy counts until they are recomputed.
- Lifecycle split/backfill guidance:
  - legacy `emerging` -> `epistemic_state=emerging`, `activity_state=active`
  - legacy `confirmed` -> `epistemic_state=confirmed`, `activity_state=active`
  - legacy `fading` -> `epistemic_state=confirmed`, `activity_state=dormant`
  - legacy `archived` -> `activity_state=closed`; `epistemic_state=retracted` only when event feedback recorded `mark_noise` or `invalidate`, otherwise `confirmed`

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

### event_claims

Stable claim/version identities recorded under one mutable `events` cluster.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| event_id | UUID | No | | Foreign key to events |
| claim_key | VARCHAR(255) | No | | Deterministic per-event stable key (`__event__` fallback or normalized claim text) |
| claim_text | TEXT | No | | Human-readable claim/version text |
| claim_type | VARCHAR(20) | No | `statement` | Claim kind: `fallback` or `statement` |
| claim_order | INTEGER | No | 0 | Stable display / reconciliation order |
| is_active | BOOLEAN | No | true | Whether the claim still appears in the latest event extraction |
| first_seen_at | TIMESTAMPTZ | No | NOW() | First time this claim identity was observed |
| last_seen_at | TIMESTAMPTZ | No | NOW() | Most recent extraction that still referenced this claim |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |
| updated_at | TIMESTAMPTZ | No | NOW() | Last update time |

**Indexes / uniqueness:**
- Primary key: `id`
- Unique: `(event_id, claim_key)`
- Index: `(event_id, is_active)`

Operational note:
- Each event always has one fallback claim (`claim_key='__event__'`) so legacy single-claim flows still have a durable stable identity even when Tier-2 emits no explicit statements.

---

### trends

Trend definitions and current probability state.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| name | VARCHAR(255) | No | | Unique trend name |
| description | TEXT | Yes | | Human-readable description |
| runtime_trend_id | VARCHAR(255) | No | | Unique runtime taxonomy identifier used by Tier-1/Tier-2/pipeline routing |
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
- Unique: `runtime_trend_id`

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
- `trends.definition.forecast_contract` is synchronized metadata describing the forecast question, horizon, resolver, and closure rule for the stored probability.
- `trends.definition.horizon_variant` can optionally encode explicit multi-horizon grouping via `theme_key`, optional `theme_name`, a horizon `label`, optional `window_days`, and `sort_order`.
- `trends.runtime_trend_id` is the canonical routing key for runtime taxonomy lookups; it must match `trends.definition.id` after normalization.

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
| event_claim_id | UUID | No | | Foreign key to stable `event_claims` identity used for replay/invalidation lineage |
| signal_type | VARCHAR(100) | No | | Type of signal detected |
| base_weight | DECIMAL(10,6) | Yes | | Indicator weight used at scoring time (nullable for pre-`TASK-157` rows) |
| direction_multiplier | DECIMAL(3,1) | Yes | | Direction factor used at scoring time (`+1.0` escalatory, `-1.0` de-escalatory; nullable for legacy rows) |
| trend_definition_hash | VARCHAR(64) | Yes | | Deterministic hash of trend definition used at scoring time (nullable for legacy rows) |
| scoring_math_version | VARCHAR(64) | No | `trend-scoring-v1` | Named deterministic scoring-formula version (`legacy-unversioned` for older rows) |
| scoring_parameter_set | VARCHAR(64) | No | `stable-default-v1` | Named scoring-parameter-set contract used when the delta was applied |
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
| is_invalidated | BOOLEAN | No | FALSE | Whether this evidence row was invalidated by human feedback or Tier-2 supersession |
| invalidated_at | TIMESTAMPTZ | Yes | | Timestamp when invalidation was recorded |
| invalidation_feedback_id | UUID | Yes | | Optional FK to `human_feedback.id` when invalidation came from operator feedback |

**Indexes / uniqueness:**
- Primary key: `id`
- Unique active row only: `(trend_id, event_claim_id, signal_type)` where `is_invalidated=false`
- Index: `(trend_id, created_at DESC)`
- Index: `event_id`
- Index: `event_claim_id`
- Index: `(event_id, is_invalidated)`

**Invalidation lineage semantics:**
- Event invalidation no longer deletes evidence rows.
- Instead, evidence is marked `is_invalidated=true` and linked to the originating `human_feedback` record while a separate `trend_restatements` row records the signed compensating delta applied later.
- Tier-2 reclassification can also supersede an active evidence row; the old row is invalidated, a replacement active row is inserted against the stable `event_claim_id`, and a `trend_restatements` row captures the compensating reversal that kept the projection honest.
- Operational analytics/reporting queries use only active (`is_invalidated=false`) evidence by default.
- Audit/replay paths can include invalidated lineage explicitly when needed, or reconstruct the stored trend value by replaying chronological evidence plus `trend_restatements`.

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

Scoring-time provenance:
- `base_weight`, `direction_multiplier`, `trend_definition_hash`, `scoring_math_version`, and `scoring_parameter_set` are persisted to preserve factorization inputs even if trend YAML/definitions change later.
- Legacy rows (created before `TASK-157`) may have these fields as `NULL`.

---

### trend_restatements

Append-only compensating ledger for corrections applied after original evidence scoring.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| trend_id | UUID | No | | FK to `trends` |
| event_id | UUID | Yes | | Optional FK to `events` for event-scoped restatements |
| event_claim_id | UUID | Yes | | Optional FK to `event_claims` for claim-aware lineage |
| trend_evidence_id | UUID | Yes | | Optional FK to the original compensated evidence row |
| feedback_id | UUID | Yes | | Optional FK to `human_feedback.id` when operator initiated |
| restatement_kind | VARCHAR(50) | No | | `full_invalidation`, `partial_restatement`, `manual_compensation`, or `reclassification` |
| source | VARCHAR(50) | No | | Correction source (`event_feedback`, `trend_override`, `tier2_reconciliation`) |
| original_evidence_delta_log_odds | DECIMAL(10,6) | Yes | | Original evidence delta before compensation |
| compensation_delta_log_odds | DECIMAL(10,6) | No | | Signed compensating delta applied to the trend |
| scoring_math_version | VARCHAR(64) | No | `trend-scoring-v1` | Named scoring-formula version active when the restatement was recorded |
| scoring_parameter_set | VARCHAR(64) | No | `stable-default-v1` | Named scoring-parameter-set contract active when the restatement was recorded |
| notes | TEXT | Yes | | Analyst/runtime explanation |
| details | JSONB | Yes | | Structured lineage context |
| recorded_at | TIMESTAMPTZ | No | NOW() | Ledger timestamp |

**Indexes / constraints:**
- Primary key: `id`
- Index: `(trend_id, recorded_at)`
- Index: `trend_evidence_id`
- Index: `feedback_id`
- Check: `restatement_kind`
- Check: `source`

**Projection contract:**
- `trend_evidence` remains the append-only record of original scored evidence applications.
- `trend_restatements` records later signed corrections without rewriting the original evidence rows.
- Deterministic recompute walks chronological evidence and restatement entries, applying the normal exponential decay between state changes, to verify or rebuild `trends.current_log_odds`.

---

### event_adjudications

Append-only typed operator workflow ledger for high-risk event review.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| event_id | UUID | No | | FK to `events` |
| feedback_id | UUID | Yes | | Optional FK to `human_feedback.id` when the adjudication reused an existing feedback mutation path |
| outcome | VARCHAR(50) | No | | `confirm`, `suppress`, `restate`, or `escalate_taxonomy_review` |
| review_status | VARCHAR(50) | No | | Derived workflow status (`resolved`, `needs_taxonomy_review`) |
| override_intent | VARCHAR(50) | No | | Typed intent (`pin_event`, `suppress_event`, `apply_restatement`, `taxonomy_escalation`) |
| resulting_effect | JSONB | No | `{}` | Structured payload describing linked feedback/restatement effects and queue-facing metadata |
| notes | TEXT | Yes | | Operator rationale |
| created_by | VARCHAR(100) | Yes | | Reviewer identity |
| created_at | TIMESTAMPTZ | No | NOW() | Ledger timestamp |

**Indexes / constraints:**
- Primary key: `id`
- Index: `(event_id, created_at)`
- Index: `(review_status, created_at)`
- Index: `feedback_id`
- Check: `outcome`
- Check: `review_status`
- Check: `override_intent`

**Operational intent:**
- `event_adjudications` is the canonical typed review-state surface for risky events.
- Existing event feedback and trend restatement paths still own the concrete mutation semantics for suppress/restate-compatible actions.
- Read APIs derive current event/review queue status from the latest adjudication plus open taxonomy-gap counts rather than inferring workflow state from generic feedback rows alone.

---

### taxonomy_gaps

Runtime triage queue for deterministic trend-impact mappings that could not be
scored safely.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| event_id | UUID | Yes | | Optional FK to `events` (`SET NULL` on delete) |
| trend_id | VARCHAR(255) | No | | Trend identifier or deterministic placeholder for unresolved mapping |
| signal_type | VARCHAR(255) | No | | Indicator key or deterministic placeholder for unresolved mapping |
| reason | ENUM | No | | `unknown_trend_id`, `unknown_signal_type`, `ambiguous_mapping`, or `no_matching_indicator` |
| source | VARCHAR(50) | No | `pipeline` | Runtime source that recorded the gap |
| details | JSONB | No | `{}` | Structured context (`event_claim_key`, candidate mappings, prior extracted evidence, etc.) |
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

### novelty_candidates

Bounded operator-facing lane for persistent signals that do not safely map onto
the active trend catalog.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| cluster_key | VARCHAR(64) | No | | Deterministic novelty-cluster identity |
| candidate_kind | VARCHAR(32) | No | | `near_threshold_item` or `event_gap` |
| event_id | UUID | Yes | | Optional FK to the most recent representative `events` row |
| raw_item_id | UUID | Yes | | Optional FK to the most recent representative `raw_items` row |
| summary | TEXT | No | | Operator-facing representative summary/snippet |
| details | JSONB | No | `{}` | Bounded ranking/context payload (`actors`, `where`, `top_trend_scores`, unresolved mapping counts, etc.) |
| recurrence_count | INTEGER | No | `1` | Number of captures rolled into this novelty cluster |
| distinct_source_count | INTEGER | No | `1` | Max observed unique-source count across captures |
| actor_location_hits | INTEGER | No | `0` | Count of captures with unusual actor/location structure |
| near_threshold_hits | INTEGER | No | `0` | Count of repeated Tier-1 near-threshold misses |
| unmapped_signal_count | INTEGER | No | `0` | Max unresolved deterministic-mapping count seen for the cluster |
| last_tier1_max_relevance | INTEGER | Yes | | Highest Tier-1 score seen for the cluster |
| ranking_score | DECIMAL(8,4) | No | `0` | Deterministic novelty ranking used by the operator queue |
| first_seen_at | TIMESTAMPTZ | No | NOW() | First capture timestamp |
| last_seen_at | TIMESTAMPTZ | No | NOW() | Most recent capture timestamp |
| created_at | TIMESTAMPTZ | No | NOW() | Row creation timestamp |

**Indexes:**
- Primary key: `id`
- Unique: `cluster_key`
- Index: `last_seen_at DESC`
- Index: `(candidate_kind, last_seen_at DESC)`
- Index: `(ranking_score DESC, last_seen_at DESC)`
- Index: `event_id`
- Index: `raw_item_id`

**Operational intent:**
- Novelty capture is deterministic and bounded; it reuses Tier-1/Tier-2 outputs and does not add LLM work.
- Novelty candidates never apply `trend_evidence` deltas by themselves.
- API queue path: `GET /api/v1/novelty-queue`.

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

**Historical-artifact policy:**
- `trend_snapshots` remain “belief at the time” artifacts and are not rewritten when later restatements occur.
- Corrected-history inspection should use the restatement ledger and projection/recompute path rather than mutating prior snapshots.

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
| generation_manifest | JSONB | No | {} | Pinned report-generation manifest covering prompt/model lineage, scoring contract, and evidence/event input ids |
| created_at | TIMESTAMPTZ | No | NOW() | Record creation time |

**Indexes:**
- Primary key: `id`
- Index: `(report_type, period_end)`
- Index: `trend_id`

**Historical-artifact policy:**
- Generated reports preserve the deterministic statistics and narrative that were true at report time.
- `generation_manifest` pins the stored artifact to its input evidence/event ids, active scoring contract, and narrative/runtime provenance basis.
- Later invalidations/restatements do not rewrite stored report bodies; corrected-history analysis should reference `trend_restatements` plus current projection verification.

---

### coverage_snapshots

Persisted recent source-coverage health snapshots for operator review.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | No | gen_random_uuid() | Primary key |
| generated_at | TIMESTAMPTZ | No | | Timestamp when the coverage report was generated |
| window_start | TIMESTAMPTZ | No | | Inclusive start of the intake coverage window |
| window_end | TIMESTAMPTZ | No | | Exclusive end of the intake coverage window |
| lookback_hours | INTEGER | No | | Window size used for the report |
| artifact_path | VARCHAR(512) | Yes | | Filesystem path to the exported JSON artifact |
| payload | JSONB | No | `{}` | Full coverage report payload (totals, segment rows, alerts) |
| created_at | TIMESTAMPTZ | No | NOW() | Snapshot row creation time |

**Indexes:**
- Primary key: `id`
- Index: `generated_at`
- Index: `window_end`

Notes:
- The payload stores bounded segment summaries for language, source family, source tier, and configured source topics.
- Snapshot artifacts are also exported to `artifacts/source_coverage/` for release-gate and operator review surfaces.

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
| action | VARCHAR(50) | No | | Feedback action (`pin`, `mark_noise`, `invalidate`, `restate`, `override_delta`, `correct_category`) |
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

## Model Verification Notes (2026-03-17)

The sections above were cross-checked against SQLAlchemy runtime model declarations:

- `canonical_entities` table: `src/storage/entity_models.py`
- `canonical_entity_aliases` table: `src/storage/entity_models.py`
- `event_entities` table: `src/storage/entity_models.py`
- `trend_definition_versions` table: `src/storage/models.py`
- `reports` table: `src/storage/models.py`
- `api_usage` table: `src/storage/models.py`
- `trend_outcomes` table: `src/storage/models.py`
- `human_feedback` table: `src/storage/restatement_models.py`
- `event_adjudications` table: `src/storage/restatement_models.py`
- `trend_restatements` table: `src/storage/restatement_models.py`

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
    COALESCE(e.event_summary, e.canonical_summary) AS summary,
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
    COALESCE(e.event_summary, e.canonical_summary) AS summary,
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
    COALESCE(event_summary, canonical_summary) AS summary,
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
