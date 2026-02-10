"""
Retrospective analysis service for trend evidence and outcomes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from openai import AsyncOpenAI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.storage.models import Event, Trend, TrendEvidence, TrendOutcome

logger = structlog.get_logger(__name__)


class RetrospectiveAnalyzer:
    """Build retrospective trend analysis over a time window."""

    def __init__(
        self,
        session: AsyncSession,
        client: AsyncOpenAI | Any | None = None,
        model: str | None = None,
        prompt_path: str = "ai/prompts/retrospective_analysis.md",
    ) -> None:
        self.session = session
        self.model = model or settings.LLM_RETROSPECTIVE_MODEL
        self.prompt_template = Path(prompt_path).read_text(encoding="utf-8")
        self.client = client if client is not None else self._create_client_optional()

    @staticmethod
    def _create_client_optional() -> AsyncOpenAI | None:
        if not settings.OPENAI_API_KEY.strip():
            return None
        return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def analyze(
        self,
        *,
        trend: Trend,
        start_date: datetime,
        end_date: datetime,
    ) -> dict[str, Any]:
        trend_id = trend.id
        if trend_id is None:
            msg = "Trend id is required for retrospective analysis"
            raise ValueError(msg)

        period_start = self._as_utc(start_date)
        period_end = self._as_utc(end_date)
        pivotal_events = await self._load_pivotal_events(
            trend_id=trend_id,
            period_start=period_start,
            period_end=period_end,
        )
        category_breakdown = self._category_breakdown_from_events(pivotal_events)
        predictive_signals = await self._load_predictive_signals(
            trend_id=trend_id,
            period_start=period_start,
            period_end=period_end,
        )
        accuracy_assessment = await self._load_accuracy_assessment(
            trend_id=trend_id,
            period_start=period_start,
            period_end=period_end,
        )
        narrative = await self._build_narrative(
            trend=trend,
            period_start=period_start,
            period_end=period_end,
            pivotal_events=pivotal_events,
            predictive_signals=predictive_signals,
            accuracy_assessment=accuracy_assessment,
        )

        return {
            "trend_id": trend_id,
            "trend_name": trend.name,
            "period_start": period_start,
            "period_end": period_end,
            "pivotal_events": pivotal_events,
            "category_breakdown": category_breakdown,
            "predictive_signals": predictive_signals,
            "accuracy_assessment": accuracy_assessment,
            "narrative": narrative,
        }

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    async def _load_pivotal_events(
        self,
        *,
        trend_id: UUID,
        period_start: datetime,
        period_end: datetime,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        query = (
            select(
                TrendEvidence.event_id,
                Event.canonical_summary,
                Event.categories,
                func.count(TrendEvidence.id).label("evidence_count"),
                func.sum(TrendEvidence.delta_log_odds).label("net_delta_log_odds"),
                func.sum(func.abs(TrendEvidence.delta_log_odds)).label("abs_delta_log_odds"),
            )
            .join(Event, Event.id == TrendEvidence.event_id)
            .where(TrendEvidence.trend_id == trend_id)
            .where(TrendEvidence.created_at >= period_start)
            .where(TrendEvidence.created_at <= period_end)
            .group_by(
                TrendEvidence.event_id,
                Event.canonical_summary,
                Event.categories,
            )
            .order_by(func.sum(func.abs(TrendEvidence.delta_log_odds)).desc())
            .limit(max(1, limit))
        )
        rows = (await self.session.execute(query)).all()

        events: list[dict[str, Any]] = []
        for row in rows:
            net_delta = float(row[4] or 0.0)
            direction = "mixed"
            if net_delta > 0:
                direction = "up"
            elif net_delta < 0:
                direction = "down"

            events.append(
                {
                    "event_id": row[0],
                    "summary": str(row[1] or "").strip(),
                    "categories": list(row[2] or []),
                    "evidence_count": int(row[3] or 0),
                    "net_delta_log_odds": round(net_delta, 6),
                    "abs_delta_log_odds": round(float(row[5] or 0.0), 6),
                    "direction": direction,
                }
            )
        return events

    @staticmethod
    def _category_breakdown_from_events(events: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in events:
            categories = event.get("categories", [])
            if not isinstance(categories, list):
                continue
            for category in categories:
                label = str(category).strip()
                if not label:
                    continue
                counts[label] = counts.get(label, 0) + 1
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return dict(ordered)

    async def _load_predictive_signals(
        self,
        *,
        trend_id: UUID,
        period_start: datetime,
        period_end: datetime,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        query = (
            select(
                TrendEvidence.signal_type,
                func.count(TrendEvidence.id).label("evidence_count"),
                func.sum(TrendEvidence.delta_log_odds).label("net_delta_log_odds"),
                func.sum(func.abs(TrendEvidence.delta_log_odds)).label("abs_delta_log_odds"),
            )
            .where(TrendEvidence.trend_id == trend_id)
            .where(TrendEvidence.created_at >= period_start)
            .where(TrendEvidence.created_at <= period_end)
            .group_by(TrendEvidence.signal_type)
            .order_by(func.sum(func.abs(TrendEvidence.delta_log_odds)).desc())
            .limit(max(1, limit))
        )
        rows = (await self.session.execute(query)).all()

        return [
            {
                "signal_type": str(signal_type),
                "evidence_count": int(evidence_count or 0),
                "net_delta_log_odds": round(float(net_delta or 0.0), 6),
                "abs_delta_log_odds": round(float(abs_delta or 0.0), 6),
            }
            for signal_type, evidence_count, net_delta, abs_delta in rows
        ]

    async def _load_accuracy_assessment(
        self,
        *,
        trend_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[str, int | float | None]:
        query = (
            select(
                TrendOutcome.brier_score,
                TrendOutcome.outcome,
            )
            .where(TrendOutcome.trend_id == trend_id)
            .where(TrendOutcome.prediction_date >= period_start)
            .where(TrendOutcome.prediction_date <= period_end)
        )
        rows = (await self.session.execute(query)).all()
        total = len(rows)
        resolved = sum(1 for _brier_score, outcome in rows if outcome is not None)
        scored_values = [float(brier_score) for brier_score, _ in rows if brier_score is not None]
        mean_brier = round(sum(scored_values) / len(scored_values), 6) if scored_values else None
        resolved_rate = round(resolved / total, 6) if total > 0 else None

        return {
            "outcome_count": total,
            "resolved_outcomes": resolved,
            "scored_outcomes": len(scored_values),
            "mean_brier_score": mean_brier,
            "resolved_rate": resolved_rate,
        }

    async def _build_narrative(
        self,
        *,
        trend: Trend,
        period_start: datetime,
        period_end: datetime,
        pivotal_events: list[dict[str, Any]],
        predictive_signals: list[dict[str, Any]],
        accuracy_assessment: dict[str, int | float | None],
    ) -> str:
        payload = {
            "trend": {
                "id": str(trend.id),
                "name": trend.name,
                "description": trend.description,
            },
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "pivotal_events": pivotal_events,
            "predictive_signals": predictive_signals,
            "accuracy_assessment": accuracy_assessment,
        }

        if self.client is None:
            return self._fallback_narrative(
                trend_name=trend.name,
                pivotal_events=pivotal_events,
                predictive_signals=predictive_signals,
                accuracy_assessment=accuracy_assessment,
            )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": self.prompt_template},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
                ],
            )
            content = getattr(response.choices[0].message, "content", None)
            if isinstance(content, str) and content.strip():
                return content.strip()
        except Exception:
            logger.exception(
                "Retrospective narrative generation failed; using fallback",
                trend_id=str(trend.id),
                trend_name=trend.name,
            )

        return self._fallback_narrative(
            trend_name=trend.name,
            pivotal_events=pivotal_events,
            predictive_signals=predictive_signals,
            accuracy_assessment=accuracy_assessment,
        )

    @staticmethod
    def _fallback_narrative(
        *,
        trend_name: str,
        pivotal_events: list[dict[str, Any]],
        predictive_signals: list[dict[str, Any]],
        accuracy_assessment: dict[str, int | float | None],
    ) -> str:
        top_signal = "none"
        if predictive_signals:
            top_signal = str(predictive_signals[0].get("signal_type", "none"))
        event_count = len(pivotal_events)
        brier_score = accuracy_assessment.get("mean_brier_score")
        brier_text = "n/a" if brier_score is None else f"{float(brier_score):.3f}"
        resolved_rate = accuracy_assessment.get("resolved_rate")
        resolved_text = "unknown"
        uncertainty_note = " Conclusions should be treated as provisional."
        if isinstance(resolved_rate, int | float):
            resolved_text = f"{float(resolved_rate):.0%}"
            if float(resolved_rate) >= 0.7:
                uncertainty_note = " Confidence is moderate given current outcome coverage."
            elif float(resolved_rate) >= 0.4:
                uncertainty_note = " Confidence is limited due to partial outcome coverage."
            else:
                uncertainty_note = " Confidence is low because outcome coverage is sparse."

        return (
            f"Retrospective analysis for {trend_name} found {event_count} pivotal events in the "
            f"selected window. The most influential signal family was '{top_signal}'. "
            f"Calibration snapshot mean Brier score is {brier_text}, with resolved coverage "
            f"at {resolved_text}.{uncertainty_note}"
        )
