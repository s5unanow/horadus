from __future__ import annotations

import importlib
from datetime import timedelta

import pytest

import src.workers.tasks as tasks_module

celery_app_module = importlib.import_module("src.workers.celery_app")
pytestmark = pytest.mark.unit


def test_build_beat_schedule_includes_source_coverage_monitor() -> None:
    schedule = celery_app_module._build_beat_schedule()

    assert schedule["monitor-source-coverage"]["task"] == "workers.monitor_source_coverage"
    assert schedule["monitor-source-coverage"]["schedule"] == timedelta(hours=6)


def test_celery_routes_include_source_coverage_queue() -> None:
    routes = celery_app_module.celery_app.conf.task_routes

    assert routes["workers.monitor_source_coverage"]["queue"] == "processing"


def test_monitor_source_coverage_wrapper_uses_async_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_async(*, asyncio_module, coro):
        del asyncio_module
        return coro

    def fake_run_task_with_heartbeat(*, deps, task_name, runner):
        del deps, task_name
        return runner()

    monkeypatch.setattr(
        tasks_module.coverage_helpers,
        "monitor_source_coverage_async",
        lambda **_: {
            "task": "monitor_source_coverage",
            "total_seen": 3,
            "total_processed": 2,
            "alert_count": 0,
            "artifact_path": "artifacts/source_coverage/coverage.json",
        },
    )
    monkeypatch.setattr(
        tasks_module.shared_helpers,
        "run_async",
        fake_run_async,
    )
    monkeypatch.setattr(
        tasks_module.shared_helpers,
        "run_task_with_heartbeat",
        fake_run_task_with_heartbeat,
    )

    result = tasks_module.monitor_source_coverage.run()

    assert result["task"] == "monitor_source_coverage"
    assert result["total_seen"] == 3
