from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypedDict


@dataclass(frozen=True, slots=True)
class ReviewLoopContext:
    repo: str
    pr_number: int
    head_oid: str
    wait_window_started_at: datetime
    deadline_epoch: float


class ReviewWindowFields(TypedDict):
    wait_window_started_at: str
    deadline_at: str
    remaining_seconds: int


def deadline_at(deadline_epoch: float) -> datetime:
    return datetime.fromtimestamp(deadline_epoch, tz=UTC)


def remaining_seconds(deadline_epoch: float) -> int:
    return max(0, math.ceil(deadline_epoch - time.time()))


def review_window_fields(loop_context: ReviewLoopContext) -> ReviewWindowFields:
    return {
        "wait_window_started_at": loop_context.wait_window_started_at.isoformat(),
        "deadline_at": deadline_at(loop_context.deadline_epoch).isoformat(),
        "remaining_seconds": remaining_seconds(loop_context.deadline_epoch),
    }


__all__ = [
    "ReviewLoopContext",
    "ReviewWindowFields",
    "deadline_at",
    "remaining_seconds",
    "review_window_fields",
]
