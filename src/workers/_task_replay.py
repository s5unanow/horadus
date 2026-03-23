from __future__ import annotations

from datetime import datetime
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


def serialize_replay_state(*, item: Any) -> dict[str, Any]:
    details_value = getattr(item, "details", None)
    details = details_value if isinstance(details_value, dict) else {}
    return {
        "status": getattr(item, "status", None),
        "attempt_count": int(getattr(item, "attempt_count", 0) or 0),
        "last_attempt_at": _serialize_replay_timestamp(getattr(item, "last_attempt_at", None)),
        "processed_at": _serialize_replay_timestamp(getattr(item, "processed_at", None)),
        "last_error": getattr(item, "last_error", None),
        "replay_failure": details.get("replay_failure") if isinstance(details, dict) else None,
        "replay_result": details.get("replay_result") if isinstance(details, dict) else None,
    }


async def fresh_replay_state(*, deps: Any, item_id: Any) -> dict[str, Any] | None:
    async with deps.async_session_maker() as session:
        replay_item = await session.get(deps.LLMReplayQueueItem, item_id)
        if replay_item is None:
            return None
        return serialize_replay_state(item=replay_item)


async def fresh_replay_status(*, deps: Any, item_id: Any) -> str | None:
    state = await fresh_replay_state(deps=deps, item_id=item_id)
    status = state.get("status") if state is not None else None
    return str(status) if isinstance(status, str) else None


def _serialize_replay_timestamp(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None
