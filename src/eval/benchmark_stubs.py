"""No-op collaborators for offline benchmark runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import NoResultFound


@dataclass(slots=True)
class NoopSession:
    """Async-session-shaped object used when benchmark persistence is in memory only."""

    def all(self) -> list[Any]:
        return []

    def one(self) -> Any:
        raise NoResultFound("No rows are available in the benchmark noop session")

    def add(self, _row: Any) -> None:
        return None

    async def execute(self, _statement: Any) -> Any:
        return self

    async def scalars(self, _statement: Any) -> Any:
        return self

    async def flush(self, *_objects: Any) -> None:
        return None


@dataclass(slots=True)
class NoopCostTracker:
    """Cost-tracker-shaped object for benchmark calls without budget persistence."""

    async def ensure_within_budget(
        self,
        _tier: str,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        _ = (provider, model)
        return

    async def record_usage(
        self,
        *,
        tier: str,
        input_tokens: int,
        output_tokens: int,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        _ = (tier, input_tokens, output_tokens, provider, model)
        return
