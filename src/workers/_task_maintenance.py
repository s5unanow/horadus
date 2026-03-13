from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


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
                event = await session.get(deps.Event, item.event_id)
                if event is None:
                    raise ValueError(f"Event not found: {item.event_id}")
                await tier2.classify_event(event=event, trends=trends)
                impacts_seen, updates_applied = await pipeline._apply_trend_impacts(
                    event=event,
                    trends=trends,
                )
                item.status = "done"
                item.processed_at = now
                item.locked_at = None
                item.locked_by = None
                item.last_error = None
                details = dict(item.details or {})
                details["replay_result"] = {
                    "impacts_seen": impacts_seen,
                    "updates_applied": updates_applied,
                    "processed_at": now.isoformat(),
                    "model": deps.settings.LLM_TIER2_MODEL,
                }
                item.details = details
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
