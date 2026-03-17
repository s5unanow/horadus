"""Database models for the Geopolitical Intelligence Platform."""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.storage.base import Base


class SourceType(enum.StrEnum):
    """Types of data sources."""

    RSS = "rss"
    TELEGRAM = "telegram"
    GDELT = "gdelt"
    API = "api"
    SCRAPER = "scraper"


class SourceTier(enum.StrEnum):
    """Source credibility tiers (Expert Recommendation)."""

    PRIMARY = "primary"  # Official sources, direct access
    WIRE = "wire"  # AP, Reuters, AFP
    MAJOR = "major"  # BBC, Guardian, major papers
    REGIONAL = "regional"  # Specialty/regional outlets
    AGGREGATOR = "aggregator"  # News aggregators, blogs


class ReportingType(enum.StrEnum):
    """Type of reporting (Expert Recommendation)."""

    FIRSTHAND = "firsthand"  # Original reporting
    SECONDARY = "secondary"  # Citing other sources
    AGGREGATOR = "aggregator"  # Pure aggregation


class ProcessingStatus(enum.StrEnum):
    """Status of item in processing pipeline."""

    PENDING = "pending"
    PROCESSING = "processing"
    CLASSIFIED = "classified"
    NOISE = "noise"
    ERROR = "error"


class EventLifecycle(enum.StrEnum):
    """Lifecycle status of an event (Expert Recommendation)."""

    EMERGING = "emerging"  # Single source, unconfirmed
    CONFIRMED = "confirmed"  # Multiple independent sources
    FADING = "fading"  # No new mentions in 48h
    ARCHIVED = "archived"  # No mentions in 7d, historical only


class EventClaimType(enum.StrEnum):
    """Stable claim identities tracked under a mutable event cluster."""

    FALLBACK = "fallback"
    STATEMENT = "statement"


class TrendDirection(enum.StrEnum):
    """Direction of trend movement."""

    RISING_FAST = "rising_fast"
    RISING = "rising"
    STABLE = "stable"
    FALLING = "falling"
    FALLING_FAST = "falling_fast"


class RiskLevel(enum.StrEnum):
    """Risk level categories (Expert Recommendation)."""

    LOW = "low"  # < 10%
    GUARDED = "guarded"  # 10-25%
    ELEVATED = "elevated"  # 25-50%
    HIGH = "high"  # 50-75%
    SEVERE = "severe"  # > 75%


class OutcomeType(enum.StrEnum):
    """Outcome types for calibration (Expert Recommendation)."""

    OCCURRED = "occurred"
    DID_NOT_OCCUR = "did_not_occur"
    PARTIAL = "partial"
    SUPERSEDED = "superseded"
    ONGOING = "ongoing"


class TaxonomyGapReason(enum.StrEnum):
    """Reason a trend impact was ignored due to taxonomy mismatch."""

    UNKNOWN_TREND_ID = "unknown_trend_id"
    UNKNOWN_SIGNAL_TYPE = "unknown_signal_type"


class TaxonomyGapStatus(enum.StrEnum):
    """Analyst triage lifecycle for recorded taxonomy gaps."""

    OPEN = "open"
    RESOLVED = "resolved"
    REJECTED = "rejected"


def enum_values(enum_class: type[enum.Enum]) -> list[str]:
    """Persist enum values (not member names) in PostgreSQL enums."""
    return [str(member.value) for member in enum_class]


def sql_string_literals(values: tuple[str, ...]) -> str:
    """Render a tuple of string values as SQL literals for CHECK constraints."""
    return ", ".join(f"'{value}'" for value in values)


SOURCE_TIER_VALUES = tuple(enum_values(SourceTier))
REPORTING_TYPE_VALUES = tuple(enum_values(ReportingType))
EVENT_LIFECYCLE_VALUES = tuple(enum_values(EventLifecycle))
EVENT_CLAIM_TYPE_VALUES = tuple(enum_values(EventClaimType))

SOURCE_TIER_SQL_VALUES = sql_string_literals(SOURCE_TIER_VALUES)
REPORTING_TYPE_SQL_VALUES = sql_string_literals(REPORTING_TYPE_VALUES)
EVENT_LIFECYCLE_SQL_VALUES = sql_string_literals(EVENT_LIFECYCLE_VALUES)
EVENT_CLAIM_TYPE_SQL_VALUES = sql_string_literals(EVENT_CLAIM_TYPE_VALUES)


class Source(Base):
    """A data source (RSS feed, Telegram channel, etc.)."""

    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type", values_callable=enum_values),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    credibility_score: Mapped[float] = mapped_column(
        Numeric(3, 2),
        default=0.50,
        nullable=False,
    )
    # NEW: Source tier (Expert Recommendation)
    source_tier: Mapped[str] = mapped_column(
        String(20),
        default=SourceTier.REGIONAL.value,
        nullable=False,
    )
    # NEW: Reporting type (Expert Recommendation)
    reporting_type: Mapped[str] = mapped_column(
        String(20),
        default=ReportingType.SECONDARY.value,
        nullable=False,
    )
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingestion_window_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    items: Mapped[list[RawItem]] = relationship(back_populates="source")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "credibility_score >= 0 AND credibility_score <= 1",
            name="check_credibility_range",
        ),
        CheckConstraint(
            f"source_tier IN ({SOURCE_TIER_SQL_VALUES})",
            name="check_sources_source_tier_allowed",
        ),
        CheckConstraint(
            f"reporting_type IN ({REPORTING_TYPE_SQL_VALUES})",
            name="check_sources_reporting_type_allowed",
        ),
        Index("idx_sources_active", "is_active"),
        Index("idx_sources_type", "type"),
        Index("idx_sources_tier", "source_tier"),
        Index("idx_sources_ingestion_window_end_at", "ingestion_window_end_at"),
    )


class RawItem(Base):
    """A single collected item before classification."""

    __tablename__ = "raw_items"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(2048), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))  # OpenAI dim
    embedding_model: Mapped[str | None] = mapped_column(String(255))
    embedding_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    embedding_input_tokens: Mapped[int | None] = mapped_column(Integer)
    embedding_retained_tokens: Mapped[int | None] = mapped_column(Integer)
    embedding_was_truncated: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    embedding_truncation_strategy: Mapped[str | None] = mapped_column(String(20))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256
    language: Mapped[str | None] = mapped_column(String(10))
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, name="processing_status", values_callable=enum_values),
        default=ProcessingStatus.PENDING,
        nullable=False,
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    source: Mapped[Source] = relationship(back_populates="items")
    event_links: Mapped[list[EventItem]] = relationship(back_populates="item")

    # Constraints
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_source_external"),
        Index("idx_raw_items_status", "processing_status"),
        Index("idx_raw_items_processing_started_at", "processing_started_at"),
        Index("idx_raw_items_hash", "content_hash"),
        Index("idx_raw_items_fetched", "fetched_at"),
        Index("idx_raw_items_source_fetched", "source_id", "fetched_at"),
        # Keep model metadata aligned with migration-managed pgvector index.
        Index(
            "idx_raw_items_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"lists": 64},
        ),
    )


class Event(Base):
    """A mutable story cluster built from one or more raw items."""

    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    canonical_summary: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))  # OpenAI dim
    embedding_model: Mapped[str | None] = mapped_column(String(255))
    embedding_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    embedding_input_tokens: Mapped[int | None] = mapped_column(Integer)
    embedding_retained_tokens: Mapped[int | None] = mapped_column(Integer)
    embedding_was_truncated: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    embedding_truncation_strategy: Mapped[str | None] = mapped_column(String(20))

    # LLM-extracted structured data
    extracted_who: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    extracted_what: Mapped[str | None] = mapped_column(Text)
    extracted_where: Mapped[str | None] = mapped_column(String(255))
    extracted_when: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extracted_claims: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    categories: Mapped[list[str] | None] = mapped_column(ARRAY(String))

    # Aggregated metadata
    source_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unique_source_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # NEW: Lifecycle tracking (Expert Recommendation)
    lifecycle_status: Mapped[str] = mapped_column(
        String(20),
        default=EventLifecycle.EMERGING.value,
        nullable=False,
    )

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # NEW: Track when event was last mentioned (Expert Recommendation)
    last_mention_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    # NEW: When event was confirmed (Expert Recommendation)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    primary_item_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("raw_items.id", ondelete="SET NULL"),
    )

    # NEW: Contradiction tracking (Expert Recommendation)
    has_contradictions: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    contradiction_notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    item_links: Mapped[list[EventItem]] = relationship(back_populates="event")
    claims: Mapped[list[EventClaim]] = relationship(back_populates="event")
    evidence_records: Mapped[list[TrendEvidence]] = relationship(
        back_populates="event",
        foreign_keys="TrendEvidence.event_id",
    )
    taxonomy_gaps: Mapped[list[TaxonomyGap]] = relationship(back_populates="event")

    # Indexes
    __table_args__ = (
        CheckConstraint(
            f"lifecycle_status IN ({EVENT_LIFECYCLE_SQL_VALUES})",
            name="check_events_lifecycle_status_allowed",
        ),
        Index("idx_events_first_seen", "first_seen_at"),
        Index("idx_events_categories", "categories", postgresql_using="gin"),
        Index("idx_events_lifecycle", "lifecycle_status", "last_mention_at"),
        # Keep model metadata aligned with migration-managed pgvector index.
        Index(
            "idx_events_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"lists": 64},
        ),
    )


class EventItem(Base):
    """
    Junction table linking Events to RawItems.

    An Event can have multiple RawItems (articles about same story).
    A RawItem belongs to exactly one Event once classified.
    """

    __tablename__ = "event_items"

    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        primary_key=True,
    )
    item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("raw_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    event: Mapped[Event] = relationship(back_populates="item_links")
    item: Mapped[RawItem] = relationship(back_populates="event_links")

    __table_args__ = (UniqueConstraint("item_id", name="uq_event_items_item_id"),)


class EventClaim(Base):
    """Stable claim identity recorded beneath a mutable event cluster."""

    __tablename__ = "event_claims"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
    )
    claim_key: Mapped[str] = mapped_column(String(255), nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(
        String(20),
        default=EventClaimType.STATEMENT.value,
        server_default=text(f"'{EventClaimType.STATEMENT.value}'"),
        nullable=False,
    )
    claim_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    event: Mapped[Event] = relationship(back_populates="claims")
    evidence_records: Mapped[list[TrendEvidence]] = relationship(
        back_populates="event_claim",
        foreign_keys="TrendEvidence.event_claim_id",
    )

    __table_args__ = (
        CheckConstraint(
            f"claim_type IN ({EVENT_CLAIM_TYPE_SQL_VALUES})",
            name="check_event_claims_claim_type_allowed",
        ),
        UniqueConstraint("event_id", "claim_key", name="uq_event_claims_event_claim_key"),
        UniqueConstraint("event_id", "id", name="uq_event_claims_event_id_id"),
        Index("idx_event_claims_event_active", "event_id", "is_active"),
    )


class Trend(Base):
    """
    A geopolitical trend being tracked.

    Trends represent hypotheses with associated probabilities.
    Examples: "EU-Russia Military Conflict", "US-China Trade War"
    Probability is stored as log-odds internally for mathematical correctness.
    Use the trend_engine functions to convert to/from probability.

    Attributes:
        id: Unique identifier
        name: Human-readable trend name
        description: Detailed description
        definition: Full configuration (JSON)
        baseline_log_odds: Starting point (as log-odds)
        current_log_odds: Current value (as log-odds)
        indicators: Signal types and weights (JSON)
        decay_half_life_days: How fast old evidence fades
        is_active: Whether trend is being tracked
    """

    __tablename__ = "trends"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    runtime_trend_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Probability as log-odds
    baseline_log_odds: Mapped[float] = mapped_column(
        Numeric(10, 6),
        nullable=False,
    )
    current_log_odds: Mapped[float] = mapped_column(
        Numeric(10, 6),
        nullable=False,
    )

    # Configuration
    indicators: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    decay_half_life_days: Mapped[int] = mapped_column(
        Integer,
        default=30,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    evidence_records: Mapped[list[TrendEvidence]] = relationship(back_populates="trend")
    snapshots: Mapped[list[TrendSnapshot]] = relationship(back_populates="trend")
    outcomes: Mapped[list[TrendOutcome]] = relationship(back_populates="trend")
    definition_versions: Mapped[list[TrendDefinitionVersion]] = relationship(back_populates="trend")

    # Indexes
    __table_args__ = (Index("idx_trends_active", "is_active"),)


class TrendDefinitionVersion(Base):
    """
    Append-only record of trend definition payload changes.

    Captures trend-definition state at write time so operators can audit
    historical definition changes independently from Git history.
    """

    __tablename__ = "trend_definition_versions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    trend_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("trends.id", ondelete="CASCADE"),
        nullable=False,
    )
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    actor: Mapped[str | None] = mapped_column(String(255))
    context: Mapped[str | None] = mapped_column(String(255))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    trend: Mapped[Trend] = relationship(back_populates="definition_versions")

    __table_args__ = (
        Index("idx_trend_definition_versions_trend_recorded", "trend_id", "recorded_at"),
        Index("idx_trend_definition_versions_hash", "definition_hash"),
    )


class TrendEvidence(Base):
    """Record one scored event signal and the resulting trend delta."""

    __tablename__ = "trend_evidence"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    trend_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("trends.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_claim_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("event_claims.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Signal classification
    signal_type: Mapped[str] = mapped_column(String(100), nullable=False)
    base_weight: Mapped[float | None] = mapped_column(Numeric(10, 6))
    direction_multiplier: Mapped[float | None] = mapped_column(Numeric(3, 1))
    trend_definition_hash: Mapped[str | None] = mapped_column(String(64))

    # Scoring factors
    credibility_score: Mapped[float | None] = mapped_column(Numeric(3, 2))
    corroboration_factor: Mapped[float | None] = mapped_column(Numeric(5, 2))
    novelty_score: Mapped[float | None] = mapped_column(Numeric(3, 2))
    evidence_age_days: Mapped[float | None] = mapped_column(Numeric(6, 2))
    temporal_decay_factor: Mapped[float | None] = mapped_column(Numeric(5, 4))
    severity_score: Mapped[float | None] = mapped_column(Numeric(3, 2))
    confidence_score: Mapped[float | None] = mapped_column(Numeric(3, 2))

    # Result
    delta_log_odds: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    is_invalidated: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_feedback_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("human_feedback.id", ondelete="SET NULL"),
    )

    # Relationships
    trend: Mapped[Trend] = relationship(back_populates="evidence_records")
    event: Mapped[Event] = relationship(
        back_populates="evidence_records",
        foreign_keys=[event_id],
    )
    event_claim: Mapped[EventClaim] = relationship(
        back_populates="evidence_records",
        foreign_keys=[event_claim_id],
    )

    # Constraints
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "event_claim_id"],
            ["event_claims.event_id", "event_claims.id"],
            ondelete="CASCADE",
            name="fk_trend_evidence_event_id_event_claim_id_event_claims",
        ),
        Index("idx_evidence_trend_created", "trend_id", "created_at"),
        Index("idx_evidence_event", "event_id"),
        Index("idx_evidence_event_claim", "event_claim_id"),
        Index("idx_evidence_event_invalidated", "event_id", "is_invalidated"),
        Index(
            "uq_trend_event_claim_signal_active",
            "trend_id",
            "event_claim_id",
            "signal_type",
            unique=True,
            postgresql_where=text("is_invalidated = false"),
        ),
    )


class TaxonomyGap(Base):
    """
    Runtime taxonomy mismatch record for analyst triage.

    Rows are created when Tier-2 impacts are skipped because:
    - trend_id is unknown to active trend taxonomy, or
    - signal_type is not configured for a known trend.
    """

    __tablename__ = "taxonomy_gaps"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("events.id", ondelete="SET NULL"),
    )
    trend_id: Mapped[str] = mapped_column(String(255), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[TaxonomyGapReason] = mapped_column(
        Enum(TaxonomyGapReason, name="taxonomy_gap_reason", values_callable=enum_values),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(50),
        default="pipeline",
        server_default=text("'pipeline'"),
        nullable=False,
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    status: Mapped[TaxonomyGapStatus] = mapped_column(
        Enum(TaxonomyGapStatus, name="taxonomy_gap_status", values_callable=enum_values),
        default=TaxonomyGapStatus.OPEN,
        server_default=text("'open'"),
        nullable=False,
    )
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(String(255))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    event: Mapped[Event | None] = relationship(back_populates="taxonomy_gaps")

    __table_args__ = (
        Index("idx_taxonomy_gaps_observed_at", "observed_at"),
        Index("idx_taxonomy_gaps_status_observed", "status", "observed_at"),
        Index("idx_taxonomy_gaps_reason", "reason"),
        Index("idx_taxonomy_gaps_trend_signal", "trend_id", "signal_type"),
    )


LLM_REPLAY_STATUS_VALUES = ("pending", "processing", "done", "error")
LLM_REPLAY_STATUS_SQL_VALUES = sql_string_literals(LLM_REPLAY_STATUS_VALUES)


class LLMReplayQueueItem(Base):
    """
    Bounded replay queue for post-recovery Tier-2 reprocessing.

    Used by degraded-mode policy to defer high-impact trend evidence application until
    a primary-quality Tier-2 model is available again.
    """

    __tablename__ = "llm_replay_queue"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default=text("'pending'"),
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(255))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    enqueued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    event: Mapped[Event] = relationship()

    __table_args__ = (
        CheckConstraint(
            f"status IN ({LLM_REPLAY_STATUS_SQL_VALUES})",
            name="check_llm_replay_queue_status_allowed",
        ),
        UniqueConstraint("stage", "event_id", name="uq_llm_replay_stage_event"),
        Index("idx_llm_replay_status_enqueued", "status", "enqueued_at"),
        Index("idx_llm_replay_event", "event_id"),
    )


class TrendSnapshot(Base):
    """
    Point-in-time snapshot of trend probability.

    Used for time-series queries and historical analysis.
    This table should be a TimescaleDB hypertable for efficient
    time-range queries.
    """

    __tablename__ = "trend_snapshots"

    trend_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("trends.id", ondelete="CASCADE"),
        primary_key=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )
    log_odds: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    event_count_24h: Mapped[int | None] = mapped_column(Integer)

    # Relationships
    trend: Mapped[Trend] = relationship(back_populates="snapshots")

    # Note: After table creation, run:
    # SELECT create_hypertable('trend_snapshots', 'timestamp');


# =============================================================================
# Report Models
# =============================================================================


class Report(Base):
    """
    Generated intelligence report.

    Reports are generated periodically (weekly/monthly) and contain:
    - Computed statistics about trends
    - LLM-generated narrative
    - Top contributing events
    """

    __tablename__ = "reports"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    report_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # 'weekly', 'monthly', 'retrospective'
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # For trend-specific reports
    trend_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("trends.id", ondelete="SET NULL"),
    )

    # Report content
    statistics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    narrative: Mapped[str | None] = mapped_column(Text)
    grounding_status: Mapped[str] = mapped_column(String(20), default="not_checked", nullable=False)
    grounding_violation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    grounding_references: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    top_events: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Indexes
    __table_args__ = (
        Index("idx_reports_type_period", "report_type", "period_end"),
        Index("idx_reports_trend", "trend_id"),
    )


# =============================================================================
# Cost Protection Models
# =============================================================================


class ApiUsage(Base):
    """
    Daily API usage counters for budget enforcement.

    Tracks per-tier call counts, tokens, and estimated spend.
    """

    __tablename__ = "api_usage"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    usage_date: Mapped[date] = mapped_column(
        "date",
        Date,
        nullable=False,
    )
    tier: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    call_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    input_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    estimated_cost_usd: Mapped[float] = mapped_column(
        Numeric(10, 4),
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("date", "tier", name="uq_api_usage_date_tier"),
        Index("idx_api_usage_date", "date"),
    )


# =============================================================================
# Calibration Models (Expert Recommendation)
# =============================================================================


class TrendOutcome(Base):
    """
    Record of how a trend prediction resolved.

    Used for calibration analysis: when we predicted X%,
    did it happen X% of the time?
    """

    __tablename__ = "trend_outcomes"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    trend_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("trends.id", ondelete="CASCADE"),
        nullable=False,
    )

    # What we predicted
    prediction_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    predicted_probability: Mapped[float] = mapped_column(
        Numeric(5, 4),
        nullable=False,
    )
    predicted_risk_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    probability_band_low: Mapped[float] = mapped_column(
        Numeric(5, 4),
        nullable=False,
    )
    probability_band_high: Mapped[float] = mapped_column(
        Numeric(5, 4),
        nullable=False,
    )

    # What happened
    outcome_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(20))  # OutcomeType
    outcome_notes: Mapped[str | None] = mapped_column(Text)
    outcome_evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Scoring
    brier_score: Mapped[float | None] = mapped_column(Numeric(10, 6))

    # Metadata
    recorded_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    trend: Mapped[Trend] = relationship(back_populates="outcomes")

    __table_args__ = (
        Index("idx_outcomes_trend_date", "trend_id", "prediction_date"),
        Index("idx_outcomes_outcome", "outcome"),
    )


from src.storage.restatement_models import HumanFeedback, TrendRestatement  # noqa: E402,F401
