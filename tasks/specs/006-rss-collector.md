# TASK-006: RSS Collector

## Overview

Build an async RSS feed collector that fetches articles from configured feeds,
extracts full-text content using Trafilatura, deduplicates, and stores in the database.

## Context

This is the first data ingestion pathway. We start with RSS because:
- Structured format (easy to parse)
- Wide coverage (most news sites have RSS)
- Reliable (rarely blocked, unlike scraping)
- Real-time-ish (updated frequently)

## Dependencies

- TASK-003: Database schema (must be complete)
- TASK-004: FastAPI skeleton (for testing)

## Requirements

### Functional

1. **Configuration Loading**
   - Read feed configs from `config/sources/rss_feeds.yaml`
   - Schema defined in `config/sources/rss_schema.yaml`
   - Support hot-reload of config without restart

2. **Feed Fetching**
   - Use `httpx` for async HTTP requests
   - Parse RSS/Atom with `feedparser`
   - Handle various RSS versions (0.9x, 1.0, 2.0, Atom)
   - Gracefully handle malformed feeds

3. **Article Extraction**
   - For each entry, fetch the full article URL
   - Extract main content using `trafilatura`
   - Fall back to RSS summary if extraction fails
   - Extract metadata: title, author, published_date, language

4. **Deduplication**
   - Check by normalized URL (strip query params, www, trailing slashes)
   - Check by content hash (SHA256 of extracted text)
   - Skip if either match exists in last 7 days

5. **Storage**
   - Create `Source` record if not exists (on first run)
   - Create `RawItem` record for each new article
   - Set `processing_status = 'pending'`

6. **Error Handling**
   - Log and skip individual article failures
   - Log and continue on feed-level failures
   - Track failure counts per source

### Non-Functional

1. **Rate Limiting**
   - Max 1 request per second per domain
   - Configurable delay between requests
   - Respect Retry-After headers

2. **Timeouts**
   - Feed fetch: 30 seconds
   - Article fetch: 30 seconds
   - Total per feed: 5 minutes

3. **Retries**
   - 3 retries with exponential backoff
   - Jitter to avoid thundering herd

## Data Structures

### Config Schema

```yaml
# config/sources/rss_feeds.yaml
feeds:
  - name: "Reuters World News"
    url: "https://feeds.reuters.com/Reuters/worldNews"
    credibility: 0.95
    categories: ["world", "politics"]
    check_interval_minutes: 30
    max_items_per_fetch: 50
    enabled: true
    
  - name: "BBC World"
    url: "http://feeds.bbci.co.uk/news/world/rss.xml"
    credibility: 0.90
    categories: ["world"]
    check_interval_minutes: 30
    max_items_per_fetch: 50
    enabled: true
    
  - name: "Al Jazeera"
    url: "https://www.aljazeera.com/xml/rss/all.xml"
    credibility: 0.85
    categories: ["world", "middle-east"]
    check_interval_minutes: 60
    enabled: true
```

### Database Tables (already defined)

```python
# From src/storage/models.py
class Source:
    id: UUID
    type: str  # 'rss'
    name: str
    url: str
    credibility_score: float
    config: dict  # Original YAML config
    is_active: bool
    last_fetched_at: datetime | None

class RawItem:
    id: UUID
    source_id: UUID
    external_id: str  # URL
    url: str
    title: str
    published_at: datetime | None
    fetched_at: datetime
    raw_content: str
    content_hash: str
    language: str | None
    processing_status: str  # 'pending', 'processing', 'classified', 'noise', 'error'
```

## Implementation

### File Structure

```
src/ingestion/
├── __init__.py
├── rss_collector.py      # Main collector class
├── rss_parser.py         # Feed parsing logic
├── content_extractor.py  # Trafilatura wrapper
├── rate_limiter.py       # Per-domain rate limiting
└── deduplicator.py       # URL/hash dedup logic

config/sources/
├── rss_feeds.yaml        # Feed configurations
└── rss_schema.yaml       # YAML schema for validation
```

### Class Design

```python
# src/ingestion/rss_collector.py

from dataclasses import dataclass
from datetime import datetime
import asyncio
import hashlib

import feedparser
import httpx
import trafilatura
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models import Source, RawItem
from src.ingestion.rate_limiter import DomainRateLimiter


@dataclass
class FeedConfig:
    name: str
    url: str
    credibility: float
    categories: list[str]
    check_interval_minutes: int
    max_items_per_fetch: int
    enabled: bool


@dataclass
class CollectionResult:
    feed_name: str
    items_fetched: int
    items_stored: int
    items_skipped: int
    errors: list[str]
    duration_seconds: float


class RSSCollector:
    """Collects articles from configured RSS feeds."""
    
    def __init__(
        self,
        session: AsyncSession,
        http_client: httpx.AsyncClient,
        config_path: str = "config/sources/rss_feeds.yaml"
    ):
        self.session = session
        self.http_client = http_client
        self.config_path = config_path
        self.rate_limiter = DomainRateLimiter(requests_per_second=1.0)
        self._feeds: list[FeedConfig] = []
    
    async def load_config(self) -> None:
        """Load feed configurations from YAML file."""
        # Implementation here
        pass
    
    async def collect_all(self) -> list[CollectionResult]:
        """Collect from all enabled feeds."""
        results = []
        for feed in self._feeds:
            if feed.enabled:
                result = await self.collect_feed(feed)
                results.append(result)
        return results
    
    async def collect_feed(self, feed: FeedConfig) -> CollectionResult:
        """Collect articles from a single feed."""
        # Implementation here
        pass
    
    async def _fetch_feed(self, url: str) -> feedparser.FeedParserDict:
        """Fetch and parse RSS feed."""
        pass
    
    async def _extract_content(self, url: str) -> str | None:
        """Extract full article content from URL."""
        pass
    
    async def _is_duplicate(self, url: str, content_hash: str) -> bool:
        """Check if article is a duplicate."""
        pass
    
    async def _store_item(
        self,
        source: Source,
        entry: dict,
        content: str,
        content_hash: str
    ) -> RawItem:
        """Store article in database."""
        pass
    
    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize URL for deduplication."""
        # Remove query params, www, trailing slashes
        pass
    
    @staticmethod
    def _compute_hash(content: str) -> str:
        """Compute SHA256 hash of content."""
        return hashlib.sha256(content.encode()).hexdigest()
```

### Rate Limiter

```python
# src/ingestion/rate_limiter.py

import asyncio
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse


class DomainRateLimiter:
    """Rate limiter that tracks requests per domain."""
    
    def __init__(self, requests_per_second: float = 1.0):
        self.min_interval = 1.0 / requests_per_second
        self._last_request: dict[str, datetime] = defaultdict(
            lambda: datetime.min
        )
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
    
    async def acquire(self, url: str) -> None:
        """Wait until we can make a request to this domain."""
        domain = urlparse(url).netloc
        
        async with self._locks[domain]:
            now = datetime.now()
            elapsed = (now - self._last_request[domain]).total_seconds()
            
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            
            self._last_request[domain] = datetime.now()
```

## Testing

### Unit Tests

```python
# tests/unit/ingestion/test_rss_collector.py

import pytest
from unittest.mock import AsyncMock, patch

from src.ingestion.rss_collector import RSSCollector, FeedConfig


class TestRSSCollector:
    """Tests for RSSCollector."""
    
    @pytest.fixture
    def sample_feed_config(self):
        return FeedConfig(
            name="Test Feed",
            url="https://example.com/feed.xml",
            credibility=0.9,
            categories=["test"],
            check_interval_minutes=30,
            max_items_per_fetch=10,
            enabled=True
        )
    
    @pytest.fixture
    def sample_rss_content(self):
        return """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>Test Feed</title>
                <item>
                    <title>Test Article</title>
                    <link>https://example.com/article/1</link>
                    <pubDate>Mon, 15 Jan 2024 10:00:00 GMT</pubDate>
                    <description>Test description</description>
                </item>
            </channel>
        </rss>
        """
    
    async def test_normalize_url_removes_query_params(self):
        """URL normalization should strip query parameters."""
        url = "https://www.example.com/article?utm_source=rss&ref=123"
        normalized = RSSCollector._normalize_url(url)
        assert "utm_source" not in normalized
        assert "ref" not in normalized
    
    async def test_normalize_url_removes_www(self):
        """URL normalization should strip www prefix."""
        url = "https://www.example.com/article"
        normalized = RSSCollector._normalize_url(url)
        assert "www." not in normalized
    
    async def test_compute_hash_is_deterministic(self):
        """Same content should produce same hash."""
        content = "Test article content"
        hash1 = RSSCollector._compute_hash(content)
        hash2 = RSSCollector._compute_hash(content)
        assert hash1 == hash2
    
    async def test_compute_hash_is_unique(self):
        """Different content should produce different hashes."""
        hash1 = RSSCollector._compute_hash("Content A")
        hash2 = RSSCollector._compute_hash("Content B")
        assert hash1 != hash2
    
    # More tests...
```

### Integration Tests

```python
# tests/integration/ingestion/test_rss_collector.py

import pytest
from httpx import AsyncClient

from src.ingestion.rss_collector import RSSCollector


@pytest.mark.integration
class TestRSSCollectorIntegration:
    """Integration tests for RSS collector (hits real feeds)."""
    
    @pytest.fixture
    async def collector(self, db_session, http_client):
        return RSSCollector(
            session=db_session,
            http_client=http_client,
            config_path="tests/fixtures/rss_feeds.yaml"
        )
    
    async def test_collect_real_feed(self, collector):
        """Test collecting from a real RSS feed (BBC)."""
        # Use a stable, reliable feed for testing
        result = await collector.collect_feed(
            FeedConfig(
                name="BBC Test",
                url="http://feeds.bbci.co.uk/news/world/rss.xml",
                credibility=0.9,
                categories=["world"],
                check_interval_minutes=30,
                max_items_per_fetch=5,  # Limit for testing
                enabled=True
            )
        )
        
        assert result.errors == []
        assert result.items_fetched > 0
        assert result.items_stored > 0
```

## Acceptance Criteria Checklist

- [ ] Load feed configs from `config/sources/rss_feeds.yaml`
- [ ] Fetch and parse RSS feeds using feedparser
- [ ] Extract full article text using Trafilatura
- [ ] Deduplicate by URL and content hash
- [ ] Store in `raw_items` table with `processing_status = 'pending'`
- [ ] Handle feed failures gracefully (log, continue)
- [ ] Rate limiting at 1 request/second per domain
- [ ] Unit tests for all core functions
- [ ] Integration test with real BBC feed
- [ ] Logging at appropriate levels (info for success, warning for skip, error for fail)
- [ ] Type hints on all functions
- [ ] Docstrings on public methods

## Notes

- Start with 5-10 well-known, reliable feeds for testing
- Add more sources incrementally after validating the pipeline
- Some sites block bots - handle gracefully and flag in config
- Consider adding User-Agent rotation if needed later
