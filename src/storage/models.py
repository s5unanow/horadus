"""
Database models for the Geopolitical Intelligence Platform.

This module defines all SQLAlchemy ORM models for the application.
Uses async SQLAlchemy 2.0 patterns.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# =============================================================================
# Base Configuration
# =============================================================================


class Base(DeclarativeBase):
    """Base class for all models."""

    type_annotation_map = {
        dict: JSONB,
        list[str]: ARRAY(String),
        UUID: PGUUID(as_uuid=True),
    }


# =============================================================================
# Enums
# =============================================================================


class SourceType(str, enum.Enum):
    """Types of data sources."""

    RSS = "rss"
    TELEGRAM = "telegram"
    GDELT = "gdelt"
    API = "api"
    SCRAPER = "scraper"


class SourceTier(str, enum.Enum):
    """Source credibility tiers (Expert Recommendation)."""

    PRIMARY = "primary"  # Official sources, direct access
    WIRE = "wire"  # AP, Reuters, AFP
    MAJOR = "major"  # BBC, Guardian, major papers
    REGIONAL = "regional"  # Specialty/regional outlets
    AGGREGATOR = "aggregator"  # News aggregators, blogs


class ReportingType(str, enum.Enum):
    """Type of reporting (Expert Recommendation)."""

    FIRSTHAND = "firsthand"  # Original reporting
    SECONDARY = "secondary"  # Citing other sources
    AGGREGATOR = "aggregator"  # Pure aggregation


class ProcessingStatus(str, enum.Enum):
    """Status of item in processing pipeline."""

    PENDING = "pending"
    PROCESSING = "processing"
    CLASSIFIED = "classified"
    NOISE = "noise"
    ERROR = "error"


class EventLifecycle(str, enum.Enum):
    """Lifecycle status of an event (Expert Recommendation)."""

    EMERGING = "emerging"  # Single source, unconfirmed
    CONFIRMED = "confirmed"  # Multiple independent sources
    FADING = "fading"  # No new mentions in 48h
    ARCHIVED = "archived"  # No mentions in 7d, historical only


class TrendDirection(str, enum.Enum):
    """Direction of trend movement."""

    RISING_FAST = "rising_fast"
    RISING = "rising"
    STABLE = "stable"
    FALLING = "falling"
    FALLING_FAST = "falling_fast"


class RiskLevel(str, enum.Enum):
    """Risk level categories (Expert Recommendation)."""

    LOW = "low"  # < 10%
    GUARDED = "guarded"  # 10-25%
    ELEVATED = "elevated"  # 25-50%
    HIGH = "high"  # 50-75%
    SEVERE = "severe"  # > 75%


class OutcomeType(str, enum.Enum):
    """Outcome types for calibration (Expert Recommendation)."""

    OCCURRED = "occurred"
    DID_NOT_OCCUR = "did_not_occur"
    PARTIAL = "partial"
    SUPERSEDED = "superseded"
    ONGOING = "ongoing"


# =============================================================================
# Source Models
# =============================================================================


class Source(Base):
    """
    A data source (RSS feed, Telegram channel, etc.).

    Attributes:
        id: Unique identifier
        type: Source type (rss, telegram, gdelt, api, scraper)
        name: Human-readable name
        url: Source URL (feed URL, channel URL, etc.)
        credibility_score: Reliability rating (0.0 to 1.0)
        source_tier: Tier classification (primary, wire, major, regional, aggregator)
        reporting_type: Type of reporting (firsthand, secondary, aggregator)
        config: Source-specific configuration (JSON)
        is_active: Whether source is being collected
        last_fetched_at: Last successful fetch time
        error_count: Consecutive error count
        last_error: Most recent error message
    """

    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type"),
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
    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
        Index("idx_sources_active", "is_active"),
        Index("idx_sources_type", "type"),
        Index("idx_sources_tier", "source_tier"),
    )


# =============================================================================
# Raw Item Models
# =============================================================================


class RawItem(Base):
    """
    A single collected item (article, post, message).

    This is the raw data before classification. Each item goes through
    the processing pipeline: pending -> processing -> classified/noise/error

    Attributes:
        id: Unique identifier
        source_id: Reference to source
        external_id: ID from source (URL for RSS, message_id for Telegram)
        url: Full URL to original content
        title: Article/post title
        published_at: Original publication time
        fetched_at: When we collected it
        raw_content: Extracted text content
        content_hash: SHA256 hash for deduplication
        language: Detected language code (e.g., 'en', 'ru')
        processing_status: Current pipeline status
        error_message: Error details if status is ERROR
    """

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
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256
    language: Mapped[str | None] = mapped_column(String(10))
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, name="processing_status"),
        default=ProcessingStatus.PENDING,
        nullable=False,
    )
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
        Index("idx_raw_items_hash", "content_hash"),
        Index("idx_raw_items_fetched", "fetched_at"),
        Index("idx_raw_items_source_fetched", "source_id", "fetched_at"),
    )


# =============================================================================
# Event Models
# =============================================================================


class Event(Base):
    """
    A clustered event (multiple articles about the same story).

    Events are the unit of analysis for trend impact. Multiple RawItems
    are clustered into Events based on embedding similarity.

    Attributes:
        id: Unique identifier
        canonical_summary: LLM-generated summary of the event
        embedding: Vector embedding for similarity search
        extracted_who: Entities involved (people, organizations)
        extracted_what: What happened
        extracted_where: Location
        extracted_when: When it happened
        extracted_claims: Structured claims from the event
        categories: Assigned category labels
        source_count: Number of sources reporting this
        lifecycle_status: Current lifecycle stage (emerging/confirmed/fading/archived)
        first_seen_at: When first article arrived
        last_mention_at: When last article was added
        last_updated_at: When last article was added
        primary_item_id: Most authoritative source item
        has_contradictions: Whether sources contradict each other
    """

    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    canonical_summary: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))  # OpenAI dim

    # LLM-extracted structured data
    extracted_who: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    extracted_what: Mapped[str | None] = mapped_column(Text)
    extracted_where: Mapped[str | None] = mapped_column(String(255))
    extracted_when: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extracted_claims: Mapped[dict | None] = mapped_column(JSONB)
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
    evidence_records: Mapped[list[TrendEvidence]] = relationship(back_populates="event")

    # Indexes
    __table_args__ = (
        Index("idx_events_first_seen", "first_seen_at"),
        Index("idx_events_categories", "categories", postgresql_using="gin"),
        Index("idx_events_lifecycle", "lifecycle_status", "last_mention_at"),
        # Vector index created separately with specific params
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


# =============================================================================
# Trend Models
# =============================================================================


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
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)

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
    indicators: Mapped[dict] = mapped_column(JSONB, nullable=False)
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

    # Indexes
    __table_args__ = (Index("idx_trends_active", "is_active"),)


class TrendEvidence(Base):
    """
    Record of evidence applied to a trend.

    Every time an event affects a trend's probability, we record:
    - What event caused it
    - What signal type was detected
    - All the scoring factors
    - The resulting log-odds delta
    - Human-readable reasoning

    This creates a full audit trail for probability changes.
    """

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

    # Signal classification
    signal_type: Mapped[str] = mapped_column(String(100), nullable=False)

    # Scoring factors
    credibility_score: Mapped[float | None] = mapped_column(Numeric(3, 2))
    corroboration_factor: Mapped[float | None] = mapped_column(Numeric(5, 2))
    novelty_score: Mapped[float | None] = mapped_column(Numeric(3, 2))
    severity_score: Mapped[float | None] = mapped_column(Numeric(3, 2))

    # Result
    delta_log_odds: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    trend: Mapped[Trend] = relationship(back_populates="evidence_records")
    event: Mapped[Event] = relationship(back_populates="evidence_records")

    # Constraints
    __table_args__ = (
        UniqueConstraint("trend_id", "event_id", "signal_type", name="uq_trend_event_signal"),
        Index("idx_evidence_trend_created", "trend_id", "created_at"),
        Index("idx_evidence_event", "event_id"),
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
    statistics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    narrative: Mapped[str | None] = mapped_column(Text)
    top_events: Mapped[dict | None] = mapped_column(JSONB)

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
    outcome_evidence: Mapped[dict | None] = mapped_column(JSONB)

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


class HumanFeedback(Base):
    """
    Human corrections and annotations (Expert Recommendation).

    Tracks manual overrides, pins, and noise markings
    for training/evaluation data.
    """

    __tablename__ = "human_feedback"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # What was annotated
    target_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # "event" | "trend_evidence" | "classification"
    target_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )

    # The feedback
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # "pin" | "mark_noise" | "override_delta" | "correct_category"
    original_value: Mapped[dict | None] = mapped_column(JSONB)
    corrected_value: Mapped[dict | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)

    # Metadata
    created_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_feedback_target", "target_type", "target_id"),
        Index("idx_feedback_action", "action"),
    )
