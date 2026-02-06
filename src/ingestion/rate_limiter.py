"""
Per-domain async rate limiting for ingestion requests.
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse


class DomainRateLimiter:
    """
    Limits requests to a configurable rate per domain.
    """

    def __init__(self, requests_per_second: float = 1.0) -> None:
        if requests_per_second <= 0:
            msg = "requests_per_second must be > 0"
            raise ValueError(msg)
        self._interval_seconds = 1.0 / requests_per_second
        self._last_request_at: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def wait(self, url: str) -> None:
        """
        Waits if needed so requests to the same domain respect the configured rate.
        """
        domain = urlparse(url).netloc.lower() or "unknown-domain"
        lock = self._locks.setdefault(domain, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            last_request_at = self._last_request_at.get(domain)
            if last_request_at is not None:
                elapsed = now - last_request_at
                remaining = self._interval_seconds - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)
            self._last_request_at[domain] = time.monotonic()
