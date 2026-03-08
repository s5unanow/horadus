from __future__ import annotations

from contextlib import suppress
from unittest.mock import AsyncMock

import pytest

from src.ingestion.rate_limiter import DomainRateLimiter

pytestmark = pytest.mark.unit


def _monotonic_from(values: list[float]):
    last = values[-1]
    sequence = iter(values)

    def _fake() -> float:
        nonlocal last
        with suppress(StopIteration):
            last = next(sequence)
        return last

    return _fake


@pytest.mark.asyncio
async def test_domain_rate_limiter_waits_between_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    sleep_mock = AsyncMock()
    monkeypatch.setattr("src.ingestion.rate_limiter.asyncio.sleep", sleep_mock)
    monkeypatch.setattr(
        "src.ingestion.rate_limiter.time.monotonic",
        _monotonic_from([0.0, 0.0, 0.5, 1.0]),
    )

    limiter = DomainRateLimiter(requests_per_second=1.0)

    await limiter.wait("https://example.com/a")
    await limiter.wait("https://example.com/b")

    assert sleep_mock.await_count == 1


def test_domain_rate_limiter_rejects_invalid_rate() -> None:
    with pytest.raises(ValueError, match="requests_per_second must be > 0"):
        DomainRateLimiter(requests_per_second=0)


@pytest.mark.asyncio
async def test_domain_rate_limiter_skips_sleep_when_interval_elapsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleep_mock = AsyncMock()
    monkeypatch.setattr("src.ingestion.rate_limiter.asyncio.sleep", sleep_mock)
    monkeypatch.setattr(
        "src.ingestion.rate_limiter.time.monotonic",
        _monotonic_from([0.0, 0.0, 1.5, 1.5]),
    )

    limiter = DomainRateLimiter(requests_per_second=1.0)

    await limiter.wait("https://example.com/a")
    await limiter.wait("https://example.com/b")

    sleep_mock.assert_not_awaited()
