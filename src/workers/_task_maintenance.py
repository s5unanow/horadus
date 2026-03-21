from __future__ import annotations

from datetime import UTC, datetime
from inspect import signature
from typing import Any
from uuid import UUID

from sqlalchemy import select

from src.storage.event_lineage_models import EventLineage
from src.storage.models import LLMReplayQueueItem


def _replay_provenance_derivation(*, item: Any, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "replay_queue",
        "queue_item_id": str(item.id),
        "original_extraction_provenance": details.get("original_extraction_provenance"),
    }


async def _replay_one_degraded_item(
    *,
    deps: Any,
    session: Any,
    tier2: Any,
    pipeline: Any,
    trends: list[Any],
    item: Any,
    now: datetime,
) -> bool:
    event = await session.get(deps.Event, item.event_id)
    if event is None:
        raise ValueError(f"Event not found: {item.event_id}")
    details = dict(item.details or {})
    classify_kwargs = {"event": event, "trends": trends}
    if "provenance_derivation" in signature(tier2.classify_event).parameters:
        classify_kwargs["provenance_derivation"] = _replay_provenance_derivation(
            item=item,
            details=details,
        )
    await tier2.classify_event(**classify_kwargs)
    impacts_seen, updates_applied = await pipeline._apply_trend_impacts(
        event=event,
        trends=trends,
    )
    item.status = "done"
    item.processed_at = now
    item.locked_at = None
    item.locked_by = None
    item.last_error = None
    details["replay_result"] = {
        "impacts_seen": impacts_seen,
        "updates_applied": updates_applied,
        "processed_at": now.isoformat(),
        "model": deps.settings.LLM_TIER2_MODEL,
    }
    item.details = details
    await session.flush()
    await _sync_lineage_replay_status(session=session, event_id=item.event_id)
    return True


async def _sync_lineage_replay_status(*, session: Any, event_id: Any) -> None:
    relevant_lineages = [
        lineage
        for lineage in (
            await session.scalars(
                select(EventLineage).where(
                    (EventLineage.source_event_id == event_id)
                    | (EventLineage.target_event_id == event_id)
                )
            )
        ).all()
        if str(event_id)
        in {str(value) for value in (lineage.details or {}).get("replay_enqueued_event_ids", [])}
    ]
    if not relevant_lineages:
        return

    replay_event_ids = {
        parsed_id
        for lineage in relevant_lineages
        for parsed_id in _parse_lineage_replay_ids(lineage)
    }
    status_rows = (
        await session.execute(
            select(LLMReplayQueueItem.event_id, LLMReplayQueueItem.status)
            .where(LLMReplayQueueItem.stage == "tier2")
            .where(LLMReplayQueueItem.event_id.in_(tuple(replay_event_ids)))
        )
    ).all()
    status_by_event_id = {str(row[0]): row[1] for row in status_rows}
    for lineage in relevant_lineages:
        replay_ids = tuple(str(parsed_id) for parsed_id in _parse_lineage_replay_ids(lineage))
        if not replay_ids:
            continue
        replay_statuses = {status_by_event_id.get(replay_id) for replay_id in replay_ids}
        details = dict(lineage.details or {})
        if "error" in replay_statuses:
            details["status"] = "replay_error"
            lineage.details = details
        elif all(status_by_event_id.get(replay_id) == "done" for replay_id in replay_ids):
            details["status"] = "replay_complete"
            lineage.details = details


def _parse_lineage_replay_ids(lineage: EventLineage) -> tuple[UUID, ...]:
    parsed_ids: list[UUID] = []
    for value in (lineage.details or {}).get("replay_enqueued_event_ids", []):
        try:
            parsed_ids.append(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return tuple(parsed_ids)


async def snapshot_trends_async(*, deps: Any) -> dict[str, Any]:
    snapshot_time = datetime.now(tz=UTC).replace(second=0, microsecond=0)
    async with deps.async_session_maker() as session:
        trends = list(
            (
                await session.scalars(
                    deps.select(deps.Trend)
                    .where(deps.Trend.is_active.is_(True))
                    .order_by(deps.Trend.name.asc())
                )
            ).all()
        )

        created = 0
        skipped = 0
        for trend in trends:
            trend_id = trend.id
            if trend_id is None:
                skipped += 1
                continue

            existing = await session.scalar(
                deps.select(deps.TrendSnapshot.trend_id)
                .where(deps.TrendSnapshot.trend_id == trend_id)
                .where(deps.TrendSnapshot.timestamp == snapshot_time)
                .limit(1)
            )
            if existing is not None:
                skipped += 1
                continue

            session.add(
                deps.TrendSnapshot(
                    trend_id=trend_id,
                    timestamp=snapshot_time,
                    log_odds=float(trend.current_log_odds),
                )
            )
            created += 1

        await session.commit()

    return {
        "status": "ok",
        "task": "snapshot_trends",
        "timestamp": snapshot_time.isoformat(),
        "scanned": len(trends),
        "created": created,
        "skipped": skipped,
    }


async def decay_trends_async(*, deps: Any) -> dict[str, Any]:
    as_of = datetime.now(tz=UTC)
    async with deps.async_session_maker() as session:
        engine = deps.TrendEngine(session=session)
        trends = list(
            (
                await session.scalars(
                    deps.select(deps.Trend)
                    .where(deps.Trend.is_active.is_(True))
                    .order_by(deps.Trend.name.asc())
                )
            ).all()
        )

        decayed = 0
        unchanged = 0
        for trend in trends:
            previous_probability = engine.get_probability(trend)
            new_probability = await engine.apply_decay(trend=trend, as_of=as_of)
            if abs(new_probability - previous_probability) > 1e-12:
                decayed += 1
            else:
                unchanged += 1
            deps.logger.debug(
                "Applied trend decay",
                trend_id=str(trend.id),
                trend_name=trend.name,
                previous_probability=previous_probability,
                new_probability=new_probability,
            )

        await session.commit()

    return {
        "status": "ok",
        "task": "apply_trend_decay",
        "as_of": as_of.isoformat(),
        "scanned": len(trends),
        "decayed": decayed,
        "unchanged": unchanged,
    }


async def check_event_lifecycles_async(*, deps: Any) -> dict[str, Any]:
    async with deps.async_session_maker() as session:
        manager = deps.EventLifecycleManager(session)
        run_result = await manager.run_decay_check()
        await session.commit()

    return {
        "status": "ok",
        **run_result,
    }


async def generate_weekly_reports_async(*, deps: Any) -> dict[str, Any]:
    async with deps.async_session_maker() as session:
        generator = deps.ReportGenerator(session=session)
        run_result = await generator.generate_weekly_reports()
        await session.commit()

    return {
        "status": "ok",
        "task": "generate_weekly_reports",
        "period_start": run_result.period_start.isoformat(),
        "period_end": run_result.period_end.isoformat(),
        "scanned": run_result.scanned,
        "created": run_result.created,
        "updated": run_result.updated,
    }


async def generate_monthly_reports_async(*, deps: Any) -> dict[str, Any]:
    async with deps.async_session_maker() as session:
        generator = deps.ReportGenerator(session=session)
        run_result = await generator.generate_monthly_reports()
        await session.commit()

    return {
        "status": "ok",
        "task": "generate_monthly_reports",
        "period_start": run_result.period_start.isoformat(),
        "period_end": run_result.period_end.isoformat(),
        "scanned": run_result.scanned,
        "created": run_result.created,
        "updated": run_result.updated,
    }


async def replay_degraded_events_async(*, deps: Any, limit: int) -> dict[str, Any]:
    tracker = (
        deps.DegradedLLMTracker(stage="tier2") if deps.settings.LLM_DEGRADED_MODE_ENABLED else None
    )
    if tracker is not None:
        status = await deps.asyncio.to_thread(tracker.evaluate)
        if status.is_degraded:
            return {
                "status": "skipped",
                "task": "replay_degraded_events",
                "reason": "degraded_llm_active",
                "stage": status.stage,
                "window": {
                    "total_calls": status.window.total_calls,
                    "secondary_calls": status.window.secondary_calls,
                    "failover_ratio": round(status.window.failover_ratio, 6),
                },
            }

    now = datetime.now(tz=UTC)
    async with deps.async_session_maker() as session:
        run_limit = max(1, int(limit))
        rows = (
            await session.scalars(
                deps.select(deps.LLMReplayQueueItem)
                .where(deps.LLMReplayQueueItem.status == "pending")
                .order_by(
                    deps.LLMReplayQueueItem.priority.desc(),
                    deps.LLMReplayQueueItem.enqueued_at.asc(),
                )
                .limit(run_limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
        items = list(rows)
        if not items:
            return {
                "status": "ok",
                "task": "replay_degraded_events",
                "drained": 0,
                "errors": 0,
            }

        for item in items:
            item.status = "processing"
            item.locked_at = now
            item.locked_by = "workers.replay_degraded_events"
            item.attempt_count = int(item.attempt_count or 0) + 1
            item.last_attempt_at = now
        await session.flush()

        trends = list(
            (
                await session.scalars(
                    deps.select(deps.Trend)
                    .where(deps.Trend.is_active.is_(True))
                    .order_by(deps.Trend.name.asc())
                )
            ).all()
        )
        tier2 = deps.Tier2Classifier(
            session=session,
            model=deps.settings.LLM_TIER2_MODEL,
            secondary_model=None,
        )
        pipeline = deps.ProcessingPipeline(
            session=session,
            tier2_classifier=tier2,
            degraded_llm_tracker=None,
        )

        drained = 0
        errors = 0
        for item in items:
            drained += 1
            try:
                await _replay_one_degraded_item(
                    deps=deps,
                    session=session,
                    tier2=tier2,
                    pipeline=pipeline,
                    trends=trends,
                    item=item,
                    now=now,
                )
            except Exception as exc:
                errors += 1
                item.status = "error"
                item.last_error = str(exc)[:1000]
                item.locked_at = None
                item.locked_by = None
        await session.commit()

    return {
        "status": "ok",
        "task": "replay_degraded_events",
        "drained": drained,
        "errors": errors,
    }
