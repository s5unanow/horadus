from __future__ import annotations

import importlib
import json
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

import src.workers.tasks as tasks_module

celery_app_module = importlib.import_module("src.workers.celery_app")

pytestmark = pytest.mark.unit


def test_build_beat_schedule_includes_enabled_collectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(celery_app_module.settings, "ENABLE_RSS_INGESTION", True)
    monkeypatch.setattr(celery_app_module.settings, "ENABLE_GDELT_INGESTION", True)
    monkeypatch.setattr(celery_app_module.settings, "RSS_COLLECTION_INTERVAL", 15)
    monkeypatch.setattr(celery_app_module.settings, "GDELT_COLLECTION_INTERVAL", 45)

    schedule = celery_app_module._build_beat_schedule()

    assert schedule["collect-rss"]["task"] == "workers.collect_rss"
    assert schedule["collect-rss"]["schedule"] == timedelta(minutes=15)
    assert schedule["collect-gdelt"]["task"] == "workers.collect_gdelt"
    assert schedule["collect-gdelt"]["schedule"] == timedelta(minutes=45)


def test_build_beat_schedule_omits_disabled_collectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(celery_app_module.settings, "ENABLE_RSS_INGESTION", False)
    monkeypatch.setattr(celery_app_module.settings, "ENABLE_GDELT_INGESTION", False)

    schedule = celery_app_module._build_beat_schedule()

    assert schedule == {}


def test_collect_rss_task_uses_async_collector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks_module.settings, "ENABLE_RSS_INGESTION", True)

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

    result = tasks_module.collect_rss.run()

    assert result["status"] == "ok"
    assert result["collector"] == "rss"
    assert result["stored"] == 2


def test_collect_gdelt_task_uses_async_collector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks_module.settings, "ENABLE_GDELT_INGESTION", True)

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

    result = tasks_module.collect_gdelt.run()

    assert result["status"] == "ok"
    assert result["collector"] == "gdelt"
    assert result["stored"] == 3


def test_task_retry_configuration() -> None:
    assert tasks_module.collect_rss.autoretry_for
    assert tasks_module.collect_rss.retry_kwargs == {"max_retries": 3}
    assert tasks_module.collect_gdelt.autoretry_for
    assert tasks_module.collect_gdelt.retry_kwargs == {"max_retries": 3}


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
