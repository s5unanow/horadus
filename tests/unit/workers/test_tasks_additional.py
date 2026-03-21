from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import src.workers.tasks as tasks_module
from src.core.source_freshness import SourceFreshnessReport, SourceFreshnessRow
from src.storage.event_state import EventActivityState

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def stub_worker_heartbeat_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_from_url(*args, **kwargs):
        del args, kwargs
        return MagicMock()

    monkeypatch.setattr(tasks_module.redis, "from_url", fake_from_url)


def _session_maker(session: object):
    @asynccontextmanager
    async def _manager():
        yield session

    return _manager


@dataclass(slots=True)
class FakeCollectorResult:
    items_fetched: int
    items_stored: int
    items_skipped: int
    errors: list[str]
    transient_errors: int = 0
    terminal_errors: int = 0


class FakeTracker:
    def __init__(self, *, stage: str) -> None:
        self.stage = stage
        self.latch_calls: list[tuple[int, str]] = []
        self.clear_calls = 0

    def latch_quality_degraded(self, *, ttl_seconds: int, reason: str) -> None:
        self.latch_calls.append((ttl_seconds, reason))

    def clear_quality_degraded(self) -> None:
        self.clear_calls += 1


def test_typed_shared_task_wraps_celery_decorator(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_shared_task(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

        def _decorator(func):
            return {"wrapped": func.__name__}

        return _decorator

    monkeypatch.setattr(tasks_module, "shared_task", fake_shared_task)

    def sample() -> None:
        return None

    wrapped = tasks_module.typed_shared_task(name="workers.sample")(sample)

    assert wrapped == {"wrapped": "sample"}
    assert captured["kwargs"] == {"name": "workers.sample"}


def test_run_async_delegates_to_asyncio_run(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def fake_run(coro):
        seen["name"] = coro.cr_code.co_name
        coro.close()
        return {"status": "ok"}

    monkeypatch.setattr(tasks_module.asyncio, "run", fake_run)

    async def sample() -> dict[str, str]:
        return {"status": "ok"}

    assert tasks_module._run_async(sample()) == {"status": "ok"}
    assert seen["name"] == "sample"


def test_processing_in_flight_helpers_return_zero_on_redis_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tasks_module, "_get_redis_client", MagicMock(side_effect=RuntimeError("boom"))
    )

    assert tasks_module._increment_processing_in_flight() == 0
    assert tasks_module._decrement_processing_in_flight() == 0


def test_push_dead_letter_logs_error_and_closes_client(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = MagicMock()
    fake_redis.lpush.side_effect = RuntimeError("boom")
    logged: list[str] = []

    monkeypatch.setattr(tasks_module.redis, "from_url", MagicMock(return_value=fake_redis))
    monkeypatch.setattr(tasks_module.logger, "exception", lambda message: logged.append(message))

    tasks_module._push_dead_letter({"task_name": "workers.collect_rss"})

    assert logged == ["Failed to push dead letter payload"]
    fake_redis.close.assert_called_once()


def test_record_worker_activity_sets_payload_and_truncates_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = MagicMock()
    monkeypatch.setattr(tasks_module.redis, "from_url", MagicMock(return_value=fake_redis))
    monkeypatch.setattr(tasks_module.settings, "WORKER_HEARTBEAT_REDIS_KEY", "worker:heartbeat")
    monkeypatch.setattr(tasks_module.settings, "WORKER_HEARTBEAT_TTL_SECONDS", 5)

    tasks_module._record_worker_activity(
        task_name="workers.sample",
        status="failed",
        error="x" * 700,
    )

    assert fake_redis.set.call_count == 1
    key, payload = fake_redis.set.call_args.args[:2]
    assert key == "worker:heartbeat"
    assert '"task": "workers.sample"' in payload
    assert '"status": "failed"' in payload
    assert '"error": "' in payload
    assert fake_redis.set.call_args.kwargs["ex"] == 60
    fake_redis.close.assert_called_once()


def test_record_worker_activity_logs_when_redis_write_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = MagicMock()
    fake_redis.set.side_effect = RuntimeError("redis down")
    logged: list[tuple[str, str, str]] = []

    monkeypatch.setattr(tasks_module.redis, "from_url", MagicMock(return_value=fake_redis))
    monkeypatch.setattr(
        tasks_module.logger,
        "exception",
        lambda message, *, task_name, status: logged.append((message, task_name, status)),
    )

    tasks_module._record_worker_activity(task_name="workers.sample", status="started")

    assert logged == [("Failed to record worker heartbeat", "workers.sample", "started")]
    fake_redis.close.assert_called_once()


def test_handle_task_failure_skips_intermediate_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    pushed: list[dict[str, object]] = []
    recorded: list[str] = []
    sender = SimpleNamespace(
        name="workers.sample",
        max_retries=3,
        request=SimpleNamespace(retries=1),
    )

    monkeypatch.setattr(tasks_module, "_push_dead_letter", lambda payload: pushed.append(payload))
    monkeypatch.setattr(
        tasks_module,
        "record_worker_error",
        lambda *, task_name: recorded.append(task_name),
    )

    tasks_module._handle_task_failure(sender=sender, task_id="abc", exception=RuntimeError("boom"))

    assert pushed == []
    assert recorded == []


def test_handle_task_failure_records_terminal_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    pushed: list[dict[str, object]] = []
    recorded: list[str] = []
    sender = SimpleNamespace(
        name="workers.sample",
        max_retries="invalid",
        request=SimpleNamespace(retries=5),
    )

    monkeypatch.setattr(tasks_module, "_push_dead_letter", lambda payload: pushed.append(payload))
    monkeypatch.setattr(
        tasks_module,
        "record_worker_error",
        lambda *, task_name: recorded.append(task_name),
    )

    tasks_module._handle_task_failure(
        sender=sender,
        task_id="abc",
        exception=RuntimeError("boom"),
        args=("x",),
        kwargs={"key": "value"},
    )

    assert recorded == ["workers.sample"]
    assert pushed[0]["task_name"] == "workers.sample"
    assert pushed[0]["task_id"] == "abc"
    assert pushed[0]["exception_type"] == "RuntimeError"
    assert pushed[0]["exception_message"] == "boom"
    assert pushed[0]["args"] == ("x",)
    assert pushed[0]["kwargs"] == {"key": "value"}
    assert pushed[0]["retries"] == 5


def test_push_dead_letter_handles_redis_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: list[str] = []

    monkeypatch.setattr(tasks_module.redis, "from_url", MagicMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(tasks_module.logger, "exception", lambda message: logged.append(message))

    tasks_module._push_dead_letter({"task_name": "workers.collect_rss"})

    assert logged == ["Failed to push dead letter payload"]


def test_record_worker_activity_handles_redis_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: list[tuple[str, str, str]] = []

    monkeypatch.setattr(tasks_module.redis, "from_url", MagicMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(
        tasks_module.logger,
        "exception",
        lambda message, *, task_name, status: logged.append((message, task_name, status)),
    )

    tasks_module._record_worker_activity(task_name="workers.sample", status="started")

    assert logged == [("Failed to record worker heartbeat", "workers.sample", "started")]


@pytest.mark.parametrize(
    ("stored_items", "pending_backlog", "in_flight", "budget_status", "expected_reason"),
    [
        (0, 12, 1, "active", "no_new_items"),
        (5, 12, 0, "sleep_mode", "budget_denied"),
    ],
)
def test_build_processing_dispatch_plan_non_dispatch_cases(
    monkeypatch: pytest.MonkeyPatch,
    stored_items: int,
    pending_backlog: int,
    in_flight: int,
    budget_status: str,
    expected_reason: str,
) -> None:
    monkeypatch.setattr(tasks_module.settings, "ENABLE_PROCESSING_PIPELINE", True)

    plan = tasks_module._build_processing_dispatch_plan(
        stored_items=stored_items,
        pending_backlog=pending_backlog,
        in_flight=in_flight,
        budget_status=budget_status,
        budget_remaining_usd=1.0,
        daily_cost_limit_usd=10.0,
    )

    assert plan.should_dispatch is False
    assert plan.reason == expected_reason
    assert plan.task_limit == 0


def test_build_processing_dispatch_plan_respects_pipeline_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks_module.settings, "ENABLE_PROCESSING_PIPELINE", False)

    plan = tasks_module._build_processing_dispatch_plan(
        stored_items=5,
        pending_backlog=20,
        in_flight=0,
        budget_status="active",
        budget_remaining_usd=5.0,
        daily_cost_limit_usd=10.0,
    )

    assert plan.should_dispatch is False
    assert plan.reason == "pipeline_disabled"


def test_build_processing_dispatch_plan_respects_in_flight_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks_module.settings, "ENABLE_PROCESSING_PIPELINE", True)
    monkeypatch.setattr(tasks_module.settings, "PROCESSING_DISPATCH_MAX_IN_FLIGHT", 2)

    plan = tasks_module._build_processing_dispatch_plan(
        stored_items=5,
        pending_backlog=20,
        in_flight=2,
        budget_status="active",
        budget_remaining_usd=5.0,
        daily_cost_limit_usd=10.0,
    )

    assert plan.should_dispatch is False
    assert plan.reason == "in_flight_throttle"


def test_retention_eligibility_helpers_handle_missing_event_dates() -> None:
    cutoffs = tasks_module.RetentionCutoffs(
        now=datetime(2026, 2, 18, 12, 0, tzinfo=UTC),
        raw_item_noise_before=datetime(2026, 1, 1, tzinfo=UTC),
        raw_item_archived_event_before=datetime(2025, 11, 1, tzinfo=UTC),
        archived_event_before=datetime(2025, 8, 1, tzinfo=UTC),
        trend_evidence_before=datetime(2025, 2, 1, tzinfo=UTC),
        batch_size=10,
        dry_run=True,
    )

    assert not tasks_module._is_raw_item_archived_event_retention_eligible(
        fetched_at=datetime(2025, 10, 1, tzinfo=UTC),
        event_activity_state=EventActivityState.CLOSED.value,
        event_last_mention_at=None,
        cutoffs=cutoffs,
    )
    assert not tasks_module._is_trend_evidence_retention_eligible(
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        event_activity_state=EventActivityState.CLOSED.value,
        event_last_mention_at=None,
        cutoffs=cutoffs,
    )


def test_processing_in_flight_count_handles_negative_and_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = MagicMock()
    fake_redis.get.return_value = "-5"
    monkeypatch.setattr(tasks_module, "_get_redis_client", lambda: fake_redis)
    assert tasks_module._get_processing_in_flight_count() == 0
    fake_redis.close.assert_called_once()

    monkeypatch.setattr(
        tasks_module, "_get_redis_client", MagicMock(side_effect=RuntimeError("boom"))
    )
    assert tasks_module._get_processing_in_flight_count() == 0


def test_processing_in_flight_increment_and_decrement(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = MagicMock()
    fake_redis.incr.return_value = 3
    fake_redis.decr.side_effect = [2, 0]
    monkeypatch.setattr(tasks_module, "_get_redis_client", lambda: fake_redis)

    assert tasks_module._increment_processing_in_flight() == 3
    fake_redis.expire.assert_called_once_with(tasks_module.PROCESSING_IN_FLIGHT_KEY, 3600)
    assert tasks_module._decrement_processing_in_flight() == 2
    assert tasks_module._decrement_processing_in_flight() == 0
    fake_redis.delete.assert_called_once_with(tasks_module.PROCESSING_IN_FLIGHT_KEY)


def test_acquire_processing_dispatch_lock_handles_zero_ttl_and_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks_module.settings, "PROCESSING_DISPATCH_LOCK_TTL_SECONDS", 0)
    assert tasks_module._acquire_processing_dispatch_lock() is True

    monkeypatch.setattr(tasks_module.settings, "PROCESSING_DISPATCH_LOCK_TTL_SECONDS", 30)
    fake_redis = MagicMock()
    fake_redis.set.return_value = False
    monkeypatch.setattr(tasks_module, "_get_redis_client", lambda: fake_redis)
    assert tasks_module._acquire_processing_dispatch_lock() is False
    fake_redis.close.assert_called_once()

    monkeypatch.setattr(
        tasks_module, "_get_redis_client", MagicMock(side_effect=RuntimeError("boom"))
    )
    assert tasks_module._acquire_processing_dispatch_lock() is True


@pytest.mark.asyncio
async def test_load_processing_dispatch_inputs_async_uses_cost_tracker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_session = AsyncMock()
    mock_session.scalar.return_value = 7

    class FakeCostTracker:
        def __init__(self, *, session) -> None:
            assert session is mock_session

        async def get_daily_summary(self) -> dict[str, object]:
            return {
                "status": "active",
                "budget_remaining_usd": 3.25,
                "daily_cost_limit_usd": 9,
            }

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(tasks_module, "CostTracker", FakeCostTracker)

    result = await tasks_module._load_processing_dispatch_inputs_async()

    assert result == {
        "pending_backlog": 7,
        "budget_status": "active",
        "budget_remaining_usd": 3.25,
        "daily_cost_limit_usd": 9.0,
    }


@pytest.mark.asyncio
async def test_collect_rss_async_aggregates_results(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_session = AsyncMock()
    http_client = object()
    seen: dict[str, object] = {}

    class FakeAsyncClient:
        async def __aenter__(self):
            return http_client

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeCollector:
        def __init__(self, *, session, http_client) -> None:
            seen["session"] = session
            seen["http_client"] = http_client

        async def collect_all(self) -> list[FakeCollectorResult]:
            return [
                FakeCollectorResult(3, 2, 1, [], transient_errors=1, terminal_errors=0),
                FakeCollectorResult(2, 1, 0, ["x"], transient_errors=0, terminal_errors=1),
            ]

    monkeypatch.setattr(tasks_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(tasks_module, "RSSCollector", FakeCollector)

    result = await tasks_module._collect_rss_async()

    assert result["collector"] == "rss"
    assert result["fetched"] == 5
    assert result["stored"] == 3
    assert result["skipped"] == 1
    assert result["errors"] == 1
    assert result["transient_errors"] == 1
    assert result["terminal_errors"] == 1
    assert result["sources_succeeded"] == 1
    assert result["sources_failed"] == 1
    assert seen == {"session": mock_session, "http_client": http_client}
    assert mock_session.commit.await_count == 1


@pytest.mark.asyncio
async def test_collect_gdelt_async_aggregates_results(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_session = AsyncMock()

    class FakeAsyncClient:
        async def __aenter__(self):
            return "client"

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeCollector:
        def __init__(self, *, session, http_client) -> None:
            assert session is mock_session
            assert http_client == "client"

        async def collect_all(self) -> list[FakeCollectorResult]:
            return [FakeCollectorResult(4, 4, 0, [])]

    monkeypatch.setattr(tasks_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(tasks_module, "GDELTClient", FakeCollector)

    result = await tasks_module._collect_gdelt_async()

    assert result["collector"] == "gdelt"
    assert result["fetched"] == 4
    assert result["stored"] == 4
    assert result["sources_succeeded"] == 1
    assert result["sources_failed"] == 0
    assert mock_session.commit.await_count == 1


def test_queue_processing_for_new_items_dispatches_when_plan_allows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks_module.settings, "ENABLE_PROCESSING_PIPELINE", True)
    monkeypatch.setattr(tasks_module.settings, "PROCESSING_PIPELINE_BATCH_SIZE", 25)

    def fake_run_async(coro):
        coro.close()
        return {
            "pending_backlog": 12,
            "budget_status": "active",
            "budget_remaining_usd": 4.0,
            "daily_cost_limit_usd": 10.0,
        }

    decisions: list[tuple[bool, str]] = []
    queued: list[int] = []

    monkeypatch.setattr(tasks_module, "_run_async", fake_run_async)
    monkeypatch.setattr(tasks_module, "_get_processing_in_flight_count", lambda: 0)
    monkeypatch.setattr(tasks_module, "_acquire_processing_dispatch_lock", lambda: True)
    monkeypatch.setattr(tasks_module, "record_processing_backlog_depth", lambda **_: None)
    monkeypatch.setattr(
        tasks_module,
        "record_processing_dispatch_decision",
        lambda *, dispatched, reason: decisions.append((dispatched, reason)),
    )
    monkeypatch.setattr(
        tasks_module,
        "process_pending_items",
        MagicMock(delay=lambda *, limit: queued.append(limit)),
    )

    dispatched = tasks_module._queue_processing_for_new_items(collector="rss", stored_items=6)

    assert dispatched is True
    assert queued == [12]
    assert decisions == [(True, "ok")]


def test_queue_processing_for_new_items_logs_non_dispatch_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks_module.settings, "ENABLE_PROCESSING_PIPELINE", True)

    def fake_run_async(coro):
        coro.close()
        return {
            "pending_backlog": 8,
            "budget_status": "sleep_mode",
            "budget_remaining_usd": 0.0,
            "daily_cost_limit_usd": 10.0,
        }

    decisions: list[tuple[bool, str]] = []

    monkeypatch.setattr(tasks_module, "_run_async", fake_run_async)
    monkeypatch.setattr(tasks_module, "_get_processing_in_flight_count", lambda: 0)
    monkeypatch.setattr(tasks_module, "_acquire_processing_dispatch_lock", lambda: True)
    monkeypatch.setattr(tasks_module, "record_processing_backlog_depth", lambda **_: None)
    monkeypatch.setattr(
        tasks_module,
        "record_processing_dispatch_decision",
        lambda *, dispatched, reason: decisions.append((dispatched, reason)),
    )
    monkeypatch.setattr(tasks_module, "process_pending_items", MagicMock(delay=MagicMock()))

    dispatched = tasks_module._queue_processing_for_new_items(collector="rss", stored_items=3)

    assert dispatched is False
    assert decisions == [(False, "budget_denied")]


@pytest.mark.asyncio
async def test_check_source_freshness_async_respects_zero_dispatch_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked_at = datetime(2026, 2, 16, 12, 0, tzinfo=UTC)
    report = SourceFreshnessReport(
        checked_at=checked_at,
        stale_multiplier=2.0,
        rows=(
            SourceFreshnessRow(
                source_id=uuid4(),
                source_name="RSS Source",
                collector="rss",
                last_fetched_at=None,
                age_seconds=100,
                stale_after_seconds=50,
                is_stale=True,
            ),
        ),
    )
    mock_session = AsyncMock()
    stale_metrics: list[tuple[str, int]] = []

    async def fake_report(*, session: object) -> SourceFreshnessReport:
        assert session is mock_session
        return report

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(tasks_module, "build_source_freshness_report", fake_report)
    monkeypatch.setattr(tasks_module.settings, "SOURCE_FRESHNESS_MAX_CATCHUP_DISPATCHES", 0)
    monkeypatch.setattr(
        tasks_module,
        "record_source_freshness_stale",
        lambda *, collector, stale_count: stale_metrics.append((collector, stale_count)),
    )
    monkeypatch.setattr(tasks_module, "record_source_catchup_dispatch", lambda **_: None)
    monkeypatch.setattr(tasks_module, "collect_rss", MagicMock(delay=MagicMock()))

    result = await tasks_module._check_source_freshness_async()

    assert result["catchup_dispatch_budget"] == 0
    assert result["catchup_dispatched"] == []
    assert result["stale_sources"][0]["last_fetched_at"] is None
    assert stale_metrics == [("rss", 1)]


@pytest.mark.asyncio
async def test_check_source_freshness_async_dispatches_gdelt_without_rss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked_at = datetime(2026, 2, 16, 12, 0, tzinfo=UTC)
    report = SourceFreshnessReport(
        checked_at=checked_at,
        stale_multiplier=2.0,
        rows=(
            SourceFreshnessRow(
                source_id=uuid4(),
                source_name="GDELT Source",
                collector="gdelt",
                last_fetched_at=checked_at - timedelta(hours=5),
                age_seconds=18000,
                stale_after_seconds=7200,
                is_stale=True,
            ),
        ),
    )
    mock_session = AsyncMock()
    gdelt_dispatches: list[str] = []

    async def fake_report(*, session: object) -> SourceFreshnessReport:
        assert session is mock_session
        return report

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(tasks_module, "build_source_freshness_report", fake_report)
    monkeypatch.setattr(tasks_module.settings, "SOURCE_FRESHNESS_MAX_CATCHUP_DISPATCHES", 2)
    monkeypatch.setattr(tasks_module.settings, "ENABLE_RSS_INGESTION", False)
    monkeypatch.setattr(tasks_module.settings, "ENABLE_GDELT_INGESTION", True)
    monkeypatch.setattr(tasks_module, "record_source_freshness_stale", lambda **_: None)
    monkeypatch.setattr(tasks_module, "record_source_catchup_dispatch", lambda **_: None)
    monkeypatch.setattr(
        tasks_module,
        "collect_gdelt",
        MagicMock(delay=lambda: gdelt_dispatches.append("gdelt")),
    )

    result = await tasks_module._check_source_freshness_async()

    assert result["catchup_dispatched"] == ["gdelt"]
    assert gdelt_dispatches == ["gdelt"]


@pytest.mark.asyncio
async def test_process_pending_async_without_degraded_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_session = AsyncMock()
    seen: dict[str, object] = {}

    class FakeTier2Classifier:
        def __init__(self, *, session, model) -> None:
            seen["tier2_session"] = session
            seen["tier2_model"] = model

    class FakePipeline:
        def __init__(self, *, session, tier2_classifier, degraded_llm_tracker) -> None:
            seen["pipeline_session"] = session
            seen["degraded_tracker"] = degraded_llm_tracker

        async def process_pending_items(self, *, limit: int):
            seen["limit"] = limit
            return {"scanned": limit, "processed": limit}

        @staticmethod
        def run_result_to_dict(run_result):
            return run_result

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(tasks_module.settings, "LLM_DEGRADED_MODE_ENABLED", False)
    monkeypatch.setattr(tasks_module, "Tier2Classifier", FakeTier2Classifier)
    monkeypatch.setattr(tasks_module, "ProcessingPipeline", FakePipeline)

    result = await tasks_module._process_pending_async(limit=5)

    assert result == {
        "status": "ok",
        "task": "processing_pipeline",
        "scanned": 5,
        "processed": 5,
    }
    assert seen["tier2_model"] == tasks_module.settings.LLM_TIER2_MODEL
    assert seen["degraded_tracker"] is None
    assert mock_session.commit.await_count == 1


@pytest.mark.asyncio
async def test_process_pending_async_handles_primary_canary_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_session = AsyncMock()
    tracker_holder: dict[str, FakeTracker] = {}

    def fake_tracker(*, stage: str) -> FakeTracker:
        tracker = FakeTracker(stage=stage)
        tracker_holder["tracker"] = tracker
        return tracker

    class FakeTier2Classifier:
        def __init__(self, *, session, model) -> None:
            self.model = model

    class FakePipeline:
        def __init__(self, *, session, tier2_classifier, degraded_llm_tracker) -> None:
            self.tier2_classifier = tier2_classifier

        async def process_pending_items(self, *, limit: int):
            return {"model": self.tier2_classifier.model, "processed": limit}

        @staticmethod
        def run_result_to_dict(run_result):
            return run_result

    async def fake_canary(**_kwargs):
        raise RuntimeError("primary down")

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(tasks_module.settings, "LLM_DEGRADED_MODE_ENABLED", True)
    monkeypatch.setattr(tasks_module.settings, "LLM_DEGRADED_CANARY_ENABLED", True)
    monkeypatch.setattr(tasks_module, "DegradedLLMTracker", fake_tracker)
    monkeypatch.setattr(tasks_module, "run_tier2_canary", fake_canary)
    monkeypatch.setattr(tasks_module, "Tier2Classifier", FakeTier2Classifier)
    monkeypatch.setattr(tasks_module, "ProcessingPipeline", FakePipeline)

    result = await tasks_module._process_pending_async(limit=2)

    assert result["model"] == tasks_module.settings.LLM_TIER2_MODEL
    assert tracker_holder["tracker"].latch_calls == [
        (
            tasks_module.settings.LLM_DEGRADED_CANARY_QUALITY_TTL_SECONDS,
            "primary_canary_error:RuntimeError",
        )
    ]


@pytest.mark.asyncio
async def test_process_pending_async_clears_quality_on_primary_canary_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_session = AsyncMock()
    tracker_holder: dict[str, FakeTracker] = {}

    def fake_tracker(*, stage: str) -> FakeTracker:
        tracker = FakeTracker(stage=stage)
        tracker_holder["tracker"] = tracker
        return tracker

    class FakeTier2Classifier:
        def __init__(self, *, session, model) -> None:
            self.model = model

    class FakePipeline:
        def __init__(self, *, session, tier2_classifier, degraded_llm_tracker) -> None:
            self.tier2_classifier = tier2_classifier

        async def process_pending_items(self, *, limit: int):
            return {"model": self.tier2_classifier.model}

        @staticmethod
        def run_result_to_dict(run_result):
            return run_result

    async def fake_canary(**_kwargs):
        return SimpleNamespace(passed=True, reason="ok")

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(tasks_module.settings, "LLM_DEGRADED_MODE_ENABLED", True)
    monkeypatch.setattr(tasks_module.settings, "LLM_DEGRADED_CANARY_ENABLED", True)
    monkeypatch.setattr(tasks_module, "DegradedLLMTracker", fake_tracker)
    monkeypatch.setattr(tasks_module, "run_tier2_canary", fake_canary)
    monkeypatch.setattr(tasks_module, "Tier2Classifier", FakeTier2Classifier)
    monkeypatch.setattr(tasks_module, "ProcessingPipeline", FakePipeline)

    await tasks_module._process_pending_async(limit=1)

    assert tracker_holder["tracker"].clear_calls == 1
    assert tracker_holder["tracker"].latch_calls == []


@pytest.mark.asyncio
async def test_process_pending_async_uses_emergency_model_on_canary_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_session = AsyncMock()
    tracker_holder: dict[str, FakeTracker] = {}
    canary_models: list[str] = []

    def fake_tracker(*, stage: str) -> FakeTracker:
        tracker = FakeTracker(stage=stage)
        tracker_holder["tracker"] = tracker
        return tracker

    class FakeTier2Classifier:
        def __init__(self, *, session, model) -> None:
            self.model = model

    class FakePipeline:
        def __init__(self, *, session, tier2_classifier, degraded_llm_tracker) -> None:
            self.tier2_classifier = tier2_classifier

        async def process_pending_items(self, *, limit: int):
            return {"model": self.tier2_classifier.model}

        @staticmethod
        def run_result_to_dict(run_result):
            return run_result

    async def fake_canary(**kwargs):
        canary_models.append(kwargs["model"])
        if len(canary_models) == 1:
            return SimpleNamespace(passed=False, reason="primary_bad")
        return SimpleNamespace(passed=True, reason="emergency_ok")

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(tasks_module.settings, "LLM_DEGRADED_MODE_ENABLED", True)
    monkeypatch.setattr(tasks_module.settings, "LLM_DEGRADED_CANARY_ENABLED", True)
    monkeypatch.setattr(tasks_module.settings, "LLM_TIER2_EMERGENCY_MODEL", "emergency-model")
    monkeypatch.setattr(tasks_module, "DegradedLLMTracker", fake_tracker)
    monkeypatch.setattr(tasks_module, "run_tier2_canary", fake_canary)
    monkeypatch.setattr(tasks_module, "Tier2Classifier", FakeTier2Classifier)
    monkeypatch.setattr(tasks_module, "ProcessingPipeline", FakePipeline)

    result = await tasks_module._process_pending_async(limit=1)

    assert canary_models == [
        tasks_module.settings.LLM_TIER2_MODEL,
        "emergency-model",
    ]
    assert result["model"] == "emergency-model"
    assert tracker_holder["tracker"].clear_calls == 1


@pytest.mark.asyncio
async def test_process_pending_async_latches_when_primary_fails_without_emergency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_session = AsyncMock()
    tracker_holder: dict[str, FakeTracker] = {}

    def fake_tracker(*, stage: str) -> FakeTracker:
        tracker = FakeTracker(stage=stage)
        tracker_holder["tracker"] = tracker
        return tracker

    class FakeTier2Classifier:
        def __init__(self, *, session, model) -> None:
            self.model = model

    class FakePipeline:
        def __init__(self, *, session, tier2_classifier, degraded_llm_tracker) -> None:
            self.tier2_classifier = tier2_classifier

        async def process_pending_items(self, *, limit: int):
            return {"model": self.tier2_classifier.model}

        @staticmethod
        def run_result_to_dict(run_result):
            return run_result

    async def fake_canary(**_kwargs):
        return SimpleNamespace(passed=False, reason="primary_bad")

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(tasks_module.settings, "LLM_DEGRADED_MODE_ENABLED", True)
    monkeypatch.setattr(tasks_module.settings, "LLM_DEGRADED_CANARY_ENABLED", True)
    monkeypatch.setattr(tasks_module.settings, "LLM_TIER2_EMERGENCY_MODEL", "   ")
    monkeypatch.setattr(tasks_module, "DegradedLLMTracker", fake_tracker)
    monkeypatch.setattr(tasks_module, "run_tier2_canary", fake_canary)
    monkeypatch.setattr(tasks_module, "Tier2Classifier", FakeTier2Classifier)
    monkeypatch.setattr(tasks_module, "ProcessingPipeline", FakePipeline)

    await tasks_module._process_pending_async(limit=1)

    assert tracker_holder["tracker"].latch_calls == [
        (
            tasks_module.settings.LLM_DEGRADED_CANARY_QUALITY_TTL_SECONDS,
            "primary:primary_bad",
        )
    ]


@pytest.mark.asyncio
async def test_process_pending_async_latches_when_emergency_canary_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_session = AsyncMock()
    tracker_holder: dict[str, FakeTracker] = {}
    calls = {"count": 0}

    def fake_tracker(*, stage: str) -> FakeTracker:
        tracker = FakeTracker(stage=stage)
        tracker_holder["tracker"] = tracker
        return tracker

    class FakeTier2Classifier:
        def __init__(self, *, session, model) -> None:
            self.model = model

    class FakePipeline:
        def __init__(self, *, session, tier2_classifier, degraded_llm_tracker) -> None:
            self.tier2_classifier = tier2_classifier

        async def process_pending_items(self, *, limit: int):
            return {"model": self.tier2_classifier.model}

        @staticmethod
        def run_result_to_dict(run_result):
            return run_result

    async def fake_canary(**_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return SimpleNamespace(passed=False, reason="primary_bad")
        raise RuntimeError("emergency down")

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(tasks_module.settings, "LLM_DEGRADED_MODE_ENABLED", True)
    monkeypatch.setattr(tasks_module.settings, "LLM_DEGRADED_CANARY_ENABLED", True)
    monkeypatch.setattr(tasks_module.settings, "LLM_TIER2_EMERGENCY_MODEL", "emergency-model")
    monkeypatch.setattr(tasks_module, "DegradedLLMTracker", fake_tracker)
    monkeypatch.setattr(tasks_module, "run_tier2_canary", fake_canary)
    monkeypatch.setattr(tasks_module, "Tier2Classifier", FakeTier2Classifier)
    monkeypatch.setattr(tasks_module, "ProcessingPipeline", FakePipeline)

    await tasks_module._process_pending_async(limit=1)

    assert tracker_holder["tracker"].latch_calls[-1] == (
        tasks_module.settings.LLM_DEGRADED_CANARY_QUALITY_TTL_SECONDS,
        "emergency_canary_error:RuntimeError",
    )


@pytest.mark.asyncio
async def test_process_pending_async_latches_when_emergency_canary_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_session = AsyncMock()
    tracker_holder: dict[str, FakeTracker] = {}
    calls = {"count": 0}

    def fake_tracker(*, stage: str) -> FakeTracker:
        tracker = FakeTracker(stage=stage)
        tracker_holder["tracker"] = tracker
        return tracker

    class FakeTier2Classifier:
        def __init__(self, *, session, model) -> None:
            self.model = model

    class FakePipeline:
        def __init__(self, *, session, tier2_classifier, degraded_llm_tracker) -> None:
            self.tier2_classifier = tier2_classifier

        async def process_pending_items(self, *, limit: int):
            return {"model": self.tier2_classifier.model}

        @staticmethod
        def run_result_to_dict(run_result):
            return run_result

    async def fake_canary(**_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return SimpleNamespace(passed=False, reason="primary_bad")
        return SimpleNamespace(passed=False, reason="emergency_bad")

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(tasks_module.settings, "LLM_DEGRADED_MODE_ENABLED", True)
    monkeypatch.setattr(tasks_module.settings, "LLM_DEGRADED_CANARY_ENABLED", True)
    monkeypatch.setattr(tasks_module.settings, "LLM_TIER2_EMERGENCY_MODEL", "emergency-model")
    monkeypatch.setattr(tasks_module, "DegradedLLMTracker", fake_tracker)
    monkeypatch.setattr(tasks_module, "run_tier2_canary", fake_canary)
    monkeypatch.setattr(tasks_module, "Tier2Classifier", FakeTier2Classifier)
    monkeypatch.setattr(tasks_module, "ProcessingPipeline", FakePipeline)

    await tasks_module._process_pending_async(limit=1)

    assert tracker_holder["tracker"].latch_calls[-1] == (
        tasks_module.settings.LLM_DEGRADED_CANARY_QUALITY_TTL_SECONDS,
        "primary:primary_bad;emergency:emergency_bad",
    )


@pytest.mark.asyncio
async def test_snapshot_trends_async_creates_and_skips_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trend_id = uuid4()
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.scalars.return_value = MagicMock(
        all=lambda: [
            SimpleNamespace(id=trend_id, name="A", current_log_odds=0.3),
            SimpleNamespace(id=None, name="B", current_log_odds=0.4),
            SimpleNamespace(id=uuid4(), name="C", current_log_odds=0.5),
        ]
    )
    mock_session.scalar = AsyncMock(side_effect=[None, uuid4()])

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))

    result = await tasks_module._snapshot_trends_async()

    assert result["scanned"] == 3
    assert result["created"] == 1
    assert result["skipped"] == 2
    assert mock_session.add.call_count == 1
    assert mock_session.commit.await_count == 1


@pytest.mark.asyncio
async def test_decay_trends_async_tracks_decayed_and_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trend_a = SimpleNamespace(id=uuid4(), name="A")
    trend_b = SimpleNamespace(id=uuid4(), name="B")
    mock_session = AsyncMock()
    mock_session.scalars.return_value = MagicMock(all=lambda: [trend_a, trend_b])

    class FakeTrendEngine:
        def __init__(self, *, session) -> None:
            assert session is mock_session

        def get_probability(self, trend) -> float:
            if trend is trend_a:
                return 0.2
            return 0.5

        async def apply_decay(self, *, trend, as_of) -> float:
            assert isinstance(as_of, datetime)
            if trend is trend_a:
                return 0.1
            return 0.5

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(tasks_module, "TrendEngine", FakeTrendEngine)

    result = await tasks_module._decay_trends_async()

    assert result["scanned"] == 2
    assert result["decayed"] == 1
    assert result["unchanged"] == 1
    assert mock_session.commit.await_count == 1


@pytest.mark.asyncio
async def test_check_event_lifecycles_async_commits_run_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_session = AsyncMock()

    class FakeManager:
        def __init__(self, session) -> None:
            assert session is mock_session

        async def run_decay_check(self) -> dict[str, object]:
            return {"task": "check_event_lifecycles", "confirmed_to_fading": 2}

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(tasks_module, "EventLifecycleManager", FakeManager)

    result = await tasks_module._check_event_lifecycles_async()

    assert result == {
        "status": "ok",
        "task": "check_event_lifecycles",
        "confirmed_to_fading": 2,
    }
    assert mock_session.commit.await_count == 1


@pytest.mark.asyncio
async def test_select_retention_helper_queries_return_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    noise_session = AsyncMock()
    archived_session = AsyncMock()
    evidence_session = AsyncMock()
    noise_ids = [uuid4()]
    archived_ids = [uuid4(), uuid4()]
    evidence_ids = [uuid4()]
    noise_session.scalars.return_value = MagicMock(all=lambda: noise_ids)
    archived_session.scalars.return_value = MagicMock(all=lambda: archived_ids)
    evidence_session.scalars.return_value = MagicMock(all=lambda: evidence_ids)
    sessions = iter([noise_session, archived_session, evidence_session])

    @asynccontextmanager
    async def fake_session_maker():
        yield next(sessions)

    monkeypatch.setattr(tasks_module, "async_session_maker", fake_session_maker)
    cutoff = datetime.now(tz=UTC)

    assert await tasks_module._select_noise_raw_item_ids(batch_size=5, cutoff=cutoff) == noise_ids
    assert (
        await tasks_module._select_archived_event_raw_item_ids(batch_size=5, cutoff=cutoff)
        == archived_ids
    )
    assert (
        await tasks_module._select_trend_evidence_ids(
            batch_size=5,
            evidence_cutoff=cutoff,
            archived_event_cutoff=cutoff,
        )
        == evidence_ids
    )


@pytest.mark.asyncio
async def test_run_data_retention_cleanup_async_dry_run_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cutoffs = tasks_module.RetentionCutoffs(
        now=datetime(2026, 2, 18, 12, 0, tzinfo=UTC),
        raw_item_noise_before=datetime(2026, 1, 1, tzinfo=UTC),
        raw_item_archived_event_before=datetime(2025, 11, 1, tzinfo=UTC),
        archived_event_before=datetime(2025, 8, 1, tzinfo=UTC),
        trend_evidence_before=datetime(2025, 2, 1, tzinfo=UTC),
        batch_size=10,
        dry_run=True,
    )
    event_id = uuid4()
    mock_session = AsyncMock()
    mock_session.scalars.return_value = MagicMock(all=lambda: [event_id])

    def fake_build_retention_cutoffs(*, dry_run=None):
        del dry_run
        return cutoffs

    monkeypatch.setattr(tasks_module, "_build_retention_cutoffs", fake_build_retention_cutoffs)
    monkeypatch.setattr(
        tasks_module, "_select_noise_raw_item_ids", AsyncMock(return_value=[uuid4()])
    )
    monkeypatch.setattr(
        tasks_module,
        "_select_archived_event_raw_item_ids",
        AsyncMock(return_value=[uuid4()]),
    )
    monkeypatch.setattr(
        tasks_module, "_select_trend_evidence_ids", AsyncMock(return_value=[uuid4()])
    )
    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))

    result = await tasks_module._run_data_retention_cleanup_async(dry_run=True)

    assert result["dry_run"] is True
    assert result["eligible"]["events"] == 1
    assert result["deleted"] == {"raw_items": 0, "trend_evidence": 0, "events": 0}
    assert mock_session.execute.await_count == 0
    assert mock_session.rollback.await_count == 1
    assert mock_session.commit.await_count == 0


@pytest.mark.asyncio
async def test_run_data_retention_cleanup_async_deletes_and_commits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cutoffs = tasks_module.RetentionCutoffs(
        now=datetime(2026, 2, 18, 12, 0, tzinfo=UTC),
        raw_item_noise_before=datetime(2026, 1, 1, tzinfo=UTC),
        raw_item_archived_event_before=datetime(2025, 11, 1, tzinfo=UTC),
        archived_event_before=datetime(2025, 8, 1, tzinfo=UTC),
        trend_evidence_before=datetime(2025, 2, 1, tzinfo=UTC),
        batch_size=10,
        dry_run=False,
    )
    raw_id = uuid4()
    archived_raw_id = uuid4()
    evidence_id = uuid4()
    event_id = uuid4()
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(rowcount=2),
            SimpleNamespace(rowcount=1),
            SimpleNamespace(rowcount=1),
        ]
    )
    mock_session.scalars.return_value = MagicMock(all=lambda: [event_id])

    def fake_build_retention_cutoffs(*, dry_run=None):
        del dry_run
        return cutoffs

    monkeypatch.setattr(tasks_module, "_build_retention_cutoffs", fake_build_retention_cutoffs)
    monkeypatch.setattr(
        tasks_module, "_select_noise_raw_item_ids", AsyncMock(return_value=[raw_id])
    )
    monkeypatch.setattr(
        tasks_module,
        "_select_archived_event_raw_item_ids",
        AsyncMock(return_value=[archived_raw_id]),
    )
    monkeypatch.setattr(
        tasks_module,
        "_select_trend_evidence_ids",
        AsyncMock(return_value=[evidence_id]),
    )
    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))

    result = await tasks_module._run_data_retention_cleanup_async(dry_run=False)

    assert result["dry_run"] is False
    assert result["eligible"]["raw_items_total"] == 2
    assert result["deleted"] == {"raw_items": 2, "trend_evidence": 1, "events": 1}
    assert mock_session.flush.await_count == 1
    assert mock_session.commit.await_count == 1


@pytest.mark.asyncio
async def test_run_data_retention_cleanup_async_skips_empty_raw_delete_but_deletes_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cutoffs = tasks_module.RetentionCutoffs(
        now=datetime(2026, 2, 18, 12, 0, tzinfo=UTC),
        raw_item_noise_before=datetime(2026, 1, 1, tzinfo=UTC),
        raw_item_archived_event_before=datetime(2025, 11, 1, tzinfo=UTC),
        archived_event_before=datetime(2025, 8, 1, tzinfo=UTC),
        trend_evidence_before=datetime(2025, 2, 1, tzinfo=UTC),
        batch_size=10,
        dry_run=False,
    )
    evidence_id = uuid4()
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=[SimpleNamespace(rowcount=1)])
    mock_session.scalars.return_value = MagicMock(all=list)

    def fake_build_retention_cutoffs(*, dry_run=None):
        del dry_run
        return cutoffs

    monkeypatch.setattr(tasks_module, "_build_retention_cutoffs", fake_build_retention_cutoffs)
    monkeypatch.setattr(tasks_module, "_select_noise_raw_item_ids", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        tasks_module,
        "_select_archived_event_raw_item_ids",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        tasks_module,
        "_select_trend_evidence_ids",
        AsyncMock(return_value=[evidence_id]),
    )
    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))

    result = await tasks_module._run_data_retention_cleanup_async(dry_run=False)

    assert result["deleted"] == {"raw_items": 0, "trend_evidence": 1, "events": 0}
    assert mock_session.flush.await_count == 1
    assert mock_session.commit.await_count == 1


@pytest.mark.asyncio
async def test_run_data_retention_cleanup_async_skips_empty_evidence_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cutoffs = tasks_module.RetentionCutoffs(
        now=datetime(2026, 2, 18, 12, 0, tzinfo=UTC),
        raw_item_noise_before=datetime(2026, 1, 1, tzinfo=UTC),
        raw_item_archived_event_before=datetime(2025, 11, 1, tzinfo=UTC),
        archived_event_before=datetime(2025, 8, 1, tzinfo=UTC),
        trend_evidence_before=datetime(2025, 2, 1, tzinfo=UTC),
        batch_size=10,
        dry_run=False,
    )
    raw_id = uuid4()
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=[SimpleNamespace(rowcount=1)])
    mock_session.scalars.return_value = MagicMock(all=list)

    def fake_build_retention_cutoffs(*, dry_run=None):
        del dry_run
        return cutoffs

    monkeypatch.setattr(tasks_module, "_build_retention_cutoffs", fake_build_retention_cutoffs)
    monkeypatch.setattr(
        tasks_module, "_select_noise_raw_item_ids", AsyncMock(return_value=[raw_id])
    )
    monkeypatch.setattr(
        tasks_module,
        "_select_archived_event_raw_item_ids",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(tasks_module, "_select_trend_evidence_ids", AsyncMock(return_value=[]))
    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))

    result = await tasks_module._run_data_retention_cleanup_async(dry_run=False)

    assert result["deleted"] == {"raw_items": 1, "trend_evidence": 0, "events": 0}
    assert mock_session.flush.await_count == 1
    assert mock_session.commit.await_count == 1


@pytest.mark.asyncio
async def test_generate_report_async_workers_commit_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    weekly_session = AsyncMock()
    monthly_session = AsyncMock()
    sessions = iter([weekly_session, monthly_session])

    @asynccontextmanager
    async def fake_session_maker():
        yield next(sessions)

    class FakeGenerator:
        def __init__(self, *, session) -> None:
            self.session = session

        async def generate_weekly_reports(self):
            return SimpleNamespace(
                period_start=datetime(2026, 2, 1, tzinfo=UTC),
                period_end=datetime(2026, 2, 8, tzinfo=UTC),
                scanned=3,
                created=2,
                updated=1,
            )

        async def generate_monthly_reports(self):
            return SimpleNamespace(
                period_start=datetime(2026, 1, 1, tzinfo=UTC),
                period_end=datetime(2026, 2, 1, tzinfo=UTC),
                scanned=4,
                created=3,
                updated=1,
            )

    monkeypatch.setattr(tasks_module, "async_session_maker", fake_session_maker)
    monkeypatch.setattr(tasks_module, "ReportGenerator", FakeGenerator)

    weekly = await tasks_module._generate_weekly_reports_async()
    monthly = await tasks_module._generate_monthly_reports_async()

    assert weekly["task"] == "generate_weekly_reports"
    assert weekly["created"] == 2
    assert monthly["task"] == "generate_monthly_reports"
    assert monthly["updated"] == 1
    assert weekly_session.commit.await_count == 1
    assert monthly_session.commit.await_count == 1


@pytest.mark.asyncio
async def test_replay_degraded_events_async_skips_when_tracker_is_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status = SimpleNamespace(
        is_degraded=True,
        stage="tier2",
        window=SimpleNamespace(total_calls=10, secondary_calls=4, failover_ratio=0.4),
    )
    tracker = SimpleNamespace(evaluate=lambda: status)

    def fake_tracker_ctor(*, stage: str):
        assert stage == "tier2"
        return tracker

    monkeypatch.setattr(tasks_module.settings, "LLM_DEGRADED_MODE_ENABLED", True)
    monkeypatch.setattr(tasks_module, "DegradedLLMTracker", fake_tracker_ctor)
    monkeypatch.setattr(tasks_module.asyncio, "to_thread", AsyncMock(return_value=status))

    result = await tasks_module._replay_degraded_events_async(limit=5)

    assert result == {
        "status": "skipped",
        "task": "replay_degraded_events",
        "reason": "degraded_llm_active",
        "stage": "tier2",
        "window": {
            "total_calls": 10,
            "secondary_calls": 4,
            "failover_ratio": 0.4,
        },
    }


@pytest.mark.asyncio
async def test_replay_degraded_events_async_returns_empty_when_queue_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_session = AsyncMock()
    mock_session.scalars.return_value = MagicMock(all=list)

    status = SimpleNamespace(
        is_degraded=False,
        stage="tier2",
        window=SimpleNamespace(total_calls=10, secondary_calls=1, failover_ratio=0.1),
    )

    def fake_tracker_ctor(*, stage: str):
        assert stage == "tier2"
        return SimpleNamespace(evaluate=lambda: status)

    monkeypatch.setattr(tasks_module.settings, "LLM_DEGRADED_MODE_ENABLED", True)
    monkeypatch.setattr(tasks_module, "DegradedLLMTracker", fake_tracker_ctor)
    monkeypatch.setattr(tasks_module.asyncio, "to_thread", AsyncMock(return_value=status))
    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))

    result = await tasks_module._replay_degraded_events_async(limit=0)

    assert result == {
        "status": "ok",
        "task": "replay_degraded_events",
        "drained": 0,
        "errors": 0,
    }


@pytest.mark.asyncio
async def test_replay_degraded_events_async_processes_success_and_error_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    success_item = SimpleNamespace(
        event_id="event-1",
        status="pending",
        locked_at=None,
        locked_by=None,
        attempt_count=0,
        last_attempt_at=None,
        details={},
        last_error=None,
        processed_at=None,
        priority=1,
        enqueued_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    error_item = SimpleNamespace(
        event_id="missing-event",
        status="pending",
        locked_at=None,
        locked_by=None,
        attempt_count=1,
        last_attempt_at=None,
        details=None,
        last_error=None,
        processed_at=None,
        priority=1,
        enqueued_at=datetime(2026, 2, 2, tzinfo=UTC),
    )
    mock_session = AsyncMock()
    mock_session.scalars = AsyncMock(
        side_effect=[
            MagicMock(all=lambda: [success_item, error_item]),
            MagicMock(all=lambda: [SimpleNamespace(id="trend-1")]),
            MagicMock(all=list),
            MagicMock(all=list),
        ]
    )

    async def fake_get(model, event_id):
        if event_id == "event-1":
            return SimpleNamespace(id="event-1")
        return None

    mock_session.get = AsyncMock(side_effect=fake_get)

    class FakeTier2Classifier:
        def __init__(self, *, session, model, secondary_model) -> None:
            assert session is mock_session
            assert secondary_model is None

        async def classify_event(self, *, event, trends) -> None:
            assert event.id == "event-1"
            assert len(trends) == 1

    class FakePipeline:
        def __init__(self, *, session, tier2_classifier, degraded_llm_tracker) -> None:
            assert session is mock_session
            assert degraded_llm_tracker is None

        async def _apply_trend_impacts(self, *, event, trends):
            assert event.id == "event-1"
            assert len(trends) == 1
            return (2, 1)

    monkeypatch.setattr(tasks_module.settings, "LLM_DEGRADED_MODE_ENABLED", False)
    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(tasks_module, "Tier2Classifier", FakeTier2Classifier)
    monkeypatch.setattr(tasks_module, "ProcessingPipeline", FakePipeline)

    result = await tasks_module._replay_degraded_events_async(limit=3)
    assert result == {"status": "ok", "task": "replay_degraded_events", "drained": 2, "errors": 1}
    assert success_item.status == "done"
    assert success_item.last_error is None
    assert success_item.details["replay_result"]["impacts_seen"] == 2
    assert error_item.status == "error"
    assert error_item.last_error == "Event not found: missing-event"
    assert mock_session.flush.await_count == 3
    assert mock_session.commit.await_count == 1


def test_replay_degraded_events_wrapper_uses_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks_module.settings, "LLM_DEGRADED_REPLAY_DRAIN_LIMIT", 7)

    async def fake_replay(limit: int) -> dict[str, object]:
        return {"status": "ok", "task": "replay_degraded_events", "drained": limit, "errors": 0}

    monkeypatch.setattr(tasks_module, "_replay_degraded_events_async", fake_replay)

    result = tasks_module.replay_degraded_events.run()

    assert result["drained"] == 7


def test_disabled_collectors_return_disabled_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks_module.settings, "ENABLE_RSS_INGESTION", False)
    monkeypatch.setattr(tasks_module.settings, "ENABLE_GDELT_INGESTION", False)

    assert tasks_module.collect_rss.run() == {"status": "disabled", "collector": "rss"}
    assert tasks_module.collect_gdelt.run() == {"status": "disabled", "collector": "gdelt"}


def test_check_source_freshness_wrapper_uses_async_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_check() -> dict[str, object]:
        return {
            "status": "ok",
            "task": "check_source_freshness",
            "stale_count": 1,
            "stale_collectors": ["rss"],
            "catchup_dispatched": [],
        }

    monkeypatch.setattr(tasks_module, "_check_source_freshness_async", fake_check)

    result = tasks_module.check_source_freshness.run()

    assert result["task"] == "check_source_freshness"
    assert result["stale_count"] == 1
