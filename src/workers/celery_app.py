"""
Celery application and periodic scheduling configuration.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from celery import Celery
from celery.schedules import crontab

from src.core.config import settings
from src.core.tracing import configure_tracing


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

    schedule["snapshot-trends"] = {
        "task": "workers.snapshot_trends",
        "schedule": timedelta(minutes=max(1, settings.TREND_SNAPSHOT_INTERVAL_MINUTES)),
    }
    schedule["apply-trend-decay"] = {
        "task": "workers.apply_trend_decay",
        "schedule": timedelta(days=1),
    }
    schedule["check-event-lifecycles"] = {
        "task": "workers.check_event_lifecycles",
        "schedule": timedelta(hours=1),
    }
    schedule["reap-stale-processing-items"] = {
        "task": "workers.reap_stale_processing_items",
        "schedule": timedelta(minutes=max(1, settings.PROCESSING_REAPER_INTERVAL_MINUTES)),
    }
    if settings.RETENTION_CLEANUP_ENABLED:
        schedule["run-data-retention-cleanup"] = {
            "task": "workers.run_data_retention_cleanup",
            "schedule": timedelta(hours=max(1, settings.RETENTION_CLEANUP_INTERVAL_HOURS)),
        }
    if settings.ENABLE_PROCESSING_PIPELINE:
        schedule["process-pending-items"] = {
            "task": "workers.process_pending_items",
            "schedule": timedelta(minutes=max(1, settings.PROCESS_PENDING_INTERVAL_MINUTES)),
        }
    schedule["check-source-freshness"] = {
        "task": "workers.check_source_freshness",
        "schedule": timedelta(minutes=max(1, settings.SOURCE_FRESHNESS_CHECK_INTERVAL_MINUTES)),
    }
    schedule["generate-weekly-reports"] = {
        "task": "workers.generate_weekly_reports",
        "schedule": crontab(
            day_of_week=str(settings.WEEKLY_REPORT_DAY_OF_WEEK),
            hour=settings.WEEKLY_REPORT_HOUR_UTC,
            minute=settings.WEEKLY_REPORT_MINUTE_UTC,
        ),
    }
    schedule["generate-monthly-reports"] = {
        "task": "workers.generate_monthly_reports",
        "schedule": crontab(
            day_of_month=str(settings.MONTHLY_REPORT_DAY_OF_MONTH),
            hour=settings.MONTHLY_REPORT_HOUR_UTC,
            minute=settings.MONTHLY_REPORT_MINUTE_UTC,
        ),
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
        "workers.check_source_freshness": {"queue": "processing"},
        "workers.snapshot_trends": {"queue": "processing"},
        "workers.apply_trend_decay": {"queue": "processing"},
        "workers.check_event_lifecycles": {"queue": "processing"},
        "workers.reap_stale_processing_items": {"queue": "processing"},
        "workers.run_data_retention_cleanup": {"queue": "processing"},
        "workers.generate_weekly_reports": {"queue": "processing"},
        "workers.generate_monthly_reports": {"queue": "processing"},
        "workers.ping": {"queue": "default"},
    },
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    beat_schedule=_build_beat_schedule(),
)

celery_app.autodiscover_tasks(["src.workers"])
configure_tracing(celery_app=celery_app)
