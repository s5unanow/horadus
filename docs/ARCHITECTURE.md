# Architecture Overview

**Last Verified**: 2026-02-18

Operational tracing setup and validation steps are documented in `docs/TRACING.md`.

## System Context

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           EXTERNAL SYSTEMS                              │
├──────────────┬──────────────┬──────────────┬──────────────┬────────────┤
│  RSS/Web     │    GDELT     │   Telegram   │   LLM API    │   Client   │
│  Sources     │    API       │   Channels   │   (OpenAI)   │   Apps     │
└──────┬───────┴──────┬───────┴──────┬───────┴──────┬───────┴─────┬──────┘
       │              │              │              │             │
       │              │              │              │             │
       ▼              ▼              ▼              ▼             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│                  GEOPOLITICAL INTELLIGENCE PLATFORM                     │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                        FastAPI (REST)                           │   │
│   │   /api/v1/trends  /api/v1/events  /api/v1/reports  /health     │   │
│   └─────────────────────────────────┬───────────────────────────────┘   │
│                                     │                                   │
│   ┌─────────────────────────────────▼───────────────────────────────┐   │
│   │                          CORE DOMAIN                            │   │
│   │                                                                 │   │
│   │   TrendEngine      EventClusterer      ReportGenerator          │   │
│   │   (log-odds        (embedding          (stats +                 │   │
│   │    probability)     similarity)         LLM narrative)          │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                     │                                   │
│   ┌─────────────────────────────────▼───────────────────────────────┐   │
│   │                      PROCESSING LAYER                           │   │
│   │                                                                 │   │
│   │   Tier1 Filter     Tier2 Classifier    Deduplicator             │   │
│   │   (nano)           (mini)              (hash + vector)          │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                     │                                   │
│   ┌─────────────────────────────────▼───────────────────────────────┐   │
│   │                      INGESTION LAYER                            │   │
│   │                                                                 │   │
│   │   RSSCollector     GDELTClient         TelegramHarvester        │   │
│   │   (feedparser)     (REST)              (Telethon)               │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                     │                                   │
│   ┌─────────────────────────────────▼───────────────────────────────┐   │
│   │                      WORKER LAYER (Celery)                      │   │
│   │                                                                 │   │
│   │   collect_rss      process_item        generate_report          │   │
│   │   collect_gdelt    snapshot_trends     apply_decay              │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                     │                                   │
│   ┌─────────────────────────────────▼───────────────────────────────┐   │
│   │                      STORAGE LAYER                              │   │
│   │                                                                 │   │
│   │   PostgreSQL + pgvector + TimescaleDB          Redis            │   │
│   │   (events, trends, evidence, snapshots)        (queue, cache)   │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Ingestion Flow

```
                    ┌─────────────┐
                    │   Source    │
                    │ (RSS/GDELT/ │
                    │  Telegram)  │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Collector  │
                    │  (fetch +   │
                    │   extract)  │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Normalize  │
                    │  to         │
                    │  RawItem    │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐     ┌─────────────┐
                    │  Dedup by   │────▶│   SKIP      │
                    │  URL/hash   │dup  │  (already   │
                    └──────┬──────┘     │   exists)   │
                           │new         └─────────────┘
                           ▼
                    ┌─────────────┐
                    │   Store     │
                    │  raw_item   │
                    │  (pending)  │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Queue for  │
                    │  processing │
                    └─────────────┘
```

Ingestion tracks per-source high-water coverage timestamps and applies overlap-aware
next-window starts to avoid silent gaps on delayed runs/restarts.
Periodic freshness checks (`workers.check_source_freshness`) alert on stale sources
and trigger bounded collector catch-up dispatch before gap risk accumulates.

### 2. Processing Flow

Current model mapping (see ADR-002):
- Tier 1 (filter): `gpt-4.1-nano`
- Tier 2 (classify/summarize): `gpt-4.1-mini`

Launch language policy:
- Supported processing languages: `en`, `uk`, `ru`
- Unsupported-language handling is deterministic via `LANGUAGE_POLICY_UNSUPPORTED_MODE`:
  - `skip`: mark item as `noise`
  - `defer`: leave item `pending` for later/manual handling
- Missing/unknown language metadata is currently processed as `unknown` (not auto-dropped)

```
┌─────────────┐
│  raw_item   │
│  (pending)  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Dedup check │
│ (url/hash)  │
└──────┬──────┘
       │
       ├──────── duplicate ───────▶ mark as noise
       │
       ▼
┌─────────────┐
│ Tier 1 LLM  │
│ relevance   │
│ score 0-10  │
└──────┬──────┘
       │
       ├──────── score < threshold ───▶ mark as noise
       │
       ▼
┌─────────────┐
│  Compute    │
│  embedding  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Cluster to  │
│ event       │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Tier 2 LLM  │
│ classify +  │
│ extraction  │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────┐
│ Apply deterministic trend   │
│ deltas (log-odds update +   │
│ evidence provenance record) │
└─────────────────────────────┘
```

Language-segmented operational metrics are emitted for:
- intake (`processing_ingested_language_total`)
- Tier-1 routing outcomes (`processing_tier1_language_outcome_total`)
- Tier-2 usage (`processing_tier2_language_usage_total`)

### 3. Probability Update (Detail)

```
┌─────────────────────────────────────────────────────────────────┐
│                     EVIDENCE DELTA CALCULATION                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   delta_log_odds = base_weight                                  │
│                    × credibility        (0.0 - 1.0)             │
│                    × corroboration      (sqrt(sources) / 3)     │
│                    × novelty            (1.0 new, 0.3 repeat)   │
│                    × severity           (0.0 - 1.0 magnitude)   │
│                    × confidence         (0.0 - 1.0 LLM score)   │
│                    × direction          (+1 escalatory, -1 de)  │
│                                                                 │
│   Example:                                                      │
│   - Military movement signal (weight: 0.04)                     │
│   - From Reuters (credibility: 0.95)                            │
│   - 3 sources (corroboration: √3/3 = 0.58)                      │
│   - New information (novelty: 1.0)                              │
│   - Major event (severity: 0.9)                                 │
│   - High confidence (confidence: 0.95)                          │
│   - Escalatory (direction: +1)                                  │
│                                                                 │
│   delta = 0.04 × 0.95 × 0.58 × 1.0 × 0.9 × 0.95 × 1 = 0.0188    │
│                                                                 │
│   trend.current_log_odds += 0.0188                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4. Reporting Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    WEEKLY REPORT GENERATION                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   1. Scheduled Job (Celery Beat)                                │
│      └─▶ Trigger: Every Sunday at 00:00 UTC                     │
│                                                                 │
│   2. For each active trend:                                     │
│      ├─▶ Query: current_probability                             │
│      ├─▶ Query: probability 7 days ago                          │
│      ├─▶ Query: top 5 contributing events                       │
│      ├─▶ Query: category breakdown                              │
│      └─▶ Compute: direction (rising/falling/stable)             │
│                                                                 │
│   3. Generate narrative (LLM):                                  │
│      ├─▶ Input: computed statistics (NOT raw events)            │
│      ├─▶ Prompt: "Write a 2-paragraph intelligence brief..."    │
│      ├─▶ Output: narrative text                                 │
│      └─▶ Deterministic grounding check against supplied stats   │
│                                                                 │
│   4. Store report:                                              │
│      └─▶ reports table (JSON + narrative + grounding metadata)  │
│                                                                 │
│   5. Expose via API:                                            │
│      └─▶ GET /api/v1/reports/{id}                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### 1. Log-Odds for Probability (ADR-003)

Why: Raw probability arithmetic is problematic (can exceed bounds, not additive).
How: Store `log_odds = ln(p / (1-p))`, convert to probability for display.
Benefit: Evidence is additive, always produces valid probabilities.

### 2. Events > Articles (ADR-004)

Why: Same story appears in 50 sources.
How: Cluster by embedding similarity (cosine > 0.88 within 48h).
Benefit: One event with corroboration count, not 50 duplicate items.
Safety: Similarity matching is constrained to vectors with the same `embedding_model`
lineage value to avoid cross-model drift.

### 3. Two-Tier LLM Processing (ADR-005)

Why: LLM calls are expensive; most news is irrelevant.
How: Tier 1 model filters, Tier 2 model classifies (see ADR-002 for current models).
Benefit: Significant cost reduction vs. running Tier 2 on all items.

### 4. Deterministic Scoring (ADR-006)

Why: LLM outputs are non-deterministic and unexplainable.
How: LLM extracts signals → Code computes deltas.
Benefit: Every probability change has an auditable paper trail.
Reference: `docs/adr/006-deterministic-scoring.md`

## Component Details

### Ingestion Layer

| Collector | Source | Library | Frequency |
|-----------|--------|---------|-----------|
| RSSCollector | RSS/Atom feeds | feedparser + trafilatura | 30 min |
| GDELTClient | GDELT API | httpx | 1 hour |
| TelegramHarvester | Telegram channels | telethon | Real-time |

### Processing Layer

| Component | Purpose | Model/Method |
|-----------|---------|--------------|
| Tier1Filter | Quick relevance check | gpt-4.1-nano |
| Tier2Classifier | Full classification | gpt-4.1-mini |
| EmbeddingService | Generate embeddings | OpenAI |
| EventClusterer | Group similar items | pgvector cosine |
| Deduplicator | Prevent duplicates | URL + hash + embedding |

### Core Domain

| Component | Purpose | Algorithm |
|-----------|---------|-----------|
| TrendEngine | Probability tracking | Log-odds with decay |
| EvidenceRecorder | Audit trail | Append-only records |
| SnapshotService | Time-series | Hourly snapshots |
| ReportGenerator | Weekly/monthly reports | Stats + LLM narrative |

### Storage Layer

| Store | Technology | Purpose |
|-------|------------|---------|
| Primary | PostgreSQL | All structured data |
| Vector | pgvector | Embedding similarity |
| Time-series | TimescaleDB | Trend snapshots |
| Queue | Redis | Celery task queue |
| Cache | Redis | Optional caching |

## Configuration

### Trend Definition

Trends are defined in YAML files:

```yaml
# config/trends/eu-russia.yaml
id: "eu-russia-conflict"
name: "EU-Russia Military Conflict"
description: "Probability of direct military confrontation"

baseline_probability: 0.08  # 8% prior (converted to log-odds: -2.44)

indicators:
  military_movement:
    weight: 0.04
    direction: escalatory
    keywords: ["troops", "deployment", "mobilization", "exercises"]

  sanctions:
    weight: 0.02
    direction: escalatory
    keywords: ["sanctions", "embargo", "restrictions"]

  diplomatic_breakdown:
    weight: 0.03
    direction: escalatory
    keywords: ["expelled", "ambassador", "recalled"]

  de_escalation:
    weight: 0.03
    direction: de_escalatory
    keywords: ["talks", "ceasefire", "agreement", "negotiation"]

decay_half_life_days: 30
```

### Source Definition

Sources are defined in YAML files:

```yaml
# config/sources/rss_feeds.yaml
feeds:
  - name: "Reuters World"
    url: "https://feeds.reuters.com/Reuters/worldNews"
    credibility: 0.95
    check_interval_minutes: 30

  - name: "BBC World"
    url: "http://feeds.bbci.co.uk/news/world/rss.xml"
    credibility: 0.90
    check_interval_minutes: 30
```

## Security Considerations

1. **API Keys**: Stored in environment variables, never in code
2. **Database**: No PII stored (news is public data)
3. **API Access**: Redis-backed API key auth + rate limiting is implemented
4. **Telegram**: Session files encrypted at rest
5. **LLM**: No sensitive data sent to external APIs

## Scaling Considerations

### Current Design (Single Server)

- Handles ~10,000 items/day easily
- PostgreSQL on same machine
- Single Celery worker

### Future Scaling (If Needed)

1. **Horizontal**: Multiple Celery workers
2. **Database**: Read replicas for API queries
3. **Queue**: Redis cluster for high throughput
4. **API**: Multiple uvicorn workers behind load balancer

## Monitoring

### Key Metrics

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| Items processed/hour | Celery | < 10 |
| LLM cost/day | Application | > $5.00 |
| API latency p95 | FastAPI | > 500ms |
| Queue depth | Redis | > 1000 |
| Error rate | Logs | > 1% |

### Health Checks

- `/health` - Full system check
- `/health/live` - App running (Kubernetes liveness)
- `/health/ready` - Dependencies available (Kubernetes readiness)
