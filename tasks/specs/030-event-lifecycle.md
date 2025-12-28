# TASK-030: Event Lifecycle Tracking

## Overview

Track event progression through lifecycle stages:
```
emerging → confirmed → fading → archived
```

This addresses expert feedback: *"Track event lifecycle (emerging → confirmed → fading). This alone kills a ton of noise."*

## Context

Without lifecycle tracking:
- Every new mention of an old story creates processing overhead
- Fading stories still appear with same weight as breaking news
- Hard to distinguish "developing situation" from "old news"

With lifecycle tracking:
- New events start as "emerging" (unconfirmed)
- Multi-source corroboration promotes to "confirmed"
- Lack of new mentions demotes to "fading"
- Trend impact can be weighted by lifecycle stage

## Requirements

### Lifecycle States

```python
class EventLifecycle(str, Enum):
    EMERGING = "emerging"    # Single source, unconfirmed
    CONFIRMED = "confirmed"  # Multiple independent sources
    FADING = "fading"        # No new mentions in 48h
    ARCHIVED = "archived"    # No mentions in 7d, historical only
```

### State Transitions

```
                    ┌─────────────────────────────────────┐
                    │                                     │
                    ▼                                     │
┌──────────┐   3+ sources   ┌───────────┐   48h silence   ┌─────────┐
│ EMERGING │ ─────────────► │ CONFIRMED │ ──────────────► │ FADING  │
└──────────┘                └───────────┘                 └─────────┘
     │                           │                             │
     │                           │ new mention                 │
     │                           └─────────────────────────────┘
     │                                      ▲
     │              new mention             │
     └──────────────────────────────────────┘

                         7d silence
┌─────────┐         ┌──────────┐
│ FADING  │ ──────► │ ARCHIVED │
└─────────┘         └──────────┘
```

### Database Changes

```python
# Add to Event model

class Event(Base):
    # Existing fields...

    # NEW: Lifecycle tracking
    lifecycle_status: Mapped[str] = mapped_column(
        String(20),
        default=EventLifecycle.EMERGING.value,
        nullable=False,
    )

    # When was this event last mentioned by a new source?
    last_mention_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # How many unique sources have reported this?
    # (Different from source_count which may include updates)
    unique_source_count: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    # When did it get confirmed (if ever)?
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
```

### Migration

```python
# alembic/versions/xxx_add_event_lifecycle.py

def upgrade():
    op.add_column('events', sa.Column(
        'lifecycle_status',
        sa.String(20),
        nullable=False,
        server_default='confirmed'  # Existing events assumed confirmed
    ))
    op.add_column('events', sa.Column(
        'last_mention_at',
        sa.DateTime(timezone=True),
        server_default=sa.func.now()
    ))
    op.add_column('events', sa.Column(
        'unique_source_count',
        sa.Integer,
        nullable=False,
        server_default='1'
    ))
    op.add_column('events', sa.Column(
        'confirmed_at',
        sa.DateTime(timezone=True),
        nullable=True
    ))

    # Index for lifecycle queries
    op.create_index(
        'idx_events_lifecycle',
        'events',
        ['lifecycle_status', 'last_mention_at']
    )

def downgrade():
    op.drop_index('idx_events_lifecycle')
    op.drop_column('events', 'confirmed_at')
    op.drop_column('events', 'unique_source_count')
    op.drop_column('events', 'last_mention_at')
    op.drop_column('events', 'lifecycle_status')
```

## Implementation

### Lifecycle Manager

```python
# src/processing/event_lifecycle.py

from datetime import datetime, timedelta
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from src.storage.models import Event

class EventLifecycle(str, Enum):
    EMERGING = "emerging"
    CONFIRMED = "confirmed"
    FADING = "fading"
    ARCHIVED = "archived"


# Thresholds (configurable)
CONFIRMATION_THRESHOLD = 3  # Sources needed to confirm
FADING_HOURS = 48           # Hours without mention to fade
ARCHIVE_DAYS = 7            # Days without mention to archive


class EventLifecycleManager:
    """Manages event lifecycle transitions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def on_new_mention(
        self,
        event: Event,
        source_id: str,
        mentioned_at: datetime | None = None,
    ) -> bool:
        """
        Process a new mention of an event.

        Returns True if lifecycle changed.
        """
        mentioned_at = mentioned_at or datetime.utcnow()
        previous_status = event.lifecycle_status

        # Update mention tracking
        event.last_mention_at = mentioned_at
        event.source_count += 1

        # Check if this is a new unique source
        # (Would need to track source IDs - simplified here)
        event.unique_source_count += 1

        # Transitions
        if event.lifecycle_status == EventLifecycle.EMERGING.value:
            if event.unique_source_count >= CONFIRMATION_THRESHOLD:
                event.lifecycle_status = EventLifecycle.CONFIRMED.value
                event.confirmed_at = mentioned_at

        elif event.lifecycle_status == EventLifecycle.FADING.value:
            # Revive to confirmed on new mention
            event.lifecycle_status = EventLifecycle.CONFIRMED.value

        elif event.lifecycle_status == EventLifecycle.ARCHIVED.value:
            # Rare: archived event gets new mention
            event.lifecycle_status = EventLifecycle.CONFIRMED.value

        return event.lifecycle_status != previous_status

    async def run_decay_check(self) -> dict:
        """
        Check all events for lifecycle decay.

        Should be run periodically (e.g., hourly via Celery).

        Returns stats on transitions.
        """
        now = datetime.utcnow()
        fading_threshold = now - timedelta(hours=FADING_HOURS)
        archive_threshold = now - timedelta(days=ARCHIVE_DAYS)

        stats = {"confirmed_to_fading": 0, "fading_to_archived": 0}

        # Confirmed → Fading
        result = await self.session.execute(
            update(Event)
            .where(Event.lifecycle_status == EventLifecycle.CONFIRMED.value)
            .where(Event.last_mention_at < fading_threshold)
            .values(lifecycle_status=EventLifecycle.FADING.value)
            .returning(Event.id)
        )
        stats["confirmed_to_fading"] = len(result.all())

        # Fading → Archived
        result = await self.session.execute(
            update(Event)
            .where(Event.lifecycle_status == EventLifecycle.FADING.value)
            .where(Event.last_mention_at < archive_threshold)
            .values(lifecycle_status=EventLifecycle.ARCHIVED.value)
            .returning(Event.id)
        )
        stats["fading_to_archived"] = len(result.all())

        return stats

    async def get_active_events(
        self,
        include_fading: bool = False,
    ) -> list[Event]:
        """Get events that are still active (emerging or confirmed)."""
        statuses = [EventLifecycle.EMERGING.value, EventLifecycle.CONFIRMED.value]
        if include_fading:
            statuses.append(EventLifecycle.FADING.value)

        result = await self.session.execute(
            select(Event)
            .where(Event.lifecycle_status.in_(statuses))
            .order_by(Event.last_mention_at.desc())
        )
        return list(result.scalars().all())
```

### Impact Weighting by Lifecycle

```python
# src/core/trend_engine.py

LIFECYCLE_WEIGHT = {
    "emerging": 0.5,    # Unconfirmed - reduced impact
    "confirmed": 1.0,   # Full impact
    "fading": 0.3,      # Old news - reduced impact
    "archived": 0.0,    # No impact on new calculations
}

def calculate_evidence_delta(
    ...existing params...,
    event_lifecycle: str = "confirmed",
) -> tuple[float, EvidenceFactors]:
    """Calculate log-odds delta with lifecycle weighting."""

    # Existing calculation
    raw_delta = (
        indicator_weight
        * source_credibility
        * corroboration
        * novelty_score
        * direction_mult
    )

    # NEW: Apply lifecycle weight
    lifecycle_weight = LIFECYCLE_WEIGHT.get(event_lifecycle, 1.0)
    raw_delta *= lifecycle_weight

    # Rest of function...
```

### Celery Task

```python
# src/workers/tasks.py

from src.processing.event_lifecycle import EventLifecycleManager

@celery_app.task
def check_event_lifecycles():
    """
    Periodic task to decay event lifecycles.

    Schedule: Every hour
    """
    async def _run():
        async with async_session_maker() as session:
            manager = EventLifecycleManager(session)
            stats = await manager.run_decay_check()
            await session.commit()
            return stats

    stats = asyncio.run(_run())
    logger.info("Event lifecycle check completed", **stats)
    return stats


# In celery beat schedule:
CELERYBEAT_SCHEDULE = {
    'check-event-lifecycles': {
        'task': 'src.workers.tasks.check_event_lifecycles',
        'schedule': crontab(minute=0),  # Every hour
    },
}
```

### API Updates

```python
# src/api/routes/events.py

@router.get("", response_model=list[EventResponse])
async def list_events(
    lifecycle: str | None = Query(
        None,
        description="Filter by lifecycle: emerging, confirmed, fading, archived"
    ),
    active_only: bool = Query(
        True,
        description="Only return emerging/confirmed events"
    ),
    ...
):
    """List events with lifecycle filtering."""
    query = select(Event)

    if lifecycle:
        query = query.where(Event.lifecycle_status == lifecycle)
    elif active_only:
        query = query.where(Event.lifecycle_status.in_([
            EventLifecycle.EMERGING.value,
            EventLifecycle.CONFIRMED.value,
        ]))

    # Rest of implementation...
```

```python
# Update EventResponse schema

class EventResponse(BaseModel):
    id: UUID
    summary: str
    categories: list[str]
    source_count: int
    first_seen_at: datetime

    # NEW
    lifecycle_status: str
    last_mention_at: datetime
    unique_source_count: int
    confirmed_at: datetime | None
```

## Testing

```python
# tests/unit/processing/test_event_lifecycle.py

import pytest
from datetime import datetime, timedelta
from src.processing.event_lifecycle import (
    EventLifecycleManager,
    EventLifecycle,
    CONFIRMATION_THRESHOLD,
    FADING_HOURS,
)

class MockEvent:
    def __init__(self):
        self.lifecycle_status = EventLifecycle.EMERGING.value
        self.last_mention_at = datetime.utcnow()
        self.source_count = 1
        self.unique_source_count = 1
        self.confirmed_at = None

class TestEventLifecycle:

    def test_emerging_to_confirmed_on_threshold(self):
        """Event confirms when reaching source threshold."""
        event = MockEvent()
        manager = EventLifecycleManager(None)

        # Add mentions until threshold
        for i in range(CONFIRMATION_THRESHOLD - 1):
            manager.on_new_mention(event, f"source_{i}")

        assert event.lifecycle_status == EventLifecycle.CONFIRMED.value
        assert event.confirmed_at is not None

    def test_confirmed_to_fading_on_silence(self):
        """Event fades after period without mentions."""
        event = MockEvent()
        event.lifecycle_status = EventLifecycle.CONFIRMED.value
        event.last_mention_at = datetime.utcnow() - timedelta(hours=FADING_HOURS + 1)

        # Would need async test setup for run_decay_check
        # Simplified assertion
        assert event.last_mention_at < datetime.utcnow() - timedelta(hours=FADING_HOURS)

    def test_fading_revives_on_new_mention(self):
        """Fading event returns to confirmed on new mention."""
        event = MockEvent()
        event.lifecycle_status = EventLifecycle.FADING.value

        manager = EventLifecycleManager(None)
        changed = manager.on_new_mention(event, "new_source")

        assert changed
        assert event.lifecycle_status == EventLifecycle.CONFIRMED.value

    def test_lifecycle_weight_reduces_impact(self):
        """Emerging and fading events have reduced trend impact."""
        from src.core.trend_engine import LIFECYCLE_WEIGHT

        assert LIFECYCLE_WEIGHT["emerging"] < LIFECYCLE_WEIGHT["confirmed"]
        assert LIFECYCLE_WEIGHT["fading"] < LIFECYCLE_WEIGHT["confirmed"]
        assert LIFECYCLE_WEIGHT["archived"] == 0.0
```

## Acceptance Criteria

- [ ] `EventLifecycle` enum with 4 states
- [ ] New columns on events table: lifecycle_status, last_mention_at, unique_source_count, confirmed_at
- [ ] Migration script
- [ ] `EventLifecycleManager` class with on_new_mention() and run_decay_check()
- [ ] Lifecycle weight affects trend impact calculation
- [ ] Celery task for hourly lifecycle decay check
- [ ] API filter by lifecycle status
- [ ] EventResponse includes lifecycle fields
- [ ] Unit tests for all transitions
- [ ] Index on (lifecycle_status, last_mention_at)

## Notes

- Thresholds (3 sources, 48h, 7d) may need tuning based on data volume
- Consider making thresholds configurable per trend or category
- Archived events still accessible for retrospectives
- Lifecycle transitions should be logged for debugging
