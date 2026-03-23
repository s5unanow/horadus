from __future__ import annotations

from typing import Any


async def build_replay_runtime(*, deps: Any, session: Any) -> tuple[list[Any], Any, Any]:
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
    return trends, tier2, pipeline


async def fresh_replay_status(*, deps: Any, item_id: Any) -> str | None:
    async with deps.async_session_maker() as session:
        replay_item = await session.get(deps.LLMReplayQueueItem, item_id)
        if replay_item is None:
            return None
        status = getattr(replay_item, "status", None)
        return str(status) if isinstance(status, str) else None
