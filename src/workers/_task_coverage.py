from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.core.observability import record_coverage_drop_alert, record_coverage_health
from src.core.source_coverage import (
    DEFAULT_COVERAGE_ARTIFACT_DIR,
    DEFAULT_COVERAGE_LOOKBACK_HOURS,
    build_source_coverage_report,
    load_latest_coverage_snapshot,
    persist_coverage_snapshot,
    write_source_coverage_artifact,
)


async def monitor_source_coverage_async(
    *,
    async_session_maker: Callable[[], Any],
    logger: Any,
) -> dict[str, Any]:
    artifact_path: Path | None = None
    async with async_session_maker() as session:
        try:
            previous_snapshot = await load_latest_coverage_snapshot(session)
            previous_payload = previous_snapshot.payload if previous_snapshot is not None else None
            report = await build_source_coverage_report(
                session=session,
                lookback_hours=DEFAULT_COVERAGE_LOOKBACK_HOURS,
                previous_snapshot_payload=previous_payload,
            )
            artifact_path = write_source_coverage_artifact(
                report=report,
                artifact_dir=DEFAULT_COVERAGE_ARTIFACT_DIR,
            )
            snapshot = await persist_coverage_snapshot(
                session,
                report=report,
                artifact_path=str(artifact_path),
            )
            await session.commit()
        except Exception:
            if artifact_path is not None:
                artifact_path.unlink(missing_ok=True)
                artifact_path.with_name("source-coverage-latest.json").unlink(missing_ok=True)
            raise

    record_coverage_health(report=report)
    for alert in report.alerts:
        record_coverage_drop_alert(severity=alert.severity, dimension=alert.dimension)

    if report.alerts:
        logger.warning(
            "Source coverage drop alerts detected",
            alert_count=len(report.alerts),
            alerts=[
                {
                    "severity": alert.severity,
                    "dimension": alert.dimension,
                    "key": alert.key,
                    "current_seen": alert.current_seen,
                    "previous_seen": alert.previous_seen,
                }
                for alert in report.alerts[:5]
            ],
        )

    return {
        "status": "ok",
        "task": "monitor_source_coverage",
        "generated_at": report.generated_at.isoformat(),
        "window_start": report.window_start.isoformat(),
        "window_end": report.window_end.isoformat(),
        "lookback_hours": report.lookback_hours,
        "snapshot_id": str(snapshot.id),
        "artifact_path": str(Path(artifact_path)),
        "total_seen": report.total.seen,
        "total_processable": report.total.processable,
        "total_processed": report.total.processed,
        "alert_count": len(report.alerts),
        "alerts": [
            {
                "severity": alert.severity,
                "dimension": alert.dimension,
                "key": alert.key,
                "message": alert.message,
            }
            for alert in report.alerts
        ],
    }


def build_monitor_source_coverage_task(
    *,
    typed_shared_task: Callable[..., Any],
    run_async: Callable[[Any], dict[str, Any]],
    run_task_with_heartbeat: Callable[..., dict[str, Any]],
    async_session_maker: Callable[[], Any],
    logger: Any,
) -> Any:
    @typed_shared_task(name="workers.monitor_source_coverage")  # type: ignore[untyped-decorator]
    def monitor_source_coverage() -> dict[str, Any]:
        def _runner() -> dict[str, Any]:
            logger.info("Starting source coverage monitor task")
            result = run_async(
                monitor_source_coverage_async(
                    async_session_maker=async_session_maker,
                    logger=logger,
                )
            )
            logger.info(
                "Finished source coverage monitor task",
                total_seen=result["total_seen"],
                total_processed=result["total_processed"],
                alert_count=result["alert_count"],
                artifact_path=result["artifact_path"],
            )
            return result

        return run_task_with_heartbeat(task_name="workers.monitor_source_coverage", runner=_runner)

    return monitor_source_coverage
