"""
Weekly and monthly report generation for trends.
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
from src.storage.models import (
    Event,
    EventItem,
    HumanFeedback,
    RawItem,
    Report,
    Source,
    Trend,
    TrendEvidence,
)

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


@dataclass(slots=True)
class MonthlyReportRun:
    scanned: int
    created: int
    updated: int
    period_start: datetime
    period_end: datetime


class ReportGenerator:
    """Generate and persist weekly/monthly trend reports."""

    _CONTRADICTION_RESOLUTION_ACTIONS = ("pin", "mark_noise", "invalidate")

    def __init__(
        self,
        session: AsyncSession,
        client: AsyncOpenAI | Any | None = None,
        model: str | None = None,
        weekly_prompt_path: str = "ai/prompts/weekly_report.md",
        monthly_prompt_path: str = "ai/prompts/monthly_report.md",
    ) -> None:
        self.session = session
        self.model = model or settings.LLM_REPORT_MODEL
        self.weekly_prompt_template = Path(weekly_prompt_path).read_text(encoding="utf-8")
        self.monthly_prompt_template = Path(monthly_prompt_path).read_text(encoding="utf-8")
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

            statistics = await self._build_weekly_statistics(
                trend=trend,
                trend_engine=trend_engine,
                period_start=run_period_start,
                period_end=run_period_end,
            )
            top_events = await self._load_top_events(
                trend_id=trend_id,
                period_start=run_period_start,
                period_end=run_period_end,
                limit=5,
            )
            narrative = await self._build_narrative(
                trend=trend,
                statistics=statistics,
                top_events=top_events,
                period_start=run_period_start,
                period_end=run_period_end,
                prompt_template=self.weekly_prompt_template,
                report_type="weekly",
            )
            top_events_payload = {"events": top_events}

            existing = await self._find_existing_report(
                report_type="weekly",
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

    async def generate_monthly_reports(
        self,
        *,
        period_end: datetime | None = None,
    ) -> MonthlyReportRun:
        run_period_end = (
            _as_utc(period_end) if period_end is not None else datetime.now(tz=UTC)
        ).replace(second=0, microsecond=0)
        run_period_start = run_period_end - timedelta(days=30)

        trends = await self._load_active_trends()
        trend_engine = TrendEngine(session=self.session)
        created = 0
        updated = 0

        for trend in trends:
            trend_id = trend.id
            if trend_id is None:
                continue

            statistics = await self._build_monthly_statistics(
                trend=trend,
                trend_engine=trend_engine,
                period_start=run_period_start,
                period_end=run_period_end,
            )
            top_events = await self._load_top_events(
                trend_id=trend_id,
                period_start=run_period_start,
                period_end=run_period_end,
                limit=10,
            )
            narrative = await self._build_narrative(
                trend=trend,
                statistics=statistics,
                top_events=top_events,
                period_start=run_period_start,
                period_end=run_period_end,
                prompt_template=self.monthly_prompt_template,
                report_type="monthly",
            )
            top_events_payload = {"events": top_events}

            existing = await self._find_existing_report(
                report_type="monthly",
                trend_id=trend_id,
                period_start=run_period_start,
                period_end=run_period_end,
            )
            if existing is None:
                self.session.add(
                    Report(
                        report_type="monthly",
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
        return MonthlyReportRun(
            scanned=len(trends),
            created=created,
            updated=updated,
            period_start=run_period_start,
            period_end=run_period_end,
        )

    async def _load_active_trends(self) -> list[Trend]:
        query = select(Trend).where(Trend.is_active.is_(True)).order_by(Trend.name.asc())
        return list((await self.session.scalars(query)).all())

    async def _find_existing_report(
        self,
        *,
        report_type: str,
        trend_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> Report | None:
        query = (
            select(Report)
            .where(Report.report_type == report_type)
            .where(Report.trend_id == trend_id)
            .where(Report.period_start == period_start)
            .where(Report.period_end == period_end)
            .limit(1)
        )
        existing: Report | None = await self.session.scalar(query)
        return existing

    async def _build_weekly_statistics(
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
        contradiction_analytics = await self._load_contradiction_analytics(
            trend_id=trend_id,
            period_start=period_start,
            period_end=period_end,
        )

        return {
            "current_probability": round(current_probability, 6),
            "weekly_change": round(weekly_change, 6),
            "direction": direction,
            "evidence_count_weekly": int(evidence_count or 0),
            "contradiction_analytics": contradiction_analytics,
        }

    async def _build_monthly_statistics(
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
        monthly_change = (
            current_probability - previous_probability if previous_probability is not None else 0.0
        )
        previous_month_change = await self._calculate_previous_period_change(
            trend_id=trend_id,
            trend_engine=trend_engine,
            period_start=period_start,
            period_end=period_end,
        )
        direction = await trend_engine.get_direction(trend=trend, days=30)
        evidence_count = await self.session.scalar(
            select(func.count(TrendEvidence.id))
            .where(TrendEvidence.trend_id == trend_id)
            .where(TrendEvidence.created_at >= period_start)
            .where(TrendEvidence.created_at <= period_end)
        )
        category_breakdown = await self._load_category_breakdown(
            trend_id=trend_id,
            period_start=period_start,
            period_end=period_end,
        )
        source_breakdown = await self._load_source_breakdown(
            trend_id=trend_id,
            period_start=period_start,
            period_end=period_end,
        )
        weekly_reports = await self._load_weekly_reports(
            trend_id=trend_id,
            period_start=period_start,
            period_end=period_end,
        )
        contradiction_analytics = await self._load_contradiction_analytics(
            trend_id=trend_id,
            period_start=period_start,
            period_end=period_end,
        )

        comparison_delta: float | None = None
        if previous_month_change is not None:
            comparison_delta = round(monthly_change - previous_month_change, 6)

        return {
            "current_probability": round(current_probability, 6),
            "monthly_change": round(monthly_change, 6),
            "previous_month_change": previous_month_change,
            "change_vs_previous_month": comparison_delta,
            "direction": direction,
            "evidence_count_monthly": int(evidence_count or 0),
            "category_breakdown": category_breakdown,
            "source_breakdown": source_breakdown,
            "weekly_reports_used": weekly_reports,
            "weekly_reports_count": len(weekly_reports),
            "contradiction_analytics": contradiction_analytics,
        }

    async def _calculate_previous_period_change(
        self,
        *,
        trend_id: UUID,
        trend_engine: TrendEngine,
        period_start: datetime,
        period_end: datetime,
    ) -> float | None:
        period_length = period_end - period_start
        previous_period_end = period_start
        previous_period_start = previous_period_end - period_length

        previous_end_probability = await trend_engine.get_probability_at(
            trend_id=trend_id,
            at=previous_period_end,
        )
        previous_start_probability = await trend_engine.get_probability_at(
            trend_id=trend_id,
            at=previous_period_start,
        )
        if previous_end_probability is None or previous_start_probability is None:
            return None
        return round(previous_end_probability - previous_start_probability, 6)

    async def _load_weekly_reports(
        self,
        *,
        trend_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> list[dict[str, Any]]:
        query = (
            select(Report)
            .where(Report.report_type == "weekly")
            .where(Report.trend_id == trend_id)
            .where(Report.period_end > period_start)
            .where(Report.period_end <= period_end)
            .order_by(Report.period_end.asc())
        )
        reports = list((await self.session.scalars(query)).all())

        summaries: list[dict[str, Any]] = []
        for report in reports:
            statistics = report.statistics if isinstance(report.statistics, dict) else {}
            summaries.append(
                {
                    "report_id": str(report.id),
                    "period_start": report.period_start.isoformat(),
                    "period_end": report.period_end.isoformat(),
                    "current_probability": float(statistics.get("current_probability", 0.0)),
                    "weekly_change": float(statistics.get("weekly_change", 0.0)),
                    "direction": str(statistics.get("direction", "stable")),
                }
            )
        return summaries

    async def _load_category_breakdown(
        self,
        *,
        trend_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[str, int]:
        query = (
            select(Event.categories)
            .join(TrendEvidence, TrendEvidence.event_id == Event.id)
            .where(TrendEvidence.trend_id == trend_id)
            .where(TrendEvidence.created_at >= period_start)
            .where(TrendEvidence.created_at <= period_end)
            .group_by(Event.id, Event.categories)
        )
        rows = (await self.session.execute(query)).all()

        counts: dict[str, int] = {}
        for row in rows:
            categories = row[0]
            if not isinstance(categories, list):
                continue
            for category in categories:
                category_name = str(category).strip()
                if not category_name:
                    continue
                counts[category_name] = counts.get(category_name, 0) + 1

        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return dict(ordered)

    async def _load_contradiction_analytics(
        self,
        *,
        trend_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[str, Any]:
        contradicted_query = (
            select(
                TrendEvidence.event_id,
                func.min(TrendEvidence.created_at).label("first_contradiction_at"),
            )
            .join(Event, Event.id == TrendEvidence.event_id)
            .where(TrendEvidence.trend_id == trend_id)
            .where(TrendEvidence.created_at >= period_start)
            .where(TrendEvidence.created_at <= period_end)
            .where(Event.has_contradictions.is_(True))
            .group_by(TrendEvidence.event_id)
        )
        contradicted_rows = (await self.session.execute(contradicted_query)).all()
        if not contradicted_rows:
            return {
                "contradicted_events_count": 0,
                "resolved_events_count": 0,
                "unresolved_events_count": 0,
                "resolution_rate": 0.0,
                "avg_resolution_time_hours": None,
                "resolution_actions": {},
            }

        first_contradiction_by_event: dict[UUID, datetime] = {}
        for row in contradicted_rows:
            event_id = row.event_id
            first_contradiction_at = row.first_contradiction_at
            if event_id is None or first_contradiction_at is None:
                continue
            first_contradiction_by_event[event_id] = first_contradiction_at

        event_ids = tuple(first_contradiction_by_event.keys())
        if not event_ids:
            return {
                "contradicted_events_count": 0,
                "resolved_events_count": 0,
                "unresolved_events_count": 0,
                "resolution_rate": 0.0,
                "avg_resolution_time_hours": None,
                "resolution_actions": {},
            }

        feedback_query = (
            select(
                HumanFeedback.target_id,
                HumanFeedback.action,
                HumanFeedback.created_at,
            )
            .where(HumanFeedback.target_type == "event")
            .where(HumanFeedback.target_id.in_(event_ids))
            .where(HumanFeedback.action.in_(self._CONTRADICTION_RESOLUTION_ACTIONS))
            .order_by(HumanFeedback.target_id.asc(), HumanFeedback.created_at.asc())
        )
        feedback_rows = (await self.session.execute(feedback_query)).all()

        first_resolution_by_event: dict[UUID, tuple[datetime, str]] = {}
        for feedback_row in feedback_rows:
            target_id = feedback_row.target_id
            action = feedback_row.action
            created_at = feedback_row.created_at
            if (
                target_id is None
                or created_at is None
                or not isinstance(action, str)
                or target_id in first_resolution_by_event
            ):
                continue
            first_resolution_by_event[target_id] = (created_at, action)

        contradicted_count = len(event_ids)
        resolved_count = len(first_resolution_by_event)
        unresolved_count = contradicted_count - resolved_count
        resolution_rate = round(resolved_count / contradicted_count, 6)

        resolution_actions: dict[str, int] = {}
        resolution_hours: list[float] = []
        for event_id, (resolved_at, action) in first_resolution_by_event.items():
            resolution_actions[action] = resolution_actions.get(action, 0) + 1
            first_contradiction_at = first_contradiction_by_event.get(event_id)
            if first_contradiction_at is None:
                continue
            hours = (resolved_at - first_contradiction_at).total_seconds() / 3600
            resolution_hours.append(max(0.0, hours))

        avg_resolution_time_hours: float | None = None
        if resolution_hours:
            avg_resolution_time_hours = round(sum(resolution_hours) / len(resolution_hours), 2)

        return {
            "contradicted_events_count": contradicted_count,
            "resolved_events_count": resolved_count,
            "unresolved_events_count": unresolved_count,
            "resolution_rate": resolution_rate,
            "avg_resolution_time_hours": avg_resolution_time_hours,
            "resolution_actions": dict(
                sorted(resolution_actions.items(), key=lambda item: (-item[1], item[0]))
            ),
        }

    async def _load_source_breakdown(
        self,
        *,
        trend_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[str, int]:
        query = (
            select(
                Source.type,
                func.count(func.distinct(RawItem.id)),
            )
            .select_from(TrendEvidence)
            .join(EventItem, EventItem.event_id == TrendEvidence.event_id)
            .join(RawItem, RawItem.id == EventItem.item_id)
            .join(Source, Source.id == RawItem.source_id)
            .where(TrendEvidence.trend_id == trend_id)
            .where(TrendEvidence.created_at >= period_start)
            .where(TrendEvidence.created_at <= period_end)
            .group_by(Source.type)
            .order_by(func.count(func.distinct(RawItem.id)).desc())
        )
        rows = (await self.session.execute(query)).all()

        breakdown: dict[str, int] = {}
        for source_type, count in rows:
            value = getattr(source_type, "value", source_type)
            source_name = str(value)
            breakdown[source_name] = int(count or 0)
        return breakdown

    async def _load_top_events(
        self,
        *,
        trend_id: UUID,
        period_start: datetime,
        period_end: datetime,
        limit: int = 5,
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
            .limit(max(1, limit))
        )
        rows = (await self.session.execute(query)).all()

        top_events: list[dict[str, Any]] = []
        for row in rows:
            top_events.append(
                {
                    "event_id": str(row[0]),
                    "impact_score": round(float(row[1] or 0.0), 6),
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
        prompt_template: str,
        report_type: str,
    ) -> str:
        payload = {
            "trend": {
                "id": str(trend.id),
                "name": trend.name,
                "description": trend.description,
            },
            "report_type": report_type,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "statistics": statistics,
            "top_events": top_events,
        }

        if self.client is None:
            return self._fallback_narrative(
                trend=trend,
                report_type=report_type,
                statistics=statistics,
            )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": prompt_template},
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
                report_type=report_type,
            )

        return self._fallback_narrative(
            trend=trend,
            report_type=report_type,
            statistics=statistics,
        )

    @staticmethod
    def _fallback_narrative(
        *,
        trend: Trend,
        report_type: str,
        statistics: dict[str, Any],
    ) -> str:
        contradiction_summary = ""
        confidence_modifier = ""
        contradiction_stats = statistics.get("contradiction_analytics")
        unresolved_events_count = 0
        if isinstance(contradiction_stats, dict):
            contradicted_events_count = int(contradiction_stats.get("contradicted_events_count", 0))
            resolved_events_count = int(contradiction_stats.get("resolved_events_count", 0))
            unresolved_events_count = int(contradiction_stats.get("unresolved_events_count", 0))
            if contradicted_events_count > 0:
                contradiction_summary = (
                    f" Contradiction review tracked {contradicted_events_count} events "
                    f"({resolved_events_count} resolved, {unresolved_events_count} unresolved)."
                )
                if unresolved_events_count > 0:
                    confidence_modifier = " unresolved contradictions"

        def confidence_label(evidence_count: int) -> str:
            if evidence_count >= 20:
                return "high"
            if evidence_count >= 8:
                return "moderate"
            return "limited"

        if report_type == "monthly":
            monthly_change = float(statistics.get("monthly_change", 0.0))
            evidence_count = int(statistics.get("evidence_count_monthly", 0))
            direction = str(statistics.get("direction", "stable"))
            current_probability = float(statistics.get("current_probability", 0.0))
            confidence = confidence_label(evidence_count)
            return (
                f"{trend.name} is currently at {current_probability:.1%} with a monthly change of "
                f"{monthly_change:+.1%}. Direction over 30 days is {direction}, with "
                f"{evidence_count} evidence updates. Confidence is {confidence} based on available "
                f"coverage{confidence_modifier}."
                f"{contradiction_summary}"
            )

        direction = str(statistics.get("direction", "stable"))
        current_probability = float(statistics.get("current_probability", 0.0))
        weekly_change = float(statistics.get("weekly_change", 0.0))
        evidence_count = int(statistics.get("evidence_count_weekly", 0))
        confidence = confidence_label(evidence_count)
        return (
            f"{trend.name} is currently at {current_probability:.1%} with a weekly change of "
            f"{weekly_change:+.1%}. Direction is {direction}, based on {evidence_count} "
            f"evidence updates in the reporting window. Confidence is {confidence} based on "
            f"current evidence volume{confidence_modifier}.{contradiction_summary}"
        )
