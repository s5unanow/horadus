# TASK-003: Database Schema & Migrations

## Overview

Create the initial database schema using Alembic migrations. This includes all core tables, indexes, and TimescaleDB hypertables.

## Context

The database schema is the foundation of the system. It needs to support:
- High-volume ingestion (raw_items)
- Event clustering (events, event_items)
- Trend probability tracking (trends, trend_evidence, trend_snapshots)
- Vector similarity search (pgvector embeddings)
- Time-series queries (TimescaleDB)

## Requirements

### Tables

See `docs/DATA_MODEL.md` for full schema. Summary:

| Table | Purpose |
|-------|---------|
| sources | Data source configurations |
| raw_items | Individual articles/posts |
| events | Clustered news events |
| event_items | Junction: events ↔ raw_items |
| trends | Trend definitions and current state |
| trend_evidence | Evidence trail for probability changes |
| trend_snapshots | Time-series of probability history |

### Alembic Setup

1. Initialize Alembic in project root
2. Configure async SQLAlchemy support
3. Create initial migration with all tables

## Implementation

### Step 1: Create SQLAlchemy Models

Create `src/storage/models.py`:

```python
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # rss, telegram, gdelt, api
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text)
    credibility_score: Mapped[float] = mapped_column(Numeric(3, 2), default=0.50)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    raw_items: Mapped[list["RawItem"]] = relationship(back_populates="source")


class RawItem(Base):
    __tablename__ = "raw_items"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sources.id"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text)
    title: Mapped[Optional[str]] = mapped_column(Text)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[Optional[str]] = mapped_column(String(10))
    processing_status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, processing, classified, noise, error
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    source: Mapped["Source"] = relationship(back_populates="raw_items")

    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_raw_items_source_external"),
        Index("idx_raw_items_status", "processing_status"),
        Index("idx_raw_items_hash", "content_hash"),
        Index("idx_raw_items_fetched", "fetched_at"),
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    canonical_summary: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1536))
    
    # LLM-extracted structured data
    extracted_who: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    extracted_what: Mapped[Optional[str]] = mapped_column(Text)
    extracted_where: Mapped[Optional[str]] = mapped_column(Text)
    extracted_when: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    extracted_claims: Mapped[Optional[dict]] = mapped_column(JSONB)
    categories: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    
    # Aggregated metadata
    source_count: Mapped[int] = mapped_column(Integer, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    primary_item_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("raw_items.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_events_first_seen", "first_seen_at"),
        Index("idx_events_categories", "categories", postgresql_using="gin"),
    )


class EventItem(Base):
    __tablename__ = "event_items"

    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("raw_items.id", ondelete="CASCADE"), primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Trend(Base):
    __tablename__ = "trends"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    
    # Probability tracking (log-odds)
    baseline_log_odds: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    current_log_odds: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    
    # Config
    indicators: Mapped[dict] = mapped_column(JSONB, nullable=False)
    decay_half_life_days: Mapped[int] = mapped_column(Integer, default=30)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TrendEvidence(Base):
    __tablename__ = "trend_evidence"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    trend_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("trends.id"), nullable=False
    )
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("events.id"), nullable=False
    )
    
    # Scoring factors
    signal_type: Mapped[str] = mapped_column(String(100), nullable=False)
    credibility_score: Mapped[Optional[float]] = mapped_column(Numeric(3, 2))
    corroboration_factor: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    novelty_score: Mapped[Optional[float]] = mapped_column(Numeric(3, 2))
    severity_score: Mapped[Optional[float]] = mapped_column(Numeric(3, 2))
    
    # Result
    delta_log_odds: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    reasoning: Mapped[Optional[str]] = mapped_column(Text)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("trend_id", "event_id", "signal_type", name="uq_trend_evidence"),
        Index("idx_trend_evidence_trend", "trend_id", "created_at"),
        Index("idx_trend_evidence_event", "event_id"),
    )


class TrendSnapshot(Base):
    __tablename__ = "trend_snapshots"

    trend_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("trends.id"), primary_key=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    log_odds: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    event_count_24h: Mapped[Optional[int]] = mapped_column(Integer)
```

### Step 2: Configure Alembic

Create `alembic.ini`:

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url = postgresql+asyncpg://postgres:postgres@localhost:5432/geoint

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

Create `alembic/env.py`:

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.storage.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### Step 3: Create Initial Migration

Create `alembic/versions/001_initial_schema.py`:

```python
"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2024-01-XX

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable extensions (should already be done in Docker init, but safe to repeat)
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.execute('CREATE EXTENSION IF NOT EXISTS timescaledb')

    # Create tables (SQLAlchemy will handle this, but showing explicit for clarity)
    # The actual table creation is handled by the autogenerated migration
    
    # After creating trend_snapshots, convert to hypertable
    op.execute("""
        SELECT create_hypertable('trend_snapshots', 'timestamp', 
                                  if_not_exists => TRUE,
                                  migrate_data => TRUE)
    """)
    
    # Create vector index (IVFFlat for approximate nearest neighbor)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_embedding 
        ON events USING ivfflat (embedding vector_cosine_ops) 
        WITH (lists = 100)
    """)


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table('trend_snapshots')
    op.drop_table('trend_evidence')
    op.drop_table('event_items')
    op.drop_table('events')
    op.drop_table('raw_items')
    op.drop_table('trends')
    op.drop_table('sources')
```

## Verification

```bash
# Ensure Docker is running
docker-compose up -d

# Run migrations
alembic upgrade head

# Verify tables exist
docker exec geoint-postgres psql -U postgres -d geoint -c "\dt"

# Should show:
#  sources
#  raw_items
#  events
#  event_items
#  trends
#  trend_evidence
#  trend_snapshots

# Verify hypertable
docker exec geoint-postgres psql -U postgres -d geoint -c \
  "SELECT hypertable_name FROM timescaledb_information.hypertables;"

# Verify vector extension
docker exec geoint-postgres psql -U postgres -d geoint -c \
  "SELECT * FROM pg_extension WHERE extname = 'vector';"

# Rollback test
alembic downgrade -1
alembic upgrade head
```

## Acceptance Checklist

- [ ] `src/storage/models.py` created with all models
- [ ] `alembic.ini` created
- [ ] `alembic/env.py` configured for async
- [ ] `alembic/versions/001_initial_schema.py` created
- [ ] `alembic upgrade head` succeeds
- [ ] All 7 tables exist in database
- [ ] `trend_snapshots` is a TimescaleDB hypertable
- [ ] Vector index exists on `events.embedding`
- [ ] `alembic downgrade -1` and `upgrade head` work
