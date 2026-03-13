from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast


@dataclass(slots=True)
class ProcessingDispatchPlan:
    should_dispatch: bool
    reason: str
    task_limit: int
    pending_backlog: int
    in_flight: int
    budget_status: str
    budget_remaining_usd: float | None


def build_processing_dispatch_plan(
    *,
    deps: Any,
    stored_items: int,
    pending_backlog: int,
    in_flight: int,
    budget_status: str,
    budget_remaining_usd: float | None,
    daily_cost_limit_usd: float,
) -> ProcessingDispatchPlan:
    if stored_items <= 0:
        return ProcessingDispatchPlan(
            should_dispatch=False,
            reason="no_new_items",
            task_limit=0,
            pending_backlog=max(0, pending_backlog),
            in_flight=max(0, in_flight),
            budget_status=budget_status,
            budget_remaining_usd=budget_remaining_usd,
        )
    if not deps.settings.ENABLE_PROCESSING_PIPELINE:
        return ProcessingDispatchPlan(
            should_dispatch=False,
            reason="pipeline_disabled",
            task_limit=0,
            pending_backlog=max(0, pending_backlog),
            in_flight=max(0, in_flight),
            budget_status=budget_status,
            budget_remaining_usd=budget_remaining_usd,
        )

    max_in_flight = max(1, deps.settings.PROCESSING_DISPATCH_MAX_IN_FLIGHT)
    if in_flight >= max_in_flight:
        return ProcessingDispatchPlan(
            should_dispatch=False,
            reason="in_flight_throttle",
            task_limit=0,
            pending_backlog=max(0, pending_backlog),
            in_flight=max(0, in_flight),
            budget_status=budget_status,
            budget_remaining_usd=budget_remaining_usd,
        )

    queue_limit = max(1, deps.settings.PROCESSING_PIPELINE_BATCH_SIZE)
    base_limit = min(queue_limit, max(stored_items, min(pending_backlog, queue_limit)))
    if budget_status == "sleep_mode":
        return ProcessingDispatchPlan(
            should_dispatch=False,
            reason="budget_denied",
            task_limit=0,
            pending_backlog=max(0, pending_backlog),
            in_flight=max(0, in_flight),
            budget_status=budget_status,
            budget_remaining_usd=budget_remaining_usd,
        )

    min_headroom_pct = max(0, deps.settings.PROCESSING_DISPATCH_MIN_BUDGET_HEADROOM_PCT)
    if (
        budget_remaining_usd is not None
        and daily_cost_limit_usd > 0
        and min_headroom_pct > 0
        and ((budget_remaining_usd / daily_cost_limit_usd) * 100.0) <= min_headroom_pct
    ):
        throttled_limit = min(
            base_limit,
            max(1, deps.settings.PROCESSING_DISPATCH_LOW_HEADROOM_LIMIT),
        )
        return ProcessingDispatchPlan(
            should_dispatch=throttled_limit > 0,
            reason="budget_low_headroom",
            task_limit=throttled_limit,
            pending_backlog=max(0, pending_backlog),
            in_flight=max(0, in_flight),
            budget_status=budget_status,
            budget_remaining_usd=budget_remaining_usd,
        )

    return ProcessingDispatchPlan(
        should_dispatch=True,
        reason="ok",
        task_limit=base_limit,
        pending_backlog=max(0, pending_backlog),
        in_flight=max(0, in_flight),
        budget_status=budget_status,
        budget_remaining_usd=budget_remaining_usd,
    )


def get_redis_client(*, deps: Any) -> Any:
    return deps.redis.from_url(deps.settings.REDIS_URL, decode_responses=True)


def get_processing_in_flight_count(*, deps: Any) -> int:
    client: Any | None = None
    try:
        client = deps._get_redis_client()
        raw_value = client.get(deps.PROCESSING_IN_FLIGHT_KEY)
        return max(0, int(raw_value or 0))
    except Exception:
        return 0
    finally:
        if client is not None:
            client.close()


def increment_processing_in_flight(*, deps: Any) -> int:
    client: Any | None = None
    try:
        client = deps._get_redis_client()
        current = int(client.incr(deps.PROCESSING_IN_FLIGHT_KEY))
        client.expire(deps.PROCESSING_IN_FLIGHT_KEY, 3600)
        return max(0, current)
    except Exception:
        return 0
    finally:
        if client is not None:
            client.close()


def decrement_processing_in_flight(*, deps: Any) -> int:
    client: Any | None = None
    try:
        client = deps._get_redis_client()
        updated = int(client.decr(deps.PROCESSING_IN_FLIGHT_KEY))
        if updated <= 0:
            client.delete(deps.PROCESSING_IN_FLIGHT_KEY)
            return 0
        return updated
    except Exception:
        return 0
    finally:
        if client is not None:
            client.close()


def acquire_processing_dispatch_lock(*, deps: Any) -> bool:
    lock_ttl = max(0, deps.settings.PROCESSING_DISPATCH_LOCK_TTL_SECONDS)
    if lock_ttl == 0:
        return True

    client: Any | None = None
    try:
        client = deps._get_redis_client()
        acquired = client.set(
            deps.PROCESSING_DISPATCH_LOCK_KEY,
            datetime.now(tz=UTC).isoformat(),
            ex=lock_ttl,
            nx=True,
        )
        return bool(acquired)
    except Exception:
        return True
    finally:
        if client is not None:
            client.close()


async def load_processing_dispatch_inputs_async(*, deps: Any) -> dict[str, Any]:
    async with deps.async_session_maker() as session:
        pending_count_raw = await session.scalar(
            deps.select(deps.func.count(deps.RawItem.id)).where(
                deps.RawItem.processing_status == deps.ProcessingStatus.PENDING
            )
        )
        pending_count = int(pending_count_raw or 0)
        budget_summary = await deps.CostTracker(session=session).get_daily_summary()
    return {
        "pending_backlog": pending_count,
        "budget_status": str(budget_summary.get("status", "active")),
        "budget_remaining_usd": budget_summary.get("budget_remaining_usd"),
        "daily_cost_limit_usd": float(budget_summary.get("daily_cost_limit_usd", 0.0) or 0.0),
    }


def queue_processing_for_new_items(*, deps: Any, collector: str, stored_items: int) -> bool:
    dispatch_inputs = deps._run_async(deps._load_processing_dispatch_inputs_async())
    pending_backlog = int(dispatch_inputs["pending_backlog"])
    budget_status = str(dispatch_inputs["budget_status"])
    budget_remaining_raw = dispatch_inputs.get("budget_remaining_usd")
    budget_remaining = (
        float(budget_remaining_raw) if isinstance(budget_remaining_raw, int | float) else None
    )
    daily_cost_limit = float(dispatch_inputs.get("daily_cost_limit_usd", 0.0) or 0.0)
    in_flight = deps._get_processing_in_flight_count()

    plan = deps._build_processing_dispatch_plan(
        stored_items=stored_items,
        pending_backlog=pending_backlog,
        in_flight=in_flight,
        budget_status=budget_status,
        budget_remaining_usd=budget_remaining,
        daily_cost_limit_usd=daily_cost_limit,
    )
    deps.record_processing_backlog_depth(pending_count=pending_backlog)

    if plan.should_dispatch and not deps._acquire_processing_dispatch_lock():
        deps.record_processing_dispatch_decision(
            dispatched=False,
            reason="dispatch_lock_active",
        )
        deps.logger.info(
            "Skipped processing dispatch due to active dispatch lock",
            collector=collector,
            stored_items=stored_items,
            pending_backlog=pending_backlog,
            in_flight=in_flight,
        )
        return False

    if not plan.should_dispatch:
        deps.record_processing_dispatch_decision(dispatched=False, reason=plan.reason)
        deps.logger.info(
            "Skipped processing dispatch",
            collector=collector,
            stored_items=stored_items,
            reason=plan.reason,
            pending_backlog=plan.pending_backlog,
            in_flight=plan.in_flight,
            budget_status=plan.budget_status,
            budget_remaining_usd=plan.budget_remaining_usd,
        )
        return False

    cast("Any", deps.process_pending_items).delay(limit=plan.task_limit)
    deps.record_processing_dispatch_decision(dispatched=True, reason=plan.reason)
    deps.logger.info(
        "Queued processing pipeline task",
        collector=collector,
        stored_items=stored_items,
        task_limit=plan.task_limit,
        pending_backlog=plan.pending_backlog,
        in_flight=plan.in_flight,
        budget_status=plan.budget_status,
        budget_remaining_usd=plan.budget_remaining_usd,
    )
    return True


async def process_pending_async(*, deps: Any, limit: int) -> dict[str, Any]:
    async with deps.async_session_maker() as session:
        degraded_tracker = (
            deps.DegradedLLMTracker(stage="tier2")
            if deps.settings.LLM_DEGRADED_MODE_ENABLED
            else None
        )

        tier2_model = deps.settings.LLM_TIER2_MODEL
        if degraded_tracker is not None and deps.settings.LLM_DEGRADED_CANARY_ENABLED:
            try:
                primary_canary = await deps.run_tier2_canary(
                    model=deps.settings.LLM_TIER2_MODEL,
                    api_key=deps.settings.OPENAI_API_KEY,
                    base_url=deps.settings.LLM_PRIMARY_BASE_URL,
                    max_items=deps.settings.LLM_DEGRADED_CANARY_MAX_TIER2_ITEMS,
                )
            except Exception as exc:
                primary_canary = None
                degraded_tracker.latch_quality_degraded(
                    ttl_seconds=deps.settings.LLM_DEGRADED_CANARY_QUALITY_TTL_SECONDS,
                    reason=f"primary_canary_error:{type(exc).__name__}",
                )

            if primary_canary is not None and primary_canary.passed:
                degraded_tracker.clear_quality_degraded()
            elif primary_canary is not None:
                emergency_model = deps.settings.LLM_TIER2_EMERGENCY_MODEL
                if isinstance(emergency_model, str) and emergency_model.strip():
                    try:
                        emergency_canary = await deps.run_tier2_canary(
                            model=emergency_model.strip(),
                            api_key=deps.settings.OPENAI_API_KEY,
                            base_url=deps.settings.LLM_PRIMARY_BASE_URL,
                            max_items=deps.settings.LLM_DEGRADED_CANARY_MAX_TIER2_ITEMS,
                        )
                    except Exception as exc:
                        emergency_canary = None
                        degraded_tracker.latch_quality_degraded(
                            ttl_seconds=deps.settings.LLM_DEGRADED_CANARY_QUALITY_TTL_SECONDS,
                            reason=f"emergency_canary_error:{type(exc).__name__}",
                        )
                    else:
                        if emergency_canary is not None and emergency_canary.passed:
                            tier2_model = emergency_model.strip()
                            degraded_tracker.clear_quality_degraded()
                        else:
                            degraded_tracker.latch_quality_degraded(
                                ttl_seconds=deps.settings.LLM_DEGRADED_CANARY_QUALITY_TTL_SECONDS,
                                reason=(
                                    "primary:"
                                    f"{primary_canary.reason};emergency:"
                                    f"{getattr(emergency_canary, 'reason', 'unknown')}"
                                ),
                            )
                else:
                    degraded_tracker.latch_quality_degraded(
                        ttl_seconds=deps.settings.LLM_DEGRADED_CANARY_QUALITY_TTL_SECONDS,
                        reason=f"primary:{primary_canary.reason}",
                    )

        tier2_classifier = deps.Tier2Classifier(session=session, model=tier2_model)
        pipeline = deps.ProcessingPipeline(
            session=session,
            tier2_classifier=tier2_classifier,
            degraded_llm_tracker=degraded_tracker,
        )
        run_result = await pipeline.process_pending_items(limit=limit)
        await session.commit()

    return {
        "status": "ok",
        "task": "processing_pipeline",
        **deps.ProcessingPipeline.run_result_to_dict(run_result),
    }


async def reap_stale_processing_async(*, deps: Any) -> dict[str, Any]:
    now = datetime.now(tz=UTC)
    stale_before = now - timedelta(minutes=deps.settings.PROCESSING_STALE_TIMEOUT_MINUTES)
    async with deps.async_session_maker() as session:
        stale_items = list(
            (
                await session.scalars(
                    deps.select(deps.RawItem)
                    .where(deps.RawItem.processing_status == deps.ProcessingStatus.PROCESSING)
                    .where(deps.RawItem.processing_started_at.is_not(None))
                    .where(deps.RawItem.processing_started_at <= stale_before)
                    .order_by(deps.RawItem.processing_started_at.asc())
                    .limit(max(1, deps.settings.PROCESSING_PIPELINE_BATCH_SIZE))
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )

        reset_item_ids: list[str] = []
        for item in stale_items:
            item.processing_status = deps.ProcessingStatus.PENDING
            item.processing_started_at = None
            item.error_message = None
            reset_item_ids.append(str(item.id))

        await session.commit()

    deps.logger.info(
        "Reaped stale processing items",
        scanned=len(stale_items),
        reset_count=len(reset_item_ids),
        reset_item_ids=reset_item_ids,
        stale_before=stale_before.isoformat(),
    )
    return {
        "status": "ok",
        "task": "reap_stale_processing_items",
        "checked_at": now.isoformat(),
        "stale_before": stale_before.isoformat(),
        "scanned": len(stale_items),
        "reset": len(reset_item_ids),
        "reset_item_ids": reset_item_ids,
    }
