from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast


async def collect_rss_async(*, deps: Any) -> dict[str, Any]:
    async with (
        deps.httpx.AsyncClient() as http_client,
        deps.async_session_maker() as session,
    ):
        collector = deps.RSSCollector(session=session, http_client=http_client)
        results = await collector.collect_all()
        await session.commit()

    return {
        "status": "ok",
        "collector": "rss",
        "fetched": sum(result.items_fetched for result in results),
        "stored": sum(result.items_stored for result in results),
        "skipped": sum(result.items_skipped for result in results),
        "errors": sum(len(result.errors) for result in results),
        "transient_errors": sum(result.transient_errors for result in results),
        "terminal_errors": sum(result.terminal_errors for result in results),
        "sources_succeeded": sum(1 for result in results if not result.errors),
        "sources_failed": sum(1 for result in results if result.errors),
        "results": [asdict(result) for result in results],
    }


async def collect_gdelt_async(*, deps: Any) -> dict[str, Any]:
    async with (
        deps.httpx.AsyncClient() as http_client,
        deps.async_session_maker() as session,
    ):
        collector = deps.GDELTClient(session=session, http_client=http_client)
        results = await collector.collect_all()
        await session.commit()

    return {
        "status": "ok",
        "collector": "gdelt",
        "fetched": sum(result.items_fetched for result in results),
        "stored": sum(result.items_stored for result in results),
        "skipped": sum(result.items_skipped for result in results),
        "errors": sum(len(result.errors) for result in results),
        "transient_errors": sum(result.transient_errors for result in results),
        "terminal_errors": sum(result.terminal_errors for result in results),
        "sources_succeeded": sum(1 for result in results if not result.errors),
        "sources_failed": sum(1 for result in results if result.errors),
        "results": [asdict(result) for result in results],
    }


async def check_source_freshness_async(*, deps: Any) -> dict[str, Any]:
    async with deps.async_session_maker() as session:
        report = await deps.build_source_freshness_report(session=session)

    stale_rows = [row for row in report.rows if row.is_stale]
    stale_by_collector: dict[str, int] = {}
    for row in stale_rows:
        stale_by_collector[row.collector] = stale_by_collector.get(row.collector, 0) + 1

    for collector, stale_count in stale_by_collector.items():
        deps.record_source_freshness_stale(collector=collector, stale_count=stale_count)

    catchup_dispatched: list[str] = []
    dispatch_budget = max(0, deps.settings.SOURCE_FRESHNESS_MAX_CATCHUP_DISPATCHES)
    if dispatch_budget > 0:
        stale_collectors = set(report.stale_collectors)
        if (
            "rss" in stale_collectors
            and deps.settings.ENABLE_RSS_INGESTION
            and len(catchup_dispatched) < dispatch_budget
        ):
            cast("Any", deps.collect_rss).delay()
            deps.record_source_catchup_dispatch(collector="rss")
            catchup_dispatched.append("rss")
        if (
            "gdelt" in stale_collectors
            and deps.settings.ENABLE_GDELT_INGESTION
            and len(catchup_dispatched) < dispatch_budget
        ):
            cast("Any", deps.collect_gdelt).delay()
            deps.record_source_catchup_dispatch(collector="gdelt")
            catchup_dispatched.append("gdelt")

    stale_source_rows = [
        {
            "source_id": str(row.source_id),
            "source_name": row.source_name,
            "collector": row.collector,
            "last_fetched_at": row.last_fetched_at.isoformat() if row.last_fetched_at else None,
            "age_seconds": row.age_seconds,
            "stale_after_seconds": row.stale_after_seconds,
        }
        for row in stale_rows
    ]

    return {
        "status": "ok",
        "task": "check_source_freshness",
        "checked_at": report.checked_at.isoformat(),
        "stale_multiplier": report.stale_multiplier,
        "stale_count": len(stale_rows),
        "stale_collectors": list(report.stale_collectors),
        "stale_by_collector": stale_by_collector,
        "catchup_dispatch_budget": dispatch_budget,
        "catchup_dispatched": catchup_dispatched,
        "stale_sources": stale_source_rows,
    }


async def monitor_cluster_drift_async(*, deps: Any) -> dict[str, Any]:
    window_end = datetime.now(tz=UTC)
    window_start = window_end - timedelta(days=deps.settings.CLUSTER_DRIFT_SENTINEL_LOOKBACK_DAYS)

    async with deps.async_session_maker() as session:
        rows = (
            await session.execute(
                deps.select(
                    deps.Event.id,
                    deps.Event.has_contradictions,
                    deps.func.count(deps.EventItem.item_id).label("item_count"),
                    deps.func.array_agg(deps.func.coalesce(deps.RawItem.language, "unknown")).label(
                        "languages"
                    ),
                )
                .outerjoin(deps.EventItem, deps.EventItem.event_id == deps.Event.id)
                .outerjoin(deps.RawItem, deps.RawItem.id == deps.EventItem.item_id)
                .where(deps.Event.first_seen_at >= window_start)
                .where(deps.Event.first_seen_at < window_end)
                .group_by(deps.Event.id, deps.Event.has_contradictions)
            )
        ).all()

    event_samples: list[Any] = []
    for row in rows:
        item_count_raw = row[2]
        languages_raw = row[3]
        language_values: tuple[str, ...]
        if isinstance(languages_raw, list):
            language_values = tuple(
                str(item or "unknown") for item in languages_raw if item is not None
            )
        else:
            language_values = ()

        event_samples.append(
            deps.ClusterEventSample(
                item_count=max(0, int(item_count_raw or 0)),
                has_contradictions=bool(row[1]),
                languages=language_values,
            )
        )

    artifact_dir = Path(deps.settings.CLUSTER_DRIFT_ARTIFACT_DIR)
    baseline_distribution = deps.load_latest_language_distribution(artifact_dir)
    thresholds = deps.ClusterDriftThresholds(
        singleton_rate_warn=deps.settings.CLUSTER_DRIFT_SINGLETON_RATE_WARN_THRESHOLD,
        large_cluster_rate_warn=deps.settings.CLUSTER_DRIFT_LARGE_CLUSTER_RATE_WARN_THRESHOLD,
        contradiction_rate_warn=deps.settings.CLUSTER_DRIFT_CONTRADICTION_RATE_WARN_THRESHOLD,
        language_drift_warn=deps.settings.CLUSTER_DRIFT_LANGUAGE_DRIFT_WARN_THRESHOLD,
        large_cluster_size=deps.settings.CLUSTER_DRIFT_LARGE_CLUSTER_SIZE,
    )
    summary = deps.compute_cluster_drift_summary(
        event_samples=event_samples,
        thresholds=thresholds,
        baseline_language_distribution=baseline_distribution,
        window_start=window_start,
        window_end=window_end,
    )
    artifact_path = deps.write_cluster_drift_artifact(
        artifact_dir=artifact_dir,
        summary=summary,
    )
    warning_keys = summary.get("warning_keys")
    warnings = list(warning_keys) if isinstance(warning_keys, list) else []

    return {
        "status": "ok",
        "task": "monitor_cluster_drift",
        "artifact_path": str(artifact_path),
        "window_start": summary["window_start"],
        "window_end": summary["window_end"],
        "event_count": summary["event_count"],
        "warning_keys": warnings,
        "singleton_rate": summary["singleton_rate"],
        "large_cluster_rate": summary["large_cluster_rate"],
        "contradiction_rate": summary["contradiction_rate"],
        "language_drift_score": summary["language_drift_score"],
    }
