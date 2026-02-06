from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.ingestion.rate_limiter import DomainRateLimiter

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_domain_rate_limiter_waits_between_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    sleep_mock = AsyncMock()
    monkeypatch.setattr("src.ingestion.rate_limiter.asyncio.sleep", sleep_mock)

    limiter = DomainRateLimiter(requests_per_second=1.0)

    await limiter.wait("https://example.com/a")
    await limiter.wait("https://example.com/b")

    assert sleep_mock.await_count == 1


def test_domain_rate_limiter_rejects_invalid_rate() -> None:
    with pytest.raises(ValueError, match="requests_per_second must be > 0"):
        DomainRateLimiter(requests_per_second=0)
