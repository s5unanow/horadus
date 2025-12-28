# Architecture Overview

## System Context

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           EXTERNAL SYSTEMS                              │
├──────────────┬──────────────┬──────────────┬──────────────┬────────────┤
│  RSS/Web     │    GDELT     │   Telegram   │  Claude API  │   Client   │
│  Sources     │    API       │   Channels   │   (LLM)      │   Apps     │
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
│   │   (Haiku)          (Sonnet)            (hash + vector)          │   │
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

### 2. Processing Flow

```
┌─────────────┐
│  raw_item   │
│  (pending)  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Tier 1 LLM  │
│ (Haiku)     │
│ relevance   │
│ score 0-10  │
└──────┬──────┘
       │
       ├─────────────────────────────────┐
       │ score < 5                       │ score >= 5
       ▼                                 ▼
┌─────────────┐                   ┌─────────────┐
│   Mark as   │                   │ Tier 2 LLM  │
│   "noise"   │                   │ (Sonnet)    │
│   Archive   │                   │             │
└─────────────┘                   │ • classify  │
                                  │ • extract   │
                                  │ • summarize │
                                  └──────┬──────┘
                                         │
                                         ▼
                                  ┌─────────────┐
                                  │  Compute    │
                                  │  embedding  │
                                  └──────┬──────┘
                                         │
                                         ▼
                                  ┌─────────────┐     ┌─────────────┐
                                  │  Find       │────▶│   Merge     │
                                  │  similar    │sim  │   into      │
                                  │  events     │>0.88│   existing  │
                                  └──────┬──────┘     │   event     │
                                         │new         └──────┬──────┘
                                         ▼                   │
                                  ┌─────────────┐            │
                                  │  Create     │            │
                                  │  new event  │            │
                                  └──────┬──────┘            │
                                         │                   │
                                         └─────────┬─────────┘
                                                   │
                                                   ▼
                                  ┌─────────────────────────────┐
                                  │   For each matching trend:  │
                                  │                             │
                                  │   1. Identify signal type   │
                                  │   2. Get source credibility │
                                  │   3. Count corroboration    │
                                  │   4. Assess novelty         │
                                  │   5. Calculate delta        │
                                  │   6. Update log_odds        │
                                  │   7. Store evidence record  │
                                  └─────────────────────────────┘
```

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
│                    × direction          (+1 escalatory, -1 de)  │
│                                                                 │
│   Example:                                                      │
│   - Military movement signal (weight: 0.04)                     │
│   - From Reuters (credibility: 0.95)                            │
│   - 3 sources (corroboration: √3/3 = 0.58)                      │
│   - New information (novelty: 1.0)                              │
│   - Escalatory (direction: +1)                                  │
│                                                                 │
│   delta = 0.04 × 0.95 × 0.58 × 1.0 × 1 = 0.022                  │
│                                                                 │
│   trend.current_log_odds += 0.022                               │
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
│      └─▶ Output: narrative text                                 │
│                                                                 │
│   4. Store report:                                              │
│      └─▶ reports table (JSON + narrative)                       │
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

### 3. Two-Tier LLM Processing (ADR-005)

Why: LLM calls are expensive; most news is irrelevant.
How: Cheap model (Haiku) filters, expensive model (Sonnet) classifies.
Benefit: ~80% cost reduction vs. processing everything with Sonnet.

### 4. Deterministic Scoring (ADR-006)

Why: LLM outputs are non-deterministic and unexplainable.
How: LLM extracts signals → Code computes deltas.
Benefit: Every probability change has an auditable paper trail.

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
| Tier1Filter | Quick relevance check | Claude Haiku |
| Tier2Classifier | Full classification | Claude Sonnet |
| EmbeddingService | Generate embeddings | Claude/OpenAI |
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
3. **API Access**: Rate limiting (future)
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
| LLM cost/day | Application | > $50 |
| API latency p95 | FastAPI | > 500ms |
| Queue depth | Redis | > 1000 |
| Error rate | Logs | > 1% |

### Health Checks

- `/health` - Full system check
- `/health/live` - App running (Kubernetes liveness)
- `/health/ready` - Dependencies available (Kubernetes readiness)
