from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from src.processing.degraded_llm_tracker import (
    DegradedLLMWindow,
    _bucket_start,
    _ModeState,
    _parse_mode_state,
    _serialize_mode_state,
    compute_availability_degraded,
    compute_availability_recovered,
)

pytestmark = pytest.mark.unit

tracker_module = sys.modules["src.processing.degraded_llm_tracker"]


def test_compute_availability_degraded_trips_on_min_failovers() -> None:
    window = DegradedLLMWindow(total_calls=2, secondary_calls=2)
    assert (
        compute_availability_degraded(
            window=window,
            enter_min_failovers=2,
            enter_ratio=0.99,
            enter_min_calls=100,
        )
        is True
    )


def test_compute_availability_degraded_trips_on_ratio_with_min_calls() -> None:
    window = DegradedLLMWindow(total_calls=8, secondary_calls=3)
    assert (
        compute_availability_degraded(
            window=window,
            enter_min_failovers=10,
            enter_ratio=0.25,
            enter_min_calls=6,
        )
        is True
    )


def test_compute_availability_recovered_requires_min_calls() -> None:
    window = DegradedLLMWindow(total_calls=2, secondary_calls=0)
    assert compute_availability_recovered(window=window, exit_ratio=0.0, exit_min_calls=6) is False


def test_compute_availability_recovered_trips_below_ratio() -> None:
    window = DegradedLLMWindow(total_calls=10, secondary_calls=0)
    assert compute_availability_recovered(window=window, exit_ratio=0.0, exit_min_calls=6) is True


def test_failover_ratio_defaults_to_zero_without_calls() -> None:
    assert DegradedLLMWindow(total_calls=0, secondary_calls=10).failover_ratio == 0.0


def test_bucket_start_and_mode_state_helpers_round_trip() -> None:
    assert _bucket_start(123, bucket_seconds=60) == 120
    state = _ModeState(mode="degraded", since_epoch=100)
    assert _parse_mode_state(_serialize_mode_state(state)) == state
    assert _parse_mode_state(None) is None
    assert _parse_mode_state("") is None
    assert _parse_mode_state("{") is None
    assert _parse_mode_state('{"mode":"bad","since_epoch":1}') is None
    assert _parse_mode_state('{"mode":"normal","since_epoch":0}') is None


class _FakePipeline:
    def __init__(self, client: _FakeRedisClient) -> None:
        self._client = client
        self._ops: list[tuple[str, tuple[object, ...]]] = []

    def hincrby(self, key: str, field: str, amount: int) -> _FakePipeline:
        self._ops.append(("hincrby", (key, field, amount)))
        return self

    def expire(self, key: str, ttl: int) -> _FakePipeline:
        self._ops.append(("expire", (key, ttl)))
        return self

    def hmget(self, key: str, *fields: str) -> _FakePipeline:
        self._ops.append(("hmget", (key, *fields)))
        return self

    def execute(self) -> list[object]:
        results: list[object] = []
        for op, args in self._ops:
            if op == "hincrby":
                key, field, amount = args
                bucket = self._client.hashes.setdefault(str(key), {})
                bucket[str(field)] = int(bucket.get(str(field), 0)) + int(amount)
                results.append(bucket[str(field)])
            elif op == "expire":
                key, ttl = args
                self._client.expirations[str(key)] = int(ttl)
                results.append(True)
            elif op == "hmget":
                key = str(args[0])
                fields = [str(field) for field in args[1:]]
                bucket = self._client.hashes.get(key, {})
                results.append([bucket.get(field) for field in fields])
        return results


class _FakeRedisClient:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, int]] = {}
        self.values: dict[str, object] = {}
        self.expirations: dict[str, int] = {}

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.expirations[key] = ttl

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def get(self, key: str) -> object | None:
        return self.values.get(key)

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


def test_record_invocation_records_bucket_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeRedisClient()
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_MODE_ENABLED", True)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_REDIS_PREFIX", "prefix")
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_BUCKET_SECONDS", 60)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_WINDOW_SECONDS", 300)
    tracker = tracker_module.DegradedLLMTracker(
        stage="tier2",
        redis_client=client,
        wall_time_fn=lambda: 125,
    )

    tracker.record_invocation(used_secondary_route=False)
    tracker.record_invocation(used_secondary_route=True)

    bucket_key = "prefix:tier2:bucket:120"
    assert client.hashes[bucket_key] == {"total": 2, "secondary": 1}
    assert client.expirations[bucket_key] == 360


def test_record_invocation_noops_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    tracker = tracker_module.DegradedLLMTracker(redis_client=client)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_MODE_ENABLED", False)

    tracker.record_invocation(used_secondary_route=True)

    client.pipeline.assert_not_called()


def test_record_invocation_logs_warning_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = MagicMock()

    class _BrokenClient:
        def pipeline(self) -> None:
            raise RuntimeError("redis down")

    tracker = tracker_module.DegradedLLMTracker(redis_client=_BrokenClient())
    monkeypatch.setattr(tracker_module, "logger", logger)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_MODE_ENABLED", True)

    tracker.record_invocation(used_secondary_route=True)

    logger.warning.assert_called_once()


def test_quality_latch_and_clear_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeRedisClient()
    logger = MagicMock()
    monkeypatch.setattr(tracker_module, "logger", logger)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_MODE_ENABLED", True)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_REDIS_PREFIX", "prefix")
    tracker = tracker_module.DegradedLLMTracker(stage="tier2", redis_client=client)

    tracker.latch_quality_degraded(ttl_seconds=10, reason="canary_failed")

    assert client.values["prefix:tier2:quality_degraded"] == "1"
    assert client.expirations["prefix:tier2:quality_degraded"] == 60
    tracker.clear_quality_degraded()
    assert "prefix:tier2:quality_degraded" not in client.values
    logger.warning.assert_called_once()


def test_quality_latch_noops_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    tracker = tracker_module.DegradedLLMTracker(redis_client=client)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_MODE_ENABLED", False)

    tracker.latch_quality_degraded(ttl_seconds=30, reason="disabled")

    client.setex.assert_not_called()


def test_quality_latch_logs_warning_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = MagicMock()

    class _BrokenClient:
        def setex(self, _key: str, _ttl: int, _value: str) -> None:
            raise RuntimeError("redis down")

    tracker = tracker_module.DegradedLLMTracker(redis_client=_BrokenClient())
    monkeypatch.setattr(tracker_module, "logger", logger)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_MODE_ENABLED", True)

    tracker.latch_quality_degraded(ttl_seconds=30, reason="broken")

    logger.warning.assert_called_once()


def test_clear_quality_degraded_swallows_errors() -> None:
    class _BrokenClient:
        def delete(self, _key: str) -> None:
            raise RuntimeError("redis down")

    tracker = tracker_module.DegradedLLMTracker(redis_client=_BrokenClient())
    tracker.clear_quality_degraded()


def test_load_window_aggregates_and_ignores_invalid_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeRedisClient()
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_REDIS_PREFIX", "prefix")
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_BUCKET_SECONDS", 60)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_WINDOW_SECONDS", 180)
    client.hashes["prefix:tier2:bucket:180"] = {"total": 2, "secondary": 1}
    client.hashes["prefix:tier2:bucket:120"] = {"total": 3, "secondary": 2}
    tracker = tracker_module.DegradedLLMTracker(stage="tier2", redis_client=client)
    original_pipeline = client.pipeline

    def pipeline_with_invalid_rows() -> _FakePipeline:
        pipeline = original_pipeline()
        original_execute = pipeline.execute

        def execute() -> list[object]:
            return [*original_execute(), "bad-row", [1]]

        pipeline.execute = execute  # type: ignore[assignment]
        return pipeline

    client.pipeline = pipeline_with_invalid_rows  # type: ignore[assignment]
    window = tracker._load_window(now_epoch=181)

    assert window == DegradedLLMWindow(total_calls=5, secondary_calls=3)


def test_mode_state_helpers_and_client_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeRedisClient()
    tracker = tracker_module.DegradedLLMTracker(stage="tier2", redis_client=client)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_REDIS_PREFIX", "prefix")
    tracker._set_mode_state(_ModeState(mode="normal", since_epoch=10))

    assert tracker._load_mode_state() == _ModeState(mode="normal", since_epoch=10)
    client.values[tracker._mode_key()] = None
    assert tracker._load_mode_state() is None
    client.values[tracker._mode_key()] = b'{"mode":"degraded","since_epoch":15}'
    assert tracker._load_mode_state() == _ModeState(mode="degraded", since_epoch=15)
    client.values[tracker._mode_key()] = b"\xff"
    assert tracker._load_mode_state() is None
    client.values[tracker._mode_key()] = 123
    assert tracker._load_mode_state() is None

    lazy_client = _FakeRedisClient()
    from_url = MagicMock(return_value=lazy_client)
    monkeypatch.setattr(tracker_module.redis.Redis, "from_url", from_url)
    lazy_tracker = tracker_module.DegradedLLMTracker(redis_client=None, redis_url="redis://test")
    loaded = lazy_tracker._client()

    assert loaded is lazy_client
    from_url.assert_called_once_with("redis://test", decode_responses=True)


def test_mode_state_helpers_handle_client_errors_and_quality_checks() -> None:
    class _BrokenClient:
        def get(self, _key: str) -> None:
            raise RuntimeError("redis down")

        def set(self, _key: str, _value: str) -> None:
            raise RuntimeError("redis down")

    tracker = tracker_module.DegradedLLMTracker(redis_client=_BrokenClient())

    assert tracker._load_mode_state() is None
    tracker._set_mode_state(_ModeState(mode="normal", since_epoch=1))

    quality_tracker = tracker_module.DegradedLLMTracker(redis_client=_FakeRedisClient())
    quality_tracker._redis.values[quality_tracker._mode_key()] = "x"  # type: ignore[union-attr]
    assert quality_tracker._is_quality_degraded() is False
    quality_tracker._redis.values[
        f"{quality_tracker._redis_prefix}:{quality_tracker.stage}:quality_degraded"
    ] = "1"  # type: ignore[union-attr]
    assert quality_tracker._is_quality_degraded() is True


def test_next_mode_transitions_and_hysteresis(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = tracker_module.DegradedLLMTracker(redis_client=_FakeRedisClient())
    set_state = MagicMock()
    monkeypatch.setattr(tracker, "_set_mode_state", set_state)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_MIN_ACTIVE_SECONDS", 30)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_EXIT_RATIO", 0.1)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_EXIT_MIN_CALLS", 3)

    mode, since = tracker._next_mode(
        now_epoch=100,
        mode_state=None,
        quality_degraded=False,
        availability_degraded=False,
        window=DegradedLLMWindow(total_calls=0, secondary_calls=0),
    )
    assert (mode, since) == ("normal", 100)

    mode, since = tracker._next_mode(
        now_epoch=110,
        mode_state=_ModeState(mode="normal", since_epoch=100),
        quality_degraded=True,
        availability_degraded=False,
        window=DegradedLLMWindow(total_calls=0, secondary_calls=0),
    )
    assert (mode, since) == ("degraded", 110)

    mode, since = tracker._next_mode(
        now_epoch=120,
        mode_state=_ModeState(mode="degraded", since_epoch=110),
        quality_degraded=False,
        availability_degraded=False,
        window=DegradedLLMWindow(total_calls=10, secondary_calls=0),
    )
    assert (mode, since) == ("degraded", 110)

    mode, since = tracker._next_mode(
        now_epoch=150,
        mode_state=_ModeState(mode="degraded", since_epoch=110),
        quality_degraded=False,
        availability_degraded=False,
        window=DegradedLLMWindow(total_calls=10, secondary_calls=0),
    )
    assert (mode, since) == ("normal", 150)
    assert set_state.call_count >= 3


def test_next_mode_handles_invalid_state_and_unrecovered_degraded_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracker = tracker_module.DegradedLLMTracker(redis_client=_FakeRedisClient())
    set_state = MagicMock()
    monkeypatch.setattr(tracker, "_set_mode_state", set_state)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_MIN_ACTIVE_SECONDS", 0)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_EXIT_RATIO", 0.0)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_EXIT_MIN_CALLS", 3)

    mode, since = tracker._next_mode(
        now_epoch=100,
        mode_state=_ModeState(mode="weird", since_epoch=50),  # type: ignore[arg-type]
        quality_degraded=False,
        availability_degraded=False,
        window=DegradedLLMWindow(total_calls=0, secondary_calls=0),
    )
    assert (mode, since) == ("normal", 100)

    mode, since = tracker._next_mode(
        now_epoch=120,
        mode_state=_ModeState(mode="degraded", since_epoch=100),
        quality_degraded=False,
        availability_degraded=False,
        window=DegradedLLMWindow(total_calls=1, secondary_calls=1),
    )
    assert (mode, since) == ("degraded", 100)


def test_evaluate_handles_disabled_and_fail_open_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = tracker_module.DegradedLLMTracker(redis_client=_FakeRedisClient())
    logger = MagicMock()
    monkeypatch.setattr(tracker_module, "logger", logger)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_MODE_ENABLED", False)

    disabled = tracker.evaluate()

    assert disabled.is_degraded is False

    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_MODE_ENABLED", True)
    monkeypatch.setattr(tracker, "_load_window", MagicMock(side_effect=RuntimeError("boom")))

    failed = tracker.evaluate()

    assert failed.is_degraded is False
    logger.warning.assert_called_once()


def test_evaluate_uses_window_quality_and_mode_transition(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = tracker_module.DegradedLLMTracker(stage="tier2", redis_client=_FakeRedisClient())

    def fake_load_window(*, now_epoch: int) -> DegradedLLMWindow:
        _ = now_epoch
        return DegradedLLMWindow(8, 3)

    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_MODE_ENABLED", True)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_ENTER_MIN_FAILOVERS", 2)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_ENTER_RATIO", 0.25)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_ENTER_MIN_CALLS", 4)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_EXIT_RATIO", 0.1)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_EXIT_MIN_CALLS", 4)
    monkeypatch.setattr(tracker_module.settings, "LLM_DEGRADED_MIN_ACTIVE_SECONDS", 0)
    monkeypatch.setattr(tracker, "_load_window", fake_load_window)
    monkeypatch.setattr(tracker, "_is_quality_degraded", lambda: False)
    monkeypatch.setattr(
        tracker, "_load_mode_state", lambda: _ModeState(mode="normal", since_epoch=1)
    )
    monkeypatch.setattr(tracker, "_next_mode", lambda **_: ("degraded", 123))
    monkeypatch.setattr(tracker, "_wall_time_fn", lambda: 200)

    status = tracker.evaluate()

    assert status.stage == "tier2"
    assert status.is_degraded is True
    assert status.availability_degraded is True
    assert status.quality_degraded is False
    assert status.degraded_since_epoch == 123
