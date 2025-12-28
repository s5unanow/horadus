# TASK-032: Trend Outcomes for Calibration

## Overview

Track how trends actually resolved to measure prediction accuracy over time.

Expert feedback: *"If you don't measure, it'll slowly become vibes."*

## Context

Without calibration:
- No way to know if "20% probability" actually happens ~20% of the time
- Can't identify systematic over/under-confidence
- Can't improve weighting parameters empirically

With calibration:
- Track predicted probability at outcome time
- Compare to what actually happened
- Calculate Brier scores and calibration curves
- Identify which trend types we predict well/poorly

## Requirements

### Outcome Types

```python
class OutcomeType(str, Enum):
    OCCURRED = "occurred"           # Event/scenario happened
    DID_NOT_OCCUR = "did_not_occur" # Explicitly did not happen
    PARTIAL = "partial"             # Partially occurred
    SUPERSEDED = "superseded"       # Question became irrelevant
    ONGOING = "ongoing"             # Still developing, no resolution
```

### Database Schema

```python
# src/storage/models.py

class TrendOutcome(Base):
    """
    Record of how a trend prediction resolved.
    
    Used for calibration analysis: when we predicted X%, 
    did it happen X% of the time?
    """
    
    __tablename__ = "trend_outcomes"
    
    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    trend_id: Mapped[UUID] = mapped_column(
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
    outcome_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    outcome: Mapped[str | None] = mapped_column(
        String(20),
    )  # OutcomeType enum value
    outcome_notes: Mapped[str | None] = mapped_column(Text)
    outcome_evidence: Mapped[dict | None] = mapped_column(JSONB)
    
    # Scoring
    brier_score: Mapped[float | None] = mapped_column(
        Numeric(10, 6),
    )  # (prediction - outcome)²
    
    # Metadata
    recorded_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    
    # Relationships
    trend: Mapped["Trend"] = relationship(back_populates="outcomes")
    
    __table_args__ = (
        Index("idx_outcomes_trend_date", "trend_id", "prediction_date"),
        Index("idx_outcomes_outcome", "outcome"),
    )


# Add relationship to Trend model
class Trend(Base):
    # ... existing fields ...
    outcomes: Mapped[list["TrendOutcome"]] = relationship(back_populates="trend")
```

### Brier Score Calculation

The Brier score measures prediction accuracy: lower is better.

```python
def calculate_brier_score(
    predicted_probability: float,
    outcome: OutcomeType,
) -> float:
    """
    Calculate Brier score for a prediction.
    
    Brier = (prediction - actual)²
    
    Where actual = 1 if occurred, 0 if not.
    
    Perfect prediction: 0.0
    Worst prediction: 1.0
    Random (0.5): 0.25
    """
    if outcome == OutcomeType.OCCURRED:
        actual = 1.0
    elif outcome == OutcomeType.DID_NOT_OCCUR:
        actual = 0.0
    elif outcome == OutcomeType.PARTIAL:
        actual = 0.5  # Debatable - could parameterize
    else:
        return None  # Can't score superseded/ongoing
    
    return (predicted_probability - actual) ** 2
```

## Implementation

### Outcome Service

```python
# src/core/calibration.py

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.storage.models import Trend, TrendOutcome, TrendSnapshot
from src.core.trend_engine import TrendEngine


@dataclass
class CalibrationBucket:
    """Calibration stats for a probability range."""
    bucket_start: float
    bucket_end: float
    prediction_count: int
    occurred_count: int
    actual_rate: float  # occurred_count / prediction_count
    expected_rate: float  # midpoint of bucket
    calibration_error: float  # |actual - expected|


@dataclass
class CalibrationReport:
    """Overall calibration statistics."""
    total_predictions: int
    resolved_predictions: int
    mean_brier_score: float
    buckets: list[CalibrationBucket]
    overconfident: bool  # True if we predict too high
    underconfident: bool  # True if we predict too low


class CalibrationService:
    """Service for recording outcomes and analyzing calibration."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.engine = TrendEngine(session)
    
    async def record_outcome(
        self,
        trend_id: UUID,
        outcome: OutcomeType,
        outcome_date: datetime,
        notes: str | None = None,
        evidence: dict | None = None,
        recorded_by: str | None = None,
    ) -> TrendOutcome:
        """
        Record the outcome of a trend prediction.
        
        Captures what we predicted at outcome_date and scores it.
        """
        # Get the prediction closest to outcome date
        trend = await self.session.get(Trend, trend_id)
        if not trend:
            raise ValueError(f"Trend {trend_id} not found")
        
        # Get probability at prediction time (from snapshots)
        snapshot = await self._get_snapshot_at(trend_id, outcome_date)
        
        if snapshot:
            predicted_prob = 1 / (1 + math.exp(-float(snapshot.log_odds)))
        else:
            # Fall back to current if no snapshot
            predicted_prob = self.engine.get_probability(trend)
        
        # Calculate band (simplified - could retrieve from stored data)
        band_low = max(0.001, predicted_prob - 0.10)
        band_high = min(0.999, predicted_prob + 0.10)
        
        # Get risk level
        risk_level = get_risk_level(predicted_prob).value
        
        # Calculate Brier score
        brier = calculate_brier_score(predicted_prob, outcome)
        
        # Create outcome record
        record = TrendOutcome(
            trend_id=trend_id,
            prediction_date=outcome_date,
            predicted_probability=predicted_prob,
            predicted_risk_level=risk_level,
            probability_band_low=band_low,
            probability_band_high=band_high,
            outcome_date=outcome_date,
            outcome=outcome.value,
            outcome_notes=notes,
            outcome_evidence=evidence,
            brier_score=brier,
            recorded_by=recorded_by,
        )
        
        self.session.add(record)
        await self.session.flush()
        
        return record
    
    async def get_calibration_report(
        self,
        trend_id: UUID | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> CalibrationReport:
        """
        Generate calibration analysis.
        
        Groups predictions into probability buckets and compares
        predicted rates to actual occurrence rates.
        """
        # Build query
        query = select(TrendOutcome).where(
            TrendOutcome.outcome.in_([
                OutcomeType.OCCURRED.value,
                OutcomeType.DID_NOT_OCCUR.value,
            ])
        )
        
        if trend_id:
            query = query.where(TrendOutcome.trend_id == trend_id)
        if start_date:
            query = query.where(TrendOutcome.prediction_date >= start_date)
        if end_date:
            query = query.where(TrendOutcome.prediction_date <= end_date)
        
        result = await self.session.execute(query)
        outcomes = list(result.scalars().all())
        
        if not outcomes:
            return CalibrationReport(
                total_predictions=0,
                resolved_predictions=0,
                mean_brier_score=0,
                buckets=[],
                overconfident=False,
                underconfident=False,
            )
        
        # Calculate buckets (0-10%, 10-20%, ..., 90-100%)
        buckets = []
        for i in range(10):
            bucket_start = i / 10
            bucket_end = (i + 1) / 10
            
            in_bucket = [
                o for o in outcomes
                if bucket_start <= float(o.predicted_probability) < bucket_end
            ]
            
            if in_bucket:
                occurred = sum(
                    1 for o in in_bucket 
                    if o.outcome == OutcomeType.OCCURRED.value
                )
                buckets.append(CalibrationBucket(
                    bucket_start=bucket_start,
                    bucket_end=bucket_end,
                    prediction_count=len(in_bucket),
                    occurred_count=occurred,
                    actual_rate=occurred / len(in_bucket),
                    expected_rate=(bucket_start + bucket_end) / 2,
                    calibration_error=abs(
                        occurred / len(in_bucket) - (bucket_start + bucket_end) / 2
                    ),
                ))
        
        # Overall stats
        brier_scores = [float(o.brier_score) for o in outcomes if o.brier_score]
        mean_brier = sum(brier_scores) / len(brier_scores) if brier_scores else 0
        
        # Determine over/under confidence
        high_pred = [o for o in outcomes if float(o.predicted_probability) > 0.5]
        if high_pred:
            high_occurred = sum(1 for o in high_pred if o.outcome == OutcomeType.OCCURRED.value)
            overconfident = high_occurred / len(high_pred) < 0.5
        else:
            overconfident = False
        
        low_pred = [o for o in outcomes if float(o.predicted_probability) < 0.5]
        if low_pred:
            low_occurred = sum(1 for o in low_pred if o.outcome == OutcomeType.OCCURRED.value)
            underconfident = low_occurred / len(low_pred) > 0.5
        else:
            underconfident = False
        
        return CalibrationReport(
            total_predictions=len(outcomes),
            resolved_predictions=len(outcomes),
            mean_brier_score=mean_brier,
            buckets=buckets,
            overconfident=overconfident,
            underconfident=underconfident,
        )
    
    async def _get_snapshot_at(
        self,
        trend_id: UUID,
        at: datetime,
    ) -> TrendSnapshot | None:
        """Get the snapshot closest to a given time."""
        result = await self.session.execute(
            select(TrendSnapshot)
            .where(TrendSnapshot.trend_id == trend_id)
            .where(TrendSnapshot.timestamp <= at)
            .order_by(TrendSnapshot.timestamp.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
```

### API Endpoints

```python
# src/api/routes/trends.py

@router.post("/{trend_id}/outcomes", response_model=OutcomeResponse)
async def record_trend_outcome(
    trend_id: UUID,
    outcome: OutcomeType,
    outcome_date: datetime,
    notes: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> OutcomeResponse:
    """
    Record the resolution of a trend prediction.
    
    Use this when a trend's prediction can be evaluated
    (e.g., an event occurred or definitely didn't happen).
    """
    service = CalibrationService(session)
    record = await service.record_outcome(
        trend_id=trend_id,
        outcome=outcome,
        outcome_date=outcome_date,
        notes=notes,
    )
    return OutcomeResponse.from_orm(record)


@router.get("/{trend_id}/calibration", response_model=CalibrationReportResponse)
async def get_trend_calibration(
    trend_id: UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    session: AsyncSession = Depends(get_session),
) -> CalibrationReportResponse:
    """
    Get calibration analysis for a trend.
    
    Shows how well our predictions matched reality.
    """
    service = CalibrationService(session)
    report = await service.get_calibration_report(
        trend_id=trend_id,
        start_date=start_date,
        end_date=end_date,
    )
    return CalibrationReportResponse(
        total_predictions=report.total_predictions,
        resolved_predictions=report.resolved_predictions,
        mean_brier_score=report.mean_brier_score,
        buckets=[
            BucketResponse(
                range=f"{int(b.bucket_start*100)}-{int(b.bucket_end*100)}%",
                predictions=b.prediction_count,
                occurred=b.occurred_count,
                actual_rate=b.actual_rate,
                expected_rate=b.expected_rate,
                calibration_error=b.calibration_error,
            )
            for b in report.buckets
        ],
        overconfident=report.overconfident,
        underconfident=report.underconfident,
    )


@router.get("/calibration/overall", response_model=CalibrationReportResponse)
async def get_overall_calibration(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    session: AsyncSession = Depends(get_session),
) -> CalibrationReportResponse:
    """
    Get calibration analysis across all trends.
    """
    service = CalibrationService(session)
    report = await service.get_calibration_report(
        start_date=start_date,
        end_date=end_date,
    )
    return CalibrationReportResponse(...)
```

### Response Schemas

```python
# src/api/schemas/calibration.py

class OutcomeResponse(BaseModel):
    id: UUID
    trend_id: UUID
    prediction_date: datetime
    predicted_probability: float
    predicted_risk_level: str
    outcome: str
    outcome_date: datetime
    brier_score: float | None
    
    class Config:
        from_attributes = True


class BucketResponse(BaseModel):
    range: str  # "20-30%"
    predictions: int
    occurred: int
    actual_rate: float
    expected_rate: float
    calibration_error: float


class CalibrationReportResponse(BaseModel):
    total_predictions: int
    resolved_predictions: int
    mean_brier_score: float
    buckets: list[BucketResponse]
    overconfident: bool
    underconfident: bool
    
    # Interpretation helper
    @property
    def assessment(self) -> str:
        if self.mean_brier_score < 0.1:
            return "Excellent calibration"
        elif self.mean_brier_score < 0.2:
            return "Good calibration"
        elif self.mean_brier_score < 0.3:
            return "Moderate calibration - room for improvement"
        else:
            return "Poor calibration - significant improvement needed"
```

## Usage Example

```python
# Record an outcome
POST /api/v1/trends/{trend_id}/outcomes
{
    "outcome": "occurred",
    "outcome_date": "2024-06-15T00:00:00Z",
    "notes": "Minor border incident confirmed by multiple sources"
}

# Get calibration report
GET /api/v1/trends/{trend_id}/calibration

# Response:
{
    "total_predictions": 45,
    "resolved_predictions": 45,
    "mean_brier_score": 0.18,
    "buckets": [
        {"range": "0-10%", "predictions": 12, "occurred": 1, "actual_rate": 0.08, ...},
        {"range": "10-20%", "predictions": 15, "occurred": 2, "actual_rate": 0.13, ...},
        ...
    ],
    "overconfident": false,
    "underconfident": false,
    "assessment": "Good calibration"
}
```

## Testing

```python
class TestBrierScore:
    def test_perfect_prediction_occurred(self):
        """Predicting 1.0 for occurred event = 0 Brier."""
        score = calculate_brier_score(1.0, OutcomeType.OCCURRED)
        assert score == 0.0
    
    def test_perfect_prediction_not_occurred(self):
        """Predicting 0.0 for non-occurred event = 0 Brier."""
        score = calculate_brier_score(0.0, OutcomeType.DID_NOT_OCCUR)
        assert score == 0.0
    
    def test_worst_prediction_occurred(self):
        """Predicting 0.0 for occurred event = 1.0 Brier."""
        score = calculate_brier_score(0.0, OutcomeType.OCCURRED)
        assert score == 1.0
    
    def test_fifty_fifty(self):
        """Predicting 0.5 for any outcome = 0.25 Brier."""
        score = calculate_brier_score(0.5, OutcomeType.OCCURRED)
        assert score == 0.25
```

## Acceptance Criteria

- [ ] TrendOutcome model with all fields
- [ ] Migration script
- [ ] calculate_brier_score() function
- [ ] CalibrationService with record_outcome() and get_calibration_report()
- [ ] POST /trends/{id}/outcomes endpoint
- [ ] GET /trends/{id}/calibration endpoint
- [ ] GET /calibration/overall endpoint
- [ ] Calibration bucket analysis
- [ ] Over/under confidence detection
- [ ] Unit tests for Brier score calculation
- [ ] Documentation on how to record outcomes

## Notes

- Requires 2+ months of data to be statistically meaningful
- Consider automated outcome detection for some event types
- Brier score < 0.25 is better than random guessing
- Perfect calibration: 20% predictions happen 20% of the time
- Could extend to track confidence interval coverage
