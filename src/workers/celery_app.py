"""
Celery application and periodic scheduling configuration.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from celery import Celery

from src.core.config import settings


def _build_beat_schedule() -> dict[str, dict[str, Any]]:
    schedule: dict[str, dict[str, Any]] = {}

    if settings.ENABLE_RSS_INGESTION:
        schedule["collect-rss"] = {
            "task": "workers.collect_rss",
            "schedule": timedelta(minutes=max(1, settings.RSS_COLLECTION_INTERVAL)),
        }

    if settings.ENABLE_GDELT_INGESTION:
        schedule["collect-gdelt"] = {
            "task": "workers.collect_gdelt",
            "schedule": timedelta(minutes=max(1, settings.GDELT_COLLECTION_INTERVAL)),
        }

    return schedule


celery_app = Celery("horadus")
celery_app.conf.update(
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_queue="default",
    task_routes={
        "workers.collect_rss": {"queue": "ingestion"},
        "workers.collect_gdelt": {"queue": "ingestion"},
        "workers.process_pending_items": {"queue": "processing"},
        "workers.ping": {"queue": "default"},
    },
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    beat_schedule=_build_beat_schedule(),
)

celery_app.autodiscover_tasks(["src.workers"])
