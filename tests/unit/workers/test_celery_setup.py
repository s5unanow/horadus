from __future__ import annotations

import importlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from celery.schedules import crontab

import src.workers.tasks as tasks_module
from src.storage.models import ProcessingStatus, RawItem

celery_app_module = importlib.import_module("src.workers.celery_app")

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def disable_worker_heartbeat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks_module, "_record_worker_activity", lambda **_: None)


def test_build_beat_schedule_includes_enabled_collectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(celery_app_module.settings, "ENABLE_RSS_INGESTION", True)
    monkeypatch.setattr(celery_app_module.settings, "ENABLE_GDELT_INGESTION", True)
    monkeypatch.setattr(celery_app_module.settings, "RSS_COLLECTION_INTERVAL", 15)
    monkeypatch.setattr(celery_app_module.settings, "GDELT_COLLECTION_INTERVAL", 45)
    monkeypatch.setattr(celery_app_module.settings, "TREND_SNAPSHOT_INTERVAL_MINUTES", 120)
    monkeypatch.setattr(celery_app_module.settings, "PROCESSING_REAPER_INTERVAL_MINUTES", 20)
    monkeypatch.setattr(celery_app_module.settings, "WEEKLY_REPORT_DAY_OF_WEEK", 2)
    monkeypatch.setattr(celery_app_module.settings, "WEEKLY_REPORT_HOUR_UTC", 6)
    monkeypatch.setattr(celery_app_module.settings, "WEEKLY_REPORT_MINUTE_UTC", 30)
    monkeypatch.setattr(celery_app_module.settings, "MONTHLY_REPORT_DAY_OF_MONTH", 1)
    monkeypatch.setattr(celery_app_module.settings, "MONTHLY_REPORT_HOUR_UTC", 8)
    monkeypatch.setattr(celery_app_module.settings, "MONTHLY_REPORT_MINUTE_UTC", 15)

    schedule = celery_app_module._build_beat_schedule()

    assert schedule["collect-rss"]["task"] == "workers.collect_rss"
    assert schedule["collect-rss"]["schedule"] == timedelta(minutes=15)
    assert schedule["collect-gdelt"]["task"] == "workers.collect_gdelt"
    assert schedule["collect-gdelt"]["schedule"] == timedelta(minutes=45)
    assert schedule["snapshot-trends"]["task"] == "workers.snapshot_trends"
    assert schedule["snapshot-trends"]["schedule"] == timedelta(minutes=120)
    assert schedule["apply-trend-decay"]["task"] == "workers.apply_trend_decay"
    assert schedule["apply-trend-decay"]["schedule"] == timedelta(days=1)
    assert schedule["check-event-lifecycles"]["task"] == "workers.check_event_lifecycles"
    assert schedule["check-event-lifecycles"]["schedule"] == timedelta(hours=1)
    assert schedule["reap-stale-processing-items"]["task"] == "workers.reap_stale_processing_items"
    assert schedule["reap-stale-processing-items"]["schedule"] == timedelta(minutes=20)
    assert schedule["generate-weekly-reports"]["task"] == "workers.generate_weekly_reports"
    assert schedule["generate-weekly-reports"]["schedule"] == crontab(
        day_of_week="2",
        hour=6,
        minute=30,
    )
    assert schedule["generate-monthly-reports"]["task"] == "workers.generate_monthly_reports"
    assert schedule["generate-monthly-reports"]["schedule"] == crontab(
        day_of_month="1",
        hour=8,
        minute=15,
    )


def test_build_beat_schedule_omits_disabled_collectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(celery_app_module.settings, "ENABLE_RSS_INGESTION", False)
    monkeypatch.setattr(celery_app_module.settings, "ENABLE_GDELT_INGESTION", False)
    monkeypatch.setattr(celery_app_module.settings, "TREND_SNAPSHOT_INTERVAL_MINUTES", 90)
    monkeypatch.setattr(celery_app_module.settings, "PROCESSING_REAPER_INTERVAL_MINUTES", 10)
    monkeypatch.setattr(celery_app_module.settings, "WEEKLY_REPORT_DAY_OF_WEEK", 1)
    monkeypatch.setattr(celery_app_module.settings, "WEEKLY_REPORT_HOUR_UTC", 7)
    monkeypatch.setattr(celery_app_module.settings, "WEEKLY_REPORT_MINUTE_UTC", 0)
    monkeypatch.setattr(celery_app_module.settings, "MONTHLY_REPORT_DAY_OF_MONTH", 1)
    monkeypatch.setattr(celery_app_module.settings, "MONTHLY_REPORT_HOUR_UTC", 8)
    monkeypatch.setattr(celery_app_module.settings, "MONTHLY_REPORT_MINUTE_UTC", 0)

    schedule = celery_app_module._build_beat_schedule()

    assert list(schedule.keys()) == [
        "snapshot-trends",
        "apply-trend-decay",
        "check-event-lifecycles",
        "reap-stale-processing-items",
        "generate-weekly-reports",
        "generate-monthly-reports",
    ]
    assert schedule["snapshot-trends"]["task"] == "workers.snapshot_trends"
    assert schedule["snapshot-trends"]["schedule"] == timedelta(minutes=90)
    assert schedule["apply-trend-decay"]["task"] == "workers.apply_trend_decay"
    assert schedule["apply-trend-decay"]["schedule"] == timedelta(days=1)
    assert schedule["check-event-lifecycles"]["task"] == "workers.check_event_lifecycles"
    assert schedule["check-event-lifecycles"]["schedule"] == timedelta(hours=1)
    assert schedule["reap-stale-processing-items"]["task"] == "workers.reap_stale_processing_items"
    assert schedule["reap-stale-processing-items"]["schedule"] == timedelta(minutes=10)
    assert schedule["generate-weekly-reports"]["task"] == "workers.generate_weekly_reports"
    assert schedule["generate-weekly-reports"]["schedule"] == crontab(
        day_of_week="1",
        hour=7,
        minute=0,
    )
    assert schedule["generate-monthly-reports"]["task"] == "workers.generate_monthly_reports"
    assert schedule["generate-monthly-reports"]["schedule"] == crontab(
        day_of_month="1",
        hour=8,
        minute=0,
    )


def test_celery_routes_include_processing_queue() -> None:
    routes = celery_app_module.celery_app.conf.task_routes
    assert routes["workers.process_pending_items"]["queue"] == "processing"
    assert routes["workers.snapshot_trends"]["queue"] == "processing"
    assert routes["workers.apply_trend_decay"]["queue"] == "processing"
    assert routes["workers.check_event_lifecycles"]["queue"] == "processing"
    assert routes["workers.reap_stale_processing_items"]["queue"] == "processing"
    assert routes["workers.generate_weekly_reports"]["queue"] == "processing"
    assert routes["workers.generate_monthly_reports"]["queue"] == "processing"


def test_run_task_with_heartbeat_records_start_and_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, str | None]] = []

    def fake_record(*, task_name: str, status: str, error: str | None = None) -> None:
        calls.append((task_name, status, error))

    monkeypatch.setattr(tasks_module, "_record_worker_activity", fake_record)

    result = tasks_module._run_task_with_heartbeat(
        task_name="workers.sample",
        runner=lambda: {"status": "ok"},
    )

    assert result == {"status": "ok"}
    assert calls == [
        ("workers.sample", "started", None),
        ("workers.sample", "ok", None),
    ]


def test_run_task_with_heartbeat_records_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, str | None]] = []

    def fake_record(*, task_name: str, status: str, error: str | None = None) -> None:
        calls.append((task_name, status, error))

    monkeypatch.setattr(tasks_module, "_record_worker_activity", fake_record)

    def failing_runner() -> dict[str, object]:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        tasks_module._run_task_with_heartbeat(
            task_name="workers.sample",
            runner=failing_runner,
        )

    assert calls[0] == ("workers.sample", "started", None)
    assert calls[1][0] == "workers.sample"
    assert calls[1][1] == "failed"
    assert "boom" in str(calls[1][2])


def test_collect_rss_task_uses_async_collector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks_module.settings, "ENABLE_RSS_INGESTION", True)
    queue_calls: list[tuple[str, int]] = []

    def fake_queue(*, collector: str, stored_items: int) -> bool:
        queue_calls.append((collector, stored_items))
        return True

    async def fake_collect() -> dict[str, object]:
        return {
            "status": "ok",
            "collector": "rss",
            "fetched": 3,
            "stored": 2,
            "skipped": 1,
            "errors": 0,
            "results": [],
        }

    monkeypatch.setattr(tasks_module, "_collect_rss_async", fake_collect)
    monkeypatch.setattr(tasks_module, "_queue_processing_for_new_items", fake_queue)

    result = tasks_module.collect_rss.run()

    assert result["status"] == "ok"
    assert result["collector"] == "rss"
    assert result["stored"] == 2
    assert queue_calls == [("rss", 2)]


def test_collect_rss_records_observability_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks_module.settings, "ENABLE_RSS_INGESTION", True)
    captured: list[dict[str, int | str]] = []

    async def fake_collect() -> dict[str, object]:
        return {
            "status": "ok",
            "collector": "rss",
            "fetched": 5,
            "stored": 3,
            "skipped": 2,
            "errors": 1,
            "results": [],
        }

    def fake_record(
        *,
        collector: str,
        fetched: int,
        stored: int,
        skipped: int,
        errors: int,
    ) -> None:
        captured.append(
            {
                "collector": collector,
                "fetched": fetched,
                "stored": stored,
                "skipped": skipped,
                "errors": errors,
            }
        )

    monkeypatch.setattr(tasks_module, "_collect_rss_async", fake_collect)
    monkeypatch.setattr(tasks_module, "_queue_processing_for_new_items", lambda **_: True)
    monkeypatch.setattr(tasks_module, "record_collector_metrics", fake_record)

    tasks_module.collect_rss.run()

    assert captured == [
        {
            "collector": "rss",
            "fetched": 5,
            "stored": 3,
            "skipped": 2,
            "errors": 1,
        }
    ]


def test_collect_gdelt_task_uses_async_collector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks_module.settings, "ENABLE_GDELT_INGESTION", True)
    queue_calls: list[tuple[str, int]] = []

    def fake_queue(*, collector: str, stored_items: int) -> bool:
        queue_calls.append((collector, stored_items))
        return True

    async def fake_collect() -> dict[str, object]:
        return {
            "status": "ok",
            "collector": "gdelt",
            "fetched": 4,
            "stored": 3,
            "skipped": 1,
            "errors": 0,
            "results": [],
        }

    monkeypatch.setattr(tasks_module, "_collect_gdelt_async", fake_collect)
    monkeypatch.setattr(tasks_module, "_queue_processing_for_new_items", fake_queue)

    result = tasks_module.collect_gdelt.run()

    assert result["status"] == "ok"
    assert result["collector"] == "gdelt"
    assert result["stored"] == 3
    assert queue_calls == [("gdelt", 3)]


def test_process_pending_items_task_uses_async_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks_module.settings, "PROCESSING_PIPELINE_BATCH_SIZE", 25)

    async def fake_process(limit: int) -> dict[str, object]:
        return {
            "status": "ok",
            "task": "processing_pipeline",
            "scanned": limit,
            "processed": limit,
            "classified": limit - 1,
            "noise": 1,
            "duplicates": 0,
            "errors": 0,
            "embedded": limit,
            "events_created": 1,
            "events_merged": limit - 1,
            "embedding_api_calls": 2,
            "tier1_prompt_tokens": 100,
            "tier1_completion_tokens": 20,
            "tier1_api_calls": 1,
            "tier2_prompt_tokens": 80,
            "tier2_completion_tokens": 40,
            "tier2_api_calls": 1,
        }

    monkeypatch.setattr(tasks_module, "_process_pending_async", fake_process)

    result = tasks_module.process_pending_items.run()

    assert result["status"] == "ok"
    assert result["task"] == "processing_pipeline"
    assert result["processed"] == 25
    assert result["classified"] == 24


def test_process_pending_items_records_observability_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks_module.settings, "PROCESSING_PIPELINE_BATCH_SIZE", 10)
    captured: list[dict[str, object]] = []

    async def fake_process(limit: int) -> dict[str, object]:
        return {
            "status": "ok",
            "task": "processing_pipeline",
            "scanned": limit,
            "processed": limit,
            "classified": limit - 1,
            "noise": 1,
            "duplicates": 0,
            "errors": 0,
            "embedded": limit,
            "events_created": 1,
            "events_merged": limit - 1,
            "embedding_api_calls": 2,
            "tier1_prompt_tokens": 100,
            "tier1_completion_tokens": 20,
            "tier1_api_calls": 1,
            "tier2_prompt_tokens": 80,
            "tier2_completion_tokens": 40,
            "tier2_api_calls": 1,
        }

    def fake_record(run_result: dict[str, object]) -> None:
        captured.append(run_result)

    monkeypatch.setattr(tasks_module, "_process_pending_async", fake_process)
    monkeypatch.setattr(tasks_module, "record_pipeline_metrics", fake_record)

    tasks_module.process_pending_items.run(limit=10)

    assert len(captured) == 1
    assert captured[0]["task"] == "processing_pipeline"
    assert captured[0]["processed"] == 10


def test_snapshot_trends_task_uses_async_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_snapshot() -> dict[str, object]:
        return {
            "status": "ok",
            "task": "snapshot_trends",
            "timestamp": "2026-02-07T13:00:00+00:00",
            "scanned": 4,
            "created": 4,
            "skipped": 0,
        }

    monkeypatch.setattr(tasks_module, "_snapshot_trends_async", fake_snapshot)

    result = tasks_module.snapshot_trends.run()

    assert result["status"] == "ok"
    assert result["task"] == "snapshot_trends"
    assert result["scanned"] == 4
    assert result["created"] == 4


def test_apply_trend_decay_task_uses_async_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_decay() -> dict[str, object]:
        return {
            "status": "ok",
            "task": "apply_trend_decay",
            "as_of": "2026-02-07T13:00:00+00:00",
            "scanned": 4,
            "decayed": 3,
            "unchanged": 1,
        }

    monkeypatch.setattr(tasks_module, "_decay_trends_async", fake_decay)

    result = tasks_module.apply_trend_decay.run()

    assert result["status"] == "ok"
    assert result["task"] == "apply_trend_decay"
    assert result["scanned"] == 4
    assert result["decayed"] == 3
    assert result["unchanged"] == 1


def test_reap_stale_processing_items_task_uses_async_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_reap() -> dict[str, object]:
        return {
            "status": "ok",
            "task": "reap_stale_processing_items",
            "checked_at": "2026-02-10T13:00:00+00:00",
            "stale_before": "2026-02-10T12:30:00+00:00",
            "scanned": 2,
            "reset": 2,
            "reset_item_ids": ["a", "b"],
        }

    captured: list[int] = []

    def fake_record(*, reset_count: int) -> None:
        captured.append(reset_count)

    monkeypatch.setattr(tasks_module, "_reap_stale_processing_async", fake_reap)
    monkeypatch.setattr(tasks_module, "record_processing_reaper_resets", fake_record)

    result = tasks_module.reap_stale_processing_items.run()

    assert result["status"] == "ok"
    assert result["task"] == "reap_stale_processing_items"
    assert result["reset"] == 2
    assert captured == [2]


@pytest.mark.asyncio
async def test_reap_stale_processing_async_resets_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale_item = RawItem(
        id=uuid4(),
        source_id=uuid4(),
        external_id="stale-item",
        raw_content="x",
        content_hash="a" * 64,
        processing_status=ProcessingStatus.PROCESSING,
        processing_started_at=datetime(2026, 2, 10, 12, 0, tzinfo=UTC),
    )
    mock_session = AsyncMock()
    mock_session.scalars.return_value = MagicMock(all=lambda: [stale_item])

    @asynccontextmanager
    async def fake_session_maker():
        yield mock_session

    monkeypatch.setattr(tasks_module, "async_session_maker", fake_session_maker)
    monkeypatch.setattr(tasks_module.settings, "PROCESSING_STALE_TIMEOUT_MINUTES", 30)
    monkeypatch.setattr(tasks_module.settings, "PROCESSING_PIPELINE_BATCH_SIZE", 50)

    result = await tasks_module._reap_stale_processing_async()

    assert result["task"] == "reap_stale_processing_items"
    assert result["scanned"] == 1
    assert result["reset"] == 1
    assert result["reset_item_ids"] == [str(stale_item.id)]
    assert stale_item.processing_status == ProcessingStatus.PENDING
    assert stale_item.processing_started_at is None
    assert stale_item.error_message is None
    assert mock_session.commit.await_count == 1


@pytest.mark.asyncio
async def test_reap_stale_processing_async_handles_no_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_session = AsyncMock()
    mock_session.scalars.return_value = MagicMock(all=list)

    @asynccontextmanager
    async def fake_session_maker():
        yield mock_session

    monkeypatch.setattr(tasks_module, "async_session_maker", fake_session_maker)
    monkeypatch.setattr(tasks_module.settings, "PROCESSING_STALE_TIMEOUT_MINUTES", 30)
    monkeypatch.setattr(tasks_module.settings, "PROCESSING_PIPELINE_BATCH_SIZE", 50)

    result = await tasks_module._reap_stale_processing_async()

    assert result["scanned"] == 0
    assert result["reset"] == 0
    assert result["reset_item_ids"] == []
    assert mock_session.commit.await_count == 1


def test_check_event_lifecycles_task_uses_async_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_check() -> dict[str, object]:
        return {
            "status": "ok",
            "task": "check_event_lifecycles",
            "as_of": "2026-02-07T13:00:00+00:00",
            "confirmed_to_fading": 2,
            "fading_to_archived": 1,
        }

    monkeypatch.setattr(tasks_module, "_check_event_lifecycles_async", fake_check)

    result = tasks_module.check_event_lifecycles.run()

    assert result["status"] == "ok"
    assert result["task"] == "check_event_lifecycles"
    assert result["confirmed_to_fading"] == 2
    assert result["fading_to_archived"] == 1


def test_generate_weekly_reports_task_uses_async_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_generate() -> dict[str, object]:
        return {
            "status": "ok",
            "task": "generate_weekly_reports",
            "period_start": "2026-02-01T00:00:00+00:00",
            "period_end": "2026-02-08T00:00:00+00:00",
            "scanned": 3,
            "created": 3,
            "updated": 0,
        }

    monkeypatch.setattr(tasks_module, "_generate_weekly_reports_async", fake_generate)

    result = tasks_module.generate_weekly_reports.run()

    assert result["status"] == "ok"
    assert result["task"] == "generate_weekly_reports"
    assert result["scanned"] == 3
    assert result["created"] == 3


def test_generate_monthly_reports_task_uses_async_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_generate() -> dict[str, object]:
        return {
            "status": "ok",
            "task": "generate_monthly_reports",
            "period_start": "2026-01-01T00:00:00+00:00",
            "period_end": "2026-02-01T00:00:00+00:00",
            "scanned": 3,
            "created": 3,
            "updated": 0,
        }

    monkeypatch.setattr(tasks_module, "_generate_monthly_reports_async", fake_generate)

    result = tasks_module.generate_monthly_reports.run()

    assert result["status"] == "ok"
    assert result["task"] == "generate_monthly_reports"
    assert result["scanned"] == 3
    assert result["created"] == 3


def test_task_retry_configuration() -> None:
    assert tasks_module.collect_rss.autoretry_for
    assert tasks_module.collect_rss.retry_kwargs == {"max_retries": 3}
    assert tasks_module.collect_gdelt.autoretry_for
    assert tasks_module.collect_gdelt.retry_kwargs == {"max_retries": 3}
    assert tasks_module.process_pending_items.autoretry_for
    assert tasks_module.process_pending_items.retry_kwargs == {"max_retries": 3}


def test_push_dead_letter_to_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = MagicMock()
    monkeypatch.setattr(tasks_module.redis, "from_url", MagicMock(return_value=fake_redis))

    tasks_module._push_dead_letter({"task_name": "workers.collect_rss"})

    fake_redis.lpush.assert_called_once()
    key, payload = fake_redis.lpush.call_args.args
    assert key == tasks_module.DEAD_LETTER_KEY
    loaded_payload = json.loads(payload)
    assert loaded_payload["task_name"] == "workers.collect_rss"
    fake_redis.ltrim.assert_called_once_with(
        tasks_module.DEAD_LETTER_KEY,
        0,
        tasks_module.DEAD_LETTER_MAX_ITEMS - 1,
    )
    fake_redis.close.assert_called_once()


def test_ping_task_returns_ok() -> None:
    result = tasks_module.ping.run()
    assert result["status"] == "ok"
    assert "timestamp" in result
