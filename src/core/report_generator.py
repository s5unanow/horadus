"""
Weekly report generation for trends.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from openai import AsyncOpenAI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.trend_engine import TrendEngine
from src.storage.models import Event, Report, Trend, TrendEvidence

logger = structlog.get_logger(__name__)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


@dataclass(slots=True)
class WeeklyReportRun:
    scanned: int
    created: int
    updated: int
    period_start: datetime
    period_end: datetime


class ReportGenerator:
    """Generate and persist weekly trend reports."""

    def __init__(
        self,
        session: AsyncSession,
        client: AsyncOpenAI | Any | None = None,
        model: str | None = None,
        prompt_path: str = "ai/prompts/weekly_report.md",
    ) -> None:
        self.session = session
        self.model = model or settings.LLM_REPORT_MODEL
        self.prompt_template = Path(prompt_path).read_text(encoding="utf-8")
        self.client = client if client is not None else self._create_client_optional()

    @staticmethod
    def _create_client_optional() -> AsyncOpenAI | None:
        if not settings.OPENAI_API_KEY.strip():
            return None
        return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def generate_weekly_reports(
        self,
        *,
        period_end: datetime | None = None,
    ) -> WeeklyReportRun:
        run_period_end = (
            _as_utc(period_end) if period_end is not None else datetime.now(tz=UTC)
        ).replace(second=0, microsecond=0)
        run_period_start = run_period_end - timedelta(days=7)

        trends = await self._load_active_trends()
        trend_engine = TrendEngine(session=self.session)
        created = 0
        updated = 0

        for trend in trends:
            trend_id = trend.id
            if trend_id is None:
                continue

            statistics = await self._build_statistics(
                trend=trend,
                trend_engine=trend_engine,
                period_start=run_period_start,
                period_end=run_period_end,
            )
            top_events = await self._load_top_events(
                trend_id=trend_id,
                period_start=run_period_start,
                period_end=run_period_end,
            )
            narrative = await self._build_narrative(
                trend=trend,
                statistics=statistics,
                top_events=top_events,
                period_start=run_period_start,
                period_end=run_period_end,
            )
            top_events_payload = {"events": top_events}

            existing = await self._find_existing_weekly_report(
                trend_id=trend_id,
                period_start=run_period_start,
                period_end=run_period_end,
            )
            if existing is None:
                self.session.add(
                    Report(
                        report_type="weekly",
                        period_start=run_period_start,
                        period_end=run_period_end,
                        trend_id=trend_id,
                        statistics=statistics,
                        narrative=narrative,
                        top_events=top_events_payload,
                    )
                )
                created += 1
            else:
                existing.statistics = statistics
                existing.narrative = narrative
                existing.top_events = top_events_payload
                updated += 1

        await self.session.flush()
        return WeeklyReportRun(
            scanned=len(trends),
            created=created,
            updated=updated,
            period_start=run_period_start,
            period_end=run_period_end,
        )

    async def _load_active_trends(self) -> list[Trend]:
        query = select(Trend).where(Trend.is_active.is_(True)).order_by(Trend.name.asc())
        return list((await self.session.scalars(query)).all())

    async def _find_existing_weekly_report(
        self,
        *,
        trend_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> Report | None:
        query = (
            select(Report)
            .where(Report.report_type == "weekly")
            .where(Report.trend_id == trend_id)
            .where(Report.period_start == period_start)
            .where(Report.period_end == period_end)
            .limit(1)
        )
        existing: Report | None = await self.session.scalar(query)
        return existing

    async def _build_statistics(
        self,
        *,
        trend: Trend,
        trend_engine: TrendEngine,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[str, Any]:
        trend_id = trend.id
        if trend_id is None:
            msg = "Trend id is required to build report statistics"
            raise ValueError(msg)

        current_probability = trend_engine.get_probability(trend)
        previous_probability = await trend_engine.get_probability_at(
            trend_id=trend_id,
            at=period_start,
        )
        weekly_change = (
            current_probability - previous_probability if previous_probability is not None else 0.0
        )
        direction = await trend_engine.get_direction(trend=trend, days=7)
        evidence_count = await self.session.scalar(
            select(func.count(TrendEvidence.id))
            .where(TrendEvidence.trend_id == trend_id)
            .where(TrendEvidence.created_at >= period_start)
            .where(TrendEvidence.created_at <= period_end)
        )

        return {
            "current_probability": round(current_probability, 6),
            "weekly_change": round(weekly_change, 6),
            "direction": direction,
            "evidence_count_weekly": int(evidence_count or 0),
        }

    async def _load_top_events(
        self,
        *,
        trend_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> list[dict[str, Any]]:
        query = (
            select(
                TrendEvidence.event_id,
                func.sum(func.abs(TrendEvidence.delta_log_odds)).label("impact_score"),
                func.count(TrendEvidence.id).label("evidence_count"),
                Event.canonical_summary,
                Event.categories,
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
            .limit(5)
        )
        rows = (await self.session.execute(query)).all()

        top_events: list[dict[str, Any]] = []
        for row in rows:
            top_events.append(
                {
                    "event_id": str(row[0]),
                    "impact_score": float(row[1] or 0.0),
                    "evidence_count": int(row[2] or 0),
                    "summary": str(row[3] or "").strip(),
                    "categories": list(row[4] or []),
                }
            )
        return top_events

    async def _build_narrative(
        self,
        *,
        trend: Trend,
        statistics: dict[str, Any],
        top_events: list[dict[str, Any]],
        period_start: datetime,
        period_end: datetime,
    ) -> str:
        payload = {
            "trend": {
                "id": str(trend.id),
                "name": trend.name,
                "description": trend.description,
            },
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "statistics": statistics,
            "top_events": top_events,
        }

        if self.client is None:
            return self._fallback_narrative(trend=trend, statistics=statistics)

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
                "Report narrative generation failed; using fallback",
                trend_id=str(trend.id),
                trend_name=trend.name,
            )

        return self._fallback_narrative(trend=trend, statistics=statistics)

    @staticmethod
    def _fallback_narrative(*, trend: Trend, statistics: dict[str, Any]) -> str:
        direction = str(statistics.get("direction", "stable"))
        current_probability = float(statistics.get("current_probability", 0.0))
        weekly_change = float(statistics.get("weekly_change", 0.0))
        evidence_count = int(statistics.get("evidence_count_weekly", 0))
        return (
            f"{trend.name} is currently at {current_probability:.1%} with a weekly change of "
            f"{weekly_change:+.1%}. Direction is {direction}, based on {evidence_count} "
            "evidence updates in the reporting window."
        )
