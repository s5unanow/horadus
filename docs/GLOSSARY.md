# Glossary

Domain terminology and concepts used throughout the Geopolitical Intelligence Platform.

---

## Core Concepts

### Raw Item
A single piece of content collected from a source. This could be:
- An RSS article
- A Telegram message
- A GDELT event record

Raw items are the atomic unit of ingestion. They are not yet classified or analyzed.

**Table:** `raw_items`

---

### Event
A clustered group of raw items about the same real-world occurrence.

When Reuters, BBC, and AP all report on "Russian ship seized in Black Sea," those three articles become ONE event with `source_count = 3`.

Events are what we classify and analyze — not individual articles.

**Key attributes:**
- `canonical_summary` - Representative summary of the event
- `source_count` - Number of independent sources reporting
- `embedding` - Vector for similarity search

**Table:** `events`

---

### Trend
A hypothesis about the world that we're tracking the probability of.

Examples:
- "EU-Russia Military Conflict"
- "US-China Trade War Escalation"
- "Taiwan Strait Crisis"

Each trend has:
- A **baseline probability** (prior belief)
- **Indicators** that affect the probability
- A **current probability** that updates based on evidence

**Table:** `trends`

---

### Signal
A type of evidence that affects a trend's probability.

For the "EU-Russia Military Conflict" trend, signals might include:
- `military_movement` (escalatory)
- `sanctions` (escalatory)
- `diplomatic_talks` (de-escalatory)

Each signal has a **weight** that determines how much it affects probability.

**Stored in:** `trends.indicators` (JSONB)

---

### Evidence
A record of how a specific event affected a specific trend.

When we process an event and determine it impacts a trend, we create an evidence record capturing:
- Which signal type was detected
- Source credibility
- Corroboration count
- The calculated probability delta
- Reasoning from the LLM

**Table:** `trend_evidence`

---

### Snapshot
A point-in-time record of a trend's probability.

Snapshots are taken hourly and stored for historical analysis. They enable:
- Time-series charts
- Week-over-week comparisons
- Retrospective analysis

**Table:** `trend_snapshots` (TimescaleDB hypertable)

---

## Probability Concepts

### Log-Odds
Our internal representation of probability.

**Formula:** `log_odds = ln(p / (1 - p))`

Why we use it:
- Evidence is **additive** (just add deltas)
- Never produces invalid probabilities
- Standard in Bayesian inference

**Conversion:**
```python
# Log-odds to probability
prob = 1 / (1 + exp(-log_odds))

# Probability to log-odds  
log_odds = ln(prob / (1 - prob))
```

**Example:**
| Probability | Log-Odds |
|-------------|----------|
| 1% | -4.60 |
| 10% | -2.20 |
| 50% | 0.00 |
| 90% | +2.20 |
| 99% | +4.60 |

---

### Evidence Delta
The change in log-odds from a single event.

**Formula:**
```
delta = weight × credibility × corroboration × novelty × direction
```

Where:
- `weight` = signal type's base weight (e.g., 0.04)
- `credibility` = source reliability (0-1)
- `corroboration` = sqrt(sources) / 3, capped at 1
- `novelty` = 1.0 if new info, 0.3 if repeated
- `direction` = +1 (escalatory) or -1 (de-escalatory)

---

### Decay
The natural regression of probability toward baseline over time.

Old news matters less. A military movement reported 6 months ago shouldn't still be pushing probability up.

**Parameter:** `decay_half_life_days`

If set to 30, after 30 days an event's impact is reduced by 50%.

---

### Baseline Probability
Your prior belief about a trend before any evidence.

This is where probability decays toward when there's no new evidence.

Example: "EU-Russia Military Conflict" might have a baseline of 8% — this is the "background" probability without any recent developments.

---

## Processing Concepts

### Tier 1 Filter
The first-pass LLM check using a cheap, fast model (gpt-4.1-nano).

Purpose: Quickly score relevance (0-10) for each configured trend.
- Score < 5 → Mark as "noise," archive
- Score >= 5 → Pass to Tier 2

Why: ~80% of articles are irrelevant. Don't waste expensive LLM calls on them.

---

### Tier 2 Classifier
The thorough LLM analysis using a capable model (gpt-4.1-mini).

Purpose: Extract detailed information:
- Who, what, where, when
- Specific claims and evidence
- Category classification
- Signal detection for each relevant trend
- Impact direction (escalatory/de-escalatory)
- 2-sentence summary

Only ~20% of items reach Tier 2.

---

### Deduplication
Preventing the same content from being processed multiple times.

Three levels:
1. **URL dedup** - Same URL already exists
2. **Hash dedup** - Same content hash (SHA256)
3. **Semantic dedup** - Embedding similarity > 0.92

---

### Event Clustering
Grouping similar raw items into events.

Process:
1. Compute embedding for new item
2. Search for items from last 48h with cosine similarity > 0.88
3. If found → Merge into existing event
4. If not → Create new event

---

### Corroboration
The number of independent sources reporting the same event.

Higher corroboration = higher confidence = larger evidence delta.

**Formula:** `corroboration_factor = min(sqrt(source_count) / 3, 1.0)`

| Sources | Factor |
|---------|--------|
| 1 | 0.33 |
| 4 | 0.67 |
| 9 | 1.00 |
| 16 | 1.00 (capped) |

---

### Credibility Score
A measure of source reliability (0.0 to 1.0).

Assigned per source:
- Reuters, AP: 0.95
- BBC, NYT: 0.90
- Regional news: 0.70
- Telegram channels: 0.50-0.70 (varies)
- Unknown: 0.50

Higher credibility = larger evidence delta.

---

## Report Concepts

### Weekly Report
Automated summary generated every week.

Contains for each trend:
- Current probability
- Change from last week
- Direction (rising/falling/stable)
- Top contributing events
- LLM-generated narrative

---

### Monthly Report
Deeper analysis generated every month.

Includes weekly report data plus:
- Category breakdown
- Source breakdown
- Trend comparison over time
- Executive summary

---

### Retrospective
Analysis of how past events affected trends.

Answers questions like:
- "What were the most impactful events for this trend?"
- "Which signal types drove the largest changes?"
- "How accurate were our classifications?"

---

## Technical Concepts

### Embedding
A dense vector representation of text for similarity comparison.

We use 1536-dimensional vectors (OpenAI embedding models).

Stored in PostgreSQL using **pgvector** extension.

---

### Hypertable
A TimescaleDB concept for efficient time-series storage.

The `trend_snapshots` table is a hypertable, automatically partitioned by time for fast range queries.

---

### JSONB
PostgreSQL's binary JSON type.

Used for flexible schema fields:
- `sources.config`
- `trends.indicators`
- `events.extracted_claims`

---

## Abbreviations

| Abbrev | Meaning |
|--------|---------|
| API | Application Programming Interface |
| CRUD | Create, Read, Update, Delete |
| EDA | Event-Driven Architecture |
| GDELT | Global Database of Events, Language, and Tone |
| LLM | Large Language Model |
| OSINT | Open Source Intelligence |
| RSS | Really Simple Syndication |
| UUID | Universally Unique Identifier |
