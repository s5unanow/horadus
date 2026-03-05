"""
Degraded-mode policy helpers for sustained Tier-2 LLM failover and quality drift.

Design goals:
- Deterministic entry/exit with hysteresis (circuit-breaker style).
- Shared state across workers using Redis time buckets (no Prometheus queries at runtime).
- Conservative default: when in doubt, hold deltas and replay later.
"""

from __future__ import annotations

import json
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

import redis
import structlog

from src.core.config import settings

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DegradedLLMWindow:
    total_calls: int
    secondary_calls: int

    @property
    def failover_ratio(self) -> float:
        if self.total_calls <= 0:
            return 0.0
        return self.secondary_calls / self.total_calls


@dataclass(frozen=True, slots=True)
class DegradedLLMStatus:
    stage: str
    is_degraded: bool
    availability_degraded: bool
    quality_degraded: bool
    window: DegradedLLMWindow
    degraded_since_epoch: int | None = None


@dataclass(frozen=True, slots=True)
class _ModeState:
    mode: str
    since_epoch: int


def _now_epoch() -> int:
    return int(time.time())


def _bucket_start(epoch_seconds: int, *, bucket_seconds: int) -> int:
    return (epoch_seconds // bucket_seconds) * bucket_seconds


def _parse_mode_state(raw: str | None) -> _ModeState | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    mode = str(payload.get("mode", "")).strip().lower()
    since = payload.get("since_epoch")
    if mode not in {"normal", "degraded"}:
        return None
    if not isinstance(since, int) or since <= 0:
        return None
    return _ModeState(mode=mode, since_epoch=since)


def _serialize_mode_state(state: _ModeState) -> str:
    return json.dumps({"mode": state.mode, "since_epoch": state.since_epoch}, ensure_ascii=True)


def compute_availability_degraded(
    *,
    window: DegradedLLMWindow,
    enter_min_failovers: int,
    enter_ratio: float,
    enter_min_calls: int,
) -> bool:
    return (window.secondary_calls >= max(1, enter_min_failovers)) or (
        window.total_calls >= max(1, enter_min_calls)
        and window.failover_ratio >= max(0.0, enter_ratio)
    )


def compute_availability_recovered(
    *,
    window: DegradedLLMWindow,
    exit_ratio: float,
    exit_min_calls: int,
) -> bool:
    if window.total_calls < max(1, exit_min_calls):
        return False
    return window.failover_ratio <= max(0.0, exit_ratio)


class DegradedLLMTracker:
    """
    Shared degraded-mode tracker for one stage (Tier-2 by default).

    Tracks rolling (total, secondary-used) counts using Redis time buckets.
    Separately latches "quality degraded" when the Tier-2 canary fails.
    """

    def __init__(
        self,
        *,
        stage: str = "tier2",
        redis_url: str | None = None,
        redis_client: redis.Redis[str] | None = None,
        wall_time_fn: Any | None = None,
    ) -> None:
        self.stage = stage.strip() or "tier2"
        self._redis_prefix = settings.LLM_DEGRADED_REDIS_PREFIX.strip() or "horadus:llm_degraded"
        self._bucket_seconds = max(10, int(settings.LLM_DEGRADED_BUCKET_SECONDS))
        self._window_seconds = max(60, int(settings.LLM_DEGRADED_WINDOW_SECONDS))
        self._wall_time_fn = wall_time_fn or _now_epoch
        self._redis_url = (redis_url or settings.REDIS_URL).strip()
        self._redis = redis_client

    def record_invocation(self, *, used_secondary_route: bool) -> None:
        if not settings.LLM_DEGRADED_MODE_ENABLED:
            return

        now = int(self._wall_time_fn())
        bucket = _bucket_start(now, bucket_seconds=self._bucket_seconds)
        key = f"{self._redis_prefix}:{self.stage}:bucket:{bucket}"
        try:
            client = self._client()
            pipe = client.pipeline()
            pipe.hincrby(key, "total", 1)
            if used_secondary_route:
                pipe.hincrby(key, "secondary", 1)
            pipe.expire(key, self._window_seconds + self._bucket_seconds)
            pipe.execute()
        except Exception:
            logger.warning(
                "Degraded-mode tracker failed to record invocation; continuing",
                stage=self.stage,
            )

    def latch_quality_degraded(self, *, ttl_seconds: int, reason: str) -> None:
        if not settings.LLM_DEGRADED_MODE_ENABLED:
            return
        ttl = max(60, int(ttl_seconds))
        key = f"{self._redis_prefix}:{self.stage}:quality_degraded"
        try:
            client = self._client()
            client.setex(key, ttl, "1")
            logger.warning(
                "Tier-2 canary latched quality-degraded mode",
                stage=self.stage,
                ttl_seconds=ttl,
                reason=reason,
            )
        except Exception:
            logger.warning(
                "Failed to latch quality-degraded flag in Redis; continuing",
                stage=self.stage,
                ttl_seconds=ttl,
                reason=reason,
            )

    def clear_quality_degraded(self) -> None:
        key = f"{self._redis_prefix}:{self.stage}:quality_degraded"
        try:
            client = self._client()
            client.delete(key)
        except Exception:
            return

    def evaluate(self) -> DegradedLLMStatus:
        """
        Compute current degraded-mode status and update mode latch with hysteresis.

        If Redis is unavailable, this fails open to "normal" (availability unknown),
        but callers should still hold deltas on explicit quality latch.
        """
        if not settings.LLM_DEGRADED_MODE_ENABLED:
            return DegradedLLMStatus(
                stage=self.stage,
                is_degraded=False,
                availability_degraded=False,
                quality_degraded=False,
                window=DegradedLLMWindow(total_calls=0, secondary_calls=0),
                degraded_since_epoch=None,
            )

        now = int(self._wall_time_fn())
        try:
            window = self._load_window(now_epoch=now)
            quality_degraded = self._is_quality_degraded()
            availability_degraded = compute_availability_degraded(
                window=window,
                enter_min_failovers=settings.LLM_DEGRADED_ENTER_MIN_FAILOVERS,
                enter_ratio=settings.LLM_DEGRADED_ENTER_RATIO,
                enter_min_calls=settings.LLM_DEGRADED_ENTER_MIN_CALLS,
            )
            mode_state = self._load_mode_state()
            mode, since = self._next_mode(
                now_epoch=now,
                mode_state=mode_state,
                quality_degraded=quality_degraded,
                availability_degraded=availability_degraded,
                window=window,
            )
            is_degraded = mode == "degraded"
            return DegradedLLMStatus(
                stage=self.stage,
                is_degraded=is_degraded,
                availability_degraded=availability_degraded,
                quality_degraded=quality_degraded,
                window=window,
                degraded_since_epoch=since if is_degraded else None,
            )
        except Exception:
            logger.warning(
                "Degraded-mode tracker evaluation failed; treating as normal",
                stage=self.stage,
            )
            return DegradedLLMStatus(
                stage=self.stage,
                is_degraded=False,
                availability_degraded=False,
                quality_degraded=False,
                window=DegradedLLMWindow(total_calls=0, secondary_calls=0),
                degraded_since_epoch=None,
            )

    def _load_window(self, *, now_epoch: int) -> DegradedLLMWindow:
        bucket_now = _bucket_start(now_epoch, bucket_seconds=self._bucket_seconds)
        buckets: list[int] = []
        for offset in range(0, self._window_seconds, self._bucket_seconds):
            buckets.append(bucket_now - offset)
        keys = [f"{self._redis_prefix}:{self.stage}:bucket:{bucket}" for bucket in buckets]

        client = self._client()
        pipe = client.pipeline()
        for key in keys:
            pipe.hmget(key, "total", "secondary")
        raw_rows = pipe.execute()

        total = 0
        secondary = 0
        for row in raw_rows:
            if not isinstance(row, list) or len(row) != 2:
                continue
            raw_total, raw_secondary = row
            with suppress(TypeError, ValueError):
                total += int(raw_total or 0)
            with suppress(TypeError, ValueError):
                secondary += int(raw_secondary or 0)

        return DegradedLLMWindow(total_calls=max(0, total), secondary_calls=max(0, secondary))

    def _is_quality_degraded(self) -> bool:
        key = f"{self._redis_prefix}:{self.stage}:quality_degraded"
        client = self._client()
        return bool(client.get(key))

    def _mode_key(self) -> str:
        return f"{self._redis_prefix}:{self.stage}:mode"

    def _load_mode_state(self) -> _ModeState | None:
        try:
            raw = self._client().get(self._mode_key())
        except Exception:
            return None
        if raw is None:
            return None
        if isinstance(raw, bytes):
            try:
                raw = raw.decode("utf-8")
            except Exception:
                return None
        return _parse_mode_state(raw if isinstance(raw, str) else None)

    def _set_mode_state(self, state: _ModeState) -> None:
        try:
            self._client().set(self._mode_key(), _serialize_mode_state(state))
        except Exception:
            return

    def _next_mode(
        self,
        *,
        now_epoch: int,
        mode_state: _ModeState | None,
        quality_degraded: bool,
        availability_degraded: bool,
        window: DegradedLLMWindow,
    ) -> tuple[str, int]:
        current = mode_state.mode if mode_state is not None else "normal"
        since = mode_state.since_epoch if mode_state is not None else now_epoch
        if current not in {"normal", "degraded"}:
            current = "normal"
            since = now_epoch

        if current == "normal":
            if quality_degraded or availability_degraded:
                next_state = _ModeState(mode="degraded", since_epoch=now_epoch)
                self._set_mode_state(next_state)
                return ("degraded", next_state.since_epoch)
            self._set_mode_state(_ModeState(mode="normal", since_epoch=since))
            return ("normal", since)

        min_active = max(0, int(settings.LLM_DEGRADED_MIN_ACTIVE_SECONDS))
        if now_epoch - since < min_active:
            return ("degraded", since)

        recovered = (not quality_degraded) and compute_availability_recovered(
            window=window,
            exit_ratio=settings.LLM_DEGRADED_EXIT_RATIO,
            exit_min_calls=settings.LLM_DEGRADED_EXIT_MIN_CALLS,
        )
        if recovered:
            next_state = _ModeState(mode="normal", since_epoch=now_epoch)
            self._set_mode_state(next_state)
            return ("normal", next_state.since_epoch)
        return ("degraded", since)

    def _client(self) -> redis.Redis[str]:
        if self._redis is not None:
            return self._redis
        self._redis = redis.Redis.from_url(self._redis_url, decode_responses=True)
        return self._redis
