"""Terminal-state and feedback suppression for Tier-2 candidate staging."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from src.processing.pipeline_types import PipelineUsage, _ItemExecution, _PreparedItem
from src.storage.event_state import EventActivityState, EventEpistemicState
from src.storage.models import Event, ProcessingStatus

if TYPE_CHECKING:
    from src.processing.event_cluster_link import ClusterResult

logger = structlog.get_logger(__name__)

_TERMINAL_ACTION_PREFIX = "terminal_"


async def resolve_processing_event_suppression(
    *,
    owner: Any,
    event: Event,
    cluster_result: ClusterResult,
) -> str | None:
    """Return terminal-state suppression before consulting feedback."""
    if event.epistemic_state == EventEpistemicState.RETRACTED.value:
        return "terminal_retracted"
    if event.activity_state == EventActivityState.CLOSED.value:
        return "terminal_closed"
    action = await owner._event_suppression_action(event_id=cluster_result.event_id)
    return action if isinstance(action, str) else None


async def suppress_tier2_candidate(
    *,
    owner: Any,
    prepared: _PreparedItem,
    cluster_result: ClusterResult,
    embedded: bool,
    usage: PipelineUsage,
    action: str,
) -> tuple[None, _ItemExecution]:
    """Finish an item without Tier-2 work for a suppressed event."""
    item = prepared.item
    item.processing_status = (
        ProcessingStatus.CLASSIFIED
        if action.startswith(_TERMINAL_ACTION_PREFIX)
        else ProcessingStatus.NOISE
    )
    item.processing_started_at = None
    await owner.session.flush()
    owner.record_processing_event_suppression(
        action=action,
        stage="pipeline_post_cluster",
    )
    logger.info(
        "Skipping suppressed event after clustering",
        item_id=str(prepared.item_id),
        event_id=str(cluster_result.event_id),
        action=action,
    )
    return (
        None,
        _ItemExecution(
            result=owner._build_item_result(
                item_id=prepared.item_id,
                status=item.processing_status,
                cluster_result=cluster_result,
                embedded=embedded,
            ),
            usage=usage,
        ),
    )
