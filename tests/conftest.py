"""
Pytest configuration and shared fixtures.

This module provides:
- Database fixtures for integration tests
- Mock fixtures for unit tests
- Common test utilities
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

# =============================================================================
# Event Loop Configuration
# =============================================================================


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Create a mock database session for unit tests."""
    session = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock()
    session.scalars = AsyncMock()

    @asynccontextmanager
    async def _nested_transaction() -> Generator[None, None, None]:
        yield

    session.begin_nested = MagicMock(return_value=_nested_transaction())
    return session


@pytest.fixture
def mock_http_client() -> AsyncMock:
    """Create a mock HTTP client for unit tests."""
    return AsyncMock(spec=AsyncClient)


# =============================================================================
# Sample Data Fixtures
# =============================================================================


@pytest.fixture
def sample_source_data() -> dict[str, Any]:
    """Sample source data for testing."""
    return {
        "id": uuid4(),
        "type": "rss",
        "name": "Test Feed",
        "url": "https://example.com/feed.xml",
        "credibility_score": 0.85,
        "config": {"check_interval_minutes": 30},
        "is_active": True,
    }


@pytest.fixture
def sample_raw_item_data() -> dict[str, Any]:
    """Sample raw item data for testing."""
    return {
        "id": uuid4(),
        "source_id": uuid4(),
        "external_id": "https://example.com/article/123",
        "url": "https://example.com/article/123",
        "title": "Test Article Title",
        "raw_content": "This is the full text content of the test article.",
        "content_hash": "abc123def456",
        "processing_status": "pending",
    }


@pytest.fixture
def sample_trend_data() -> dict[str, Any]:
    """Sample trend data for testing."""
    return {
        "id": uuid4(),
        "name": "Test Trend",
        "description": "A test trend for unit testing",
        "definition": {"baseline_probability": 0.1},
        "baseline_log_odds": -2.197,  # 10%
        "current_log_odds": -1.386,  # 20%
        "indicators": {
            "test_signal": {
                "weight": 0.04,
                "direction": "escalatory",
                "keywords": ["test", "signal"],
            }
        },
        "decay_half_life_days": 30,
        "is_active": True,
    }


@pytest.fixture
def sample_event_data() -> dict[str, Any]:
    """Sample event data for testing."""
    return {
        "id": uuid4(),
        "canonical_summary": "Test event summary describing what happened.",
        "extracted_who": ["Actor A", "Actor B"],
        "extracted_what": "Something significant happened",
        "extracted_where": "Test Location",
        "categories": ["test", "sample"],
        "source_count": 3,
    }


# =============================================================================
# RSS Feed Fixtures
# =============================================================================


@pytest.fixture
def sample_rss_xml() -> str:
    """Sample RSS feed XML for testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>Test Feed</title>
        <link>https://example.com</link>
        <description>A test RSS feed</description>
        <item>
            <title>Test Article 1</title>
            <link>https://example.com/article/1</link>
            <pubDate>Mon, 15 Jan 2024 10:00:00 GMT</pubDate>
            <description>Description of article 1</description>
        </item>
        <item>
            <title>Test Article 2</title>
            <link>https://example.com/article/2</link>
            <pubDate>Mon, 15 Jan 2024 11:00:00 GMT</pubDate>
            <description>Description of article 2</description>
        </item>
    </channel>
</rss>
"""


@pytest.fixture
def sample_atom_xml() -> str:
    """Sample Atom feed XML for testing."""
    return """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
    <title>Test Atom Feed</title>
    <link href="https://example.com"/>
    <entry>
        <title>Test Entry 1</title>
        <link href="https://example.com/entry/1"/>
        <published>2024-01-15T10:00:00Z</published>
        <summary>Summary of entry 1</summary>
    </entry>
</feed>
"""


# =============================================================================
# Trend Configuration Fixtures
# =============================================================================


@pytest.fixture
def sample_trend_config() -> dict[str, Any]:
    """Sample trend configuration matching config/trends/*.yaml format."""
    return {
        "id": "test-trend",
        "name": "Test Trend",
        "description": "A trend for testing purposes",
        "baseline_probability": 0.10,
        "decay_half_life_days": 30,
        "indicators": {
            "signal_a": {
                "weight": 0.04,
                "direction": "escalatory",
                "description": "Test signal A",
                "keywords": ["keyword1", "keyword2"],
            },
            "signal_b": {
                "weight": 0.03,
                "direction": "de_escalatory",
                "description": "Test signal B",
                "keywords": ["keyword3", "keyword4"],
            },
        },
        "actors": ["Actor A", "Actor B"],
        "geography": ["Location A", "Location B"],
        "categories": ["category1", "category2"],
    }


# =============================================================================
# Integration Test Markers
# =============================================================================


def pytest_configure(config: pytest.Config) -> None:
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers",
        "unit: Unit tests (fast, no external dependencies)",
    )
    config.addinivalue_line(
        "markers",
        "integration: Integration tests (require database/redis)",
    )
    config.addinivalue_line(
        "markers",
        "slow: Slow tests",
    )
    config.addinivalue_line(
        "markers",
        "external: Tests that call external APIs",
    )
