from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.report_generator import NarrativeResult, ReportGenerator, _as_utc
from src.processing.cost_tracker import TIER2, BudgetExceededError

pytestmark = pytest.mark.unit


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def test_as_utc_normalizes_naive_and_aware_datetimes() -> None:
    naive = datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC).replace(tzinfo=None)
    aware = datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC)

    assert _as_utc(naive).tzinfo is UTC
    assert _as_utc(aware) == aware


def test_create_client_optional_and_secondary_client_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[dict[str, str]] = []

    class FakeClient:
        def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
            created.append({"token_value": api_key, "base_url": base_url or ""})

    monkeypatch.setattr("src.core.report_generator.AsyncOpenAI", FakeClient)

    assert ReportGenerator._create_client_optional(api_key="   ") is None
    assert isinstance(
        ReportGenerator._create_client_optional(
            api_key="unit-test-key",  # pragma: allowlist secret
            base_url=" https://api.example.test/v1 ",
        ),
        FakeClient,
    )
    assert isinstance(
        ReportGenerator._create_client_optional(
            api_key="unit-test-key-no-base",  # pragma: allowlist secret
        ),
        FakeClient,
    )
    assert created == [
        {
            "token_value": "unit-test-key",
            "base_url": "https://api.example.test/v1",
        },
        {
            "token_value": "unit-test-key-no-base",
            "base_url": "",
        },
    ]

    generator = ReportGenerator.__new__(ReportGenerator)
    generator.secondary_model = None
    generator.secondary_base_url = None
    assert generator._build_secondary_client(secondary_client=None) is None

    generator.secondary_model = "secondary-model"
    explicit = object()
    assert generator._build_secondary_client(secondary_client=explicit) is explicit

    monkeypatch.setattr(settings, "LLM_SECONDARY_API_KEY", "test-value-2")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-value-1")
    generator.secondary_base_url = "https://secondary.example.test/v1"
    client = generator._build_secondary_client(secondary_client=None)
    assert isinstance(client, FakeClient)
    assert created[-1] == {
        "token_value": "test-value-2",
        "base_url": "https://secondary.example.test/v1",
    }


def test_build_secondary_client_rejects_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = ReportGenerator.__new__(ReportGenerator)
    generator.secondary_model = "secondary-model"
    generator.secondary_base_url = None
    monkeypatch.setattr(settings, "LLM_SECONDARY_API_KEY", "   ")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "   ")

    with pytest.raises(ValueError, match="without API key"):
        generator._build_secondary_client(secondary_client=None)


@pytest.mark.asyncio
async def test_load_contradiction_analytics_summarizes_resolution(mock_db_session) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    now = datetime.now(tz=UTC)
    event_id_one = uuid4()
    event_id_two = uuid4()

    mock_db_session.execute.side_effect = [
        SimpleNamespace(
            all=lambda: [
                SimpleNamespace(
                    event_id=event_id_one,
                    first_contradiction_at=now - timedelta(hours=8),
                ),
                SimpleNamespace(
                    event_id=event_id_two,
                    first_contradiction_at=now - timedelta(hours=5),
                ),
            ]
        ),
        SimpleNamespace(
            all=lambda: [
                SimpleNamespace(
                    target_id=event_id_one,
                    action="invalidate",
                    created_at=now - timedelta(hours=2),
                ),
                SimpleNamespace(
                    target_id=event_id_one,
                    action="pin",
                    created_at=now - timedelta(hours=1),
                ),
                SimpleNamespace(
                    target_id=event_id_two,
                    action="mark_noise",
                    created_at=now - timedelta(hours=4),
                ),
            ]
        ),
    ]

    result = await generator._load_contradiction_analytics(
        trend_id=uuid4(),
        period_start=now - timedelta(days=7),
        period_end=now,
    )

    assert result["contradicted_events_count"] == 2
    assert result["resolved_events_count"] == 2
    assert result["unresolved_events_count"] == 0
    assert result["resolution_rate"] == 1.0
    assert result["avg_resolution_time_hours"] == 3.5
    assert result["resolution_actions"] == {
        "invalidate": 1,
        "mark_noise": 1,
    }


@pytest.mark.asyncio
async def test_load_contradiction_analytics_handles_empty_period(mock_db_session) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    now = datetime.now(tz=UTC)
    mock_db_session.execute.return_value = SimpleNamespace(all=list)

    result = await generator._load_contradiction_analytics(
        trend_id=uuid4(),
        period_start=now - timedelta(days=7),
        period_end=now,
    )

    assert result == {
        "contradicted_events_count": 0,
        "resolved_events_count": 0,
        "unresolved_events_count": 0,
        "resolution_rate": 0.0,
        "avg_resolution_time_hours": None,
        "resolution_actions": {},
    }
    assert mock_db_session.execute.await_count == 1


@pytest.mark.asyncio
async def test_load_active_trends_and_find_existing_report(mock_db_session) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    trend = SimpleNamespace(name="Alpha")
    report = SimpleNamespace(id=uuid4())
    mock_db_session.scalars.return_value = _Result([trend])
    mock_db_session.scalar.return_value = report

    trends = await generator._load_active_trends()
    existing = await generator._find_existing_report(
        report_type="weekly",
        trend_id=uuid4(),
        period_start=datetime(2026, 3, 1, tzinfo=UTC),
        period_end=datetime(2026, 3, 7, tzinfo=UTC),
    )

    assert trends == [trend]
    assert existing is report


@pytest.mark.asyncio
async def test_build_weekly_statistics_includes_contradiction_analytics(mock_db_session) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    trend = SimpleNamespace(id=uuid4())
    trend_engine = SimpleNamespace(
        get_probability=lambda _trend: 0.55,
        get_probability_at=AsyncMock(return_value=0.50),
        get_direction=AsyncMock(return_value="rising"),
    )
    mock_db_session.scalar.return_value = 7
    analytics = {
        "contradicted_events_count": 3,
        "resolved_events_count": 1,
        "unresolved_events_count": 2,
        "resolution_rate": 0.333333,
        "avg_resolution_time_hours": 11.25,
        "resolution_actions": {"invalidate": 1},
    }
    generator._load_contradiction_analytics = AsyncMock(return_value=analytics)

    now = datetime.now(tz=UTC)
    result = await generator._build_weekly_statistics(
        trend=trend,
        trend_engine=trend_engine,
        period_start=now - timedelta(days=7),
        period_end=now,
    )

    assert result["current_probability"] == 0.55
    assert result["weekly_change"] == 0.05
    assert result["direction"] == "rising"
    assert result["evidence_count_weekly"] == 7
    assert result["contradiction_analytics"] == analytics


@pytest.mark.asyncio
async def test_build_weekly_statistics_requires_trend_id(mock_db_session) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    trend_engine = SimpleNamespace(
        get_probability=lambda _trend: 0.5,
        get_probability_at=AsyncMock(return_value=0.4),
        get_direction=AsyncMock(return_value="stable"),
    )

    with pytest.raises(ValueError, match="Trend id is required"):
        await generator._build_weekly_statistics(
            trend=SimpleNamespace(id=None),
            trend_engine=trend_engine,
            period_start=datetime(2026, 3, 1, tzinfo=UTC),
            period_end=datetime(2026, 3, 7, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_build_monthly_statistics_includes_contradiction_analytics(mock_db_session) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    trend = SimpleNamespace(id=uuid4())
    trend_engine = SimpleNamespace(
        get_probability=lambda _trend: 0.42,
        get_probability_at=AsyncMock(return_value=0.40),
        get_direction=AsyncMock(return_value="stable"),
    )
    mock_db_session.scalar.return_value = 11
    generator._calculate_previous_period_change = AsyncMock(return_value=0.03)
    generator._load_category_breakdown = AsyncMock(return_value={"military": 4})
    generator._load_source_breakdown = AsyncMock(return_value={"rss": 6})
    generator._load_weekly_reports = AsyncMock(return_value=[])
    analytics = {
        "contradicted_events_count": 4,
        "resolved_events_count": 3,
        "unresolved_events_count": 1,
        "resolution_rate": 0.75,
        "avg_resolution_time_hours": 8.5,
        "resolution_actions": {"mark_noise": 2, "invalidate": 1},
    }
    generator._load_contradiction_analytics = AsyncMock(return_value=analytics)

    now = datetime.now(tz=UTC)
    result = await generator._build_monthly_statistics(
        trend=trend,
        trend_engine=trend_engine,
        period_start=now - timedelta(days=30),
        period_end=now,
    )

    assert result["current_probability"] == 0.42
    assert result["monthly_change"] == 0.02
    assert result["change_vs_previous_month"] == -0.01
    assert result["direction"] == "stable"
    assert result["evidence_count_monthly"] == 11
    assert result["contradiction_analytics"] == analytics


@pytest.mark.asyncio
async def test_build_monthly_statistics_handles_missing_previous_month_change(
    mock_db_session,
) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    trend = SimpleNamespace(id=uuid4())
    trend_engine = SimpleNamespace(
        get_probability=lambda _trend: 0.42,
        get_probability_at=AsyncMock(return_value=None),
        get_direction=AsyncMock(return_value="stable"),
    )
    mock_db_session.scalar.return_value = None
    generator._calculate_previous_period_change = AsyncMock(return_value=None)
    generator._load_category_breakdown = AsyncMock(return_value={})
    generator._load_source_breakdown = AsyncMock(return_value={})
    generator._load_weekly_reports = AsyncMock(return_value=[{"id": "weekly"}])
    generator._load_contradiction_analytics = AsyncMock(return_value={})

    now = datetime.now(tz=UTC)
    result = await generator._build_monthly_statistics(
        trend=trend,
        trend_engine=trend_engine,
        period_start=now - timedelta(days=30),
        period_end=now,
    )

    assert result["monthly_change"] == 0.0
    assert result["change_vs_previous_month"] is None
    assert result["weekly_reports_count"] == 1


@pytest.mark.asyncio
async def test_build_monthly_statistics_requires_trend_id(mock_db_session) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    trend_engine = SimpleNamespace(
        get_probability=lambda _trend: 0.5,
        get_probability_at=AsyncMock(return_value=0.4),
        get_direction=AsyncMock(return_value="stable"),
    )

    with pytest.raises(ValueError, match="Trend id is required"):
        await generator._build_monthly_statistics(
            trend=SimpleNamespace(id=None),
            trend_engine=trend_engine,
            period_start=datetime(2026, 3, 1, tzinfo=UTC),
            period_end=datetime(2026, 3, 31, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_calculate_previous_period_change_handles_missing_snapshots(mock_db_session) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    trend_engine = SimpleNamespace(
        get_probability_at=AsyncMock(side_effect=[0.4, None]),
    )

    result = await generator._calculate_previous_period_change(
        trend_id=uuid4(),
        trend_engine=trend_engine,
        period_start=datetime(2026, 3, 1, tzinfo=UTC),
        period_end=datetime(2026, 3, 31, tzinfo=UTC),
    )

    assert result is None


@pytest.mark.asyncio
async def test_load_weekly_reports_category_breakdown_source_breakdown_and_top_events(
    mock_db_session,
) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    report = SimpleNamespace(
        id=uuid4(),
        period_start=datetime(2026, 3, 1, tzinfo=UTC),
        period_end=datetime(2026, 3, 7, tzinfo=UTC),
        statistics={"current_probability": 0.4, "weekly_change": 0.1, "direction": "rising"},
    )
    mock_db_session.scalars.return_value = _Result([report])
    mock_db_session.execute.side_effect = [
        _Result([(["military", " ", "diplomatic"],), ("bad",)]),
        _Result([(SimpleNamespace(value="rss"), 3), ("telegram", None)]),
        _Result([(uuid4(), 1.25, 4, " event ", ["military"])]),
    ]

    weekly = await generator._load_weekly_reports(
        trend_id=uuid4(),
        period_start=datetime(2026, 3, 1, tzinfo=UTC),
        period_end=datetime(2026, 3, 31, tzinfo=UTC),
    )
    categories = await generator._load_category_breakdown(
        trend_id=uuid4(),
        period_start=datetime(2026, 3, 1, tzinfo=UTC),
        period_end=datetime(2026, 3, 31, tzinfo=UTC),
    )
    sources = await generator._load_source_breakdown(
        trend_id=uuid4(),
        period_start=datetime(2026, 3, 1, tzinfo=UTC),
        period_end=datetime(2026, 3, 31, tzinfo=UTC),
    )
    top_events = await generator._load_top_events(
        trend_id=uuid4(),
        period_start=datetime(2026, 3, 1, tzinfo=UTC),
        period_end=datetime(2026, 3, 31, tzinfo=UTC),
    )

    assert weekly[0]["direction"] == "rising"
    assert categories == {"diplomatic": 1, "military": 1}
    assert sources == {"rss": 3, "telegram": 0}
    assert top_events[0]["summary"] == "event"
    assert top_events[0]["impact_score"] == 1.25


def test_fallback_narrative_weekly_includes_confidence_and_contradictions() -> None:
    trend = SimpleNamespace(name="Signal Watch")
    narrative = ReportGenerator._fallback_narrative(
        trend=trend,
        report_type="weekly",
        statistics={
            "current_probability": 0.42,
            "weekly_change": 0.05,
            "direction": "rising",
            "evidence_count_weekly": 4,
            "contradiction_analytics": {
                "contradicted_events_count": 3,
                "resolved_events_count": 1,
                "unresolved_events_count": 2,
            },
        },
    )

    assert "Signal Watch is currently at 42.0%" in narrative
    assert "Confidence is limited" in narrative
    assert "3 events (1 resolved, 2 unresolved)" in narrative


def test_fallback_narrative_monthly_scales_confidence_with_coverage() -> None:
    trend = SimpleNamespace(name="Signal Watch")
    narrative = ReportGenerator._fallback_narrative(
        trend=trend,
        report_type="monthly",
        statistics={
            "current_probability": 0.58,
            "monthly_change": -0.02,
            "direction": "stable",
            "evidence_count_monthly": 24,
        },
    )

    assert "monthly change of -2.0%" in narrative
    assert "Confidence is high" in narrative


def test_fallback_narrative_monthly_uses_moderate_confidence_when_contradictions_resolved() -> None:
    trend = SimpleNamespace(name="Signal Watch")
    narrative = ReportGenerator._fallback_narrative(
        trend=trend,
        report_type="monthly",
        statistics={
            "current_probability": 0.58,
            "monthly_change": 0.01,
            "direction": "stable",
            "evidence_count_monthly": 8,
            "contradiction_analytics": {
                "contradicted_events_count": 2,
                "resolved_events_count": 2,
                "unresolved_events_count": 0,
            },
        },
    )

    assert "Confidence is moderate" in narrative
    assert "2 events (2 resolved, 0 unresolved)" in narrative


def test_fallback_narrative_without_contradicted_events_skips_summary() -> None:
    trend = SimpleNamespace(name="Signal Watch")
    narrative = ReportGenerator._fallback_narrative(
        trend=trend,
        report_type="weekly",
        statistics={
            "current_probability": 0.42,
            "weekly_change": 0.05,
            "direction": "rising",
            "evidence_count_weekly": 8,
            "contradiction_analytics": {
                "contradicted_events_count": 0,
                "resolved_events_count": 0,
                "unresolved_events_count": 0,
            },
        },
    )

    assert "Contradiction review tracked" not in narrative
    assert "Confidence is moderate" in narrative


def test_weekly_prompt_contract_requires_grounding_and_uncertainty_language() -> None:
    prompt = Path("ai/prompts/weekly_report.md").read_text(encoding="utf-8")

    assert (
        "Every narrative claim must be directly supported by the provided structured payload"
        in prompt
    )
    assert "explicitly framed as uncertainty/inference" in prompt
    assert "Do not add causal explanations, locations, or confidence labels" in prompt
    assert "If evidence is sparse, conflicting, or low-coverage" in prompt


def test_monthly_prompt_contract_forbids_unsupported_causal_explanations() -> None:
    prompt = Path("ai/prompts/monthly_report.md").read_text(encoding="utf-8")

    assert "Describe likely drivers only when the payload directly supports them" in prompt
    assert "otherwise say the cause is uncertain" in prompt
    assert "explicitly framed as uncertainty/inference" in prompt
    assert "Do not add unsupported causal explanations" in prompt


@pytest.mark.asyncio
async def test_build_narrative_uses_fallback_when_budget_denied(mock_db_session) -> None:
    create_mock = AsyncMock()
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock)))
    cost_tracker = SimpleNamespace(
        ensure_within_budget=AsyncMock(side_effect=BudgetExceededError("budget denied")),
        record_usage=AsyncMock(return_value=None),
    )
    generator = ReportGenerator(
        session=mock_db_session,
        client=client,
        cost_tracker=cost_tracker,
    )
    trend = SimpleNamespace(id=uuid4(), name="Signal Watch", description="desc")

    result = await generator._build_narrative(
        trend=trend,
        statistics={
            "current_probability": 0.42,
            "weekly_change": 0.05,
            "direction": "rising",
            "evidence_count_weekly": 4,
        },
        top_events=[],
        period_start=datetime.now(tz=UTC) - timedelta(days=7),
        period_end=datetime.now(tz=UTC),
        prompt_template="prompt",
        report_type="weekly",
    )

    assert "Signal Watch is currently at" in result.narrative
    assert result.grounding_status == "fallback"
    create_mock.assert_not_awaited()
    cost_tracker.record_usage.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_narrative_uses_fallback_when_client_missing(mock_db_session) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    generator.client = None
    trend = SimpleNamespace(id=uuid4(), name="Signal Watch", description="desc")

    result = await generator._build_narrative(
        trend=trend,
        statistics={
            "current_probability": 0.42,
            "weekly_change": 0.05,
            "direction": "rising",
            "evidence_count_weekly": 4,
        },
        top_events=[],
        period_start=datetime.now(tz=UTC) - timedelta(days=7),
        period_end=datetime.now(tz=UTC),
        prompt_template="prompt",
        report_type="weekly",
    )

    assert result.grounding_status in {"fallback", "flagged"}


@pytest.mark.asyncio
async def test_build_narrative_fails_over_to_secondary_route(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_ROUTE_RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "LLM_ROUTE_RETRY_BACKOFF_SECONDS", 0.0)
    primary_calls: list[dict[str, object]] = []
    secondary_calls: list[dict[str, object]] = []

    class PrimaryCompletions:
        async def create(self, **kwargs):
            primary_calls.append(kwargs)
            raise TimeoutError("primary timeout")

    class SecondaryCompletions:
        async def create(self, **kwargs):
            secondary_calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="LLM report narrative"))],
                usage=SimpleNamespace(prompt_tokens=15, completion_tokens=6),
            )

    cost_tracker = SimpleNamespace(
        ensure_within_budget=AsyncMock(return_value=None),
        record_usage=AsyncMock(return_value=None),
    )
    generator = ReportGenerator(
        session=mock_db_session,
        client=SimpleNamespace(chat=SimpleNamespace(completions=PrimaryCompletions())),
        secondary_client=SimpleNamespace(chat=SimpleNamespace(completions=SecondaryCompletions())),
        secondary_model="gpt-4.1-nano",
        report_api_mode="chat_completions",
        cost_tracker=cost_tracker,
        primary_provider="openai",
        secondary_provider="openai-secondary",
    )
    trend = SimpleNamespace(id=uuid4(), name="Signal Watch", description="desc")

    result = await generator._build_narrative(
        trend=trend,
        statistics={
            "current_probability": 0.42,
            "weekly_change": 0.05,
            "direction": "rising",
            "evidence_count_weekly": 4,
        },
        top_events=[{"summary": "s", "impact_score": 1.0, "evidence_count": 1, "categories": []}],
        period_start=datetime.now(tz=UTC) - timedelta(days=7),
        period_end=datetime.now(tz=UTC),
        prompt_template="prompt",
        report_type="weekly",
    )

    assert result.narrative == "LLM report narrative"
    assert result.grounding_status == "grounded"
    assert len(primary_calls) == 2
    assert len(secondary_calls) == 1
    assert cost_tracker.ensure_within_budget.await_count == 2
    assert cost_tracker.ensure_within_budget.await_args_list[0].args == (TIER2,)
    assert cost_tracker.ensure_within_budget.await_args_list[0].kwargs == {
        "provider": "openai",
        "model": "gpt-4.1-mini",
    }
    assert cost_tracker.ensure_within_budget.await_args_list[1].args == (TIER2,)
    assert cost_tracker.ensure_within_budget.await_args_list[1].kwargs == {
        "provider": "openai-secondary",
        "model": "gpt-4.1-nano",
    }
    cost_tracker.record_usage.assert_awaited_once_with(
        tier=TIER2,
        input_tokens=15,
        output_tokens=6,
        provider="openai-secondary",
        model="gpt-4.1-nano",
    )


@pytest.mark.asyncio
async def test_build_narrative_supports_responses_api_mode_pilot(mock_db_session) -> None:
    responses_calls: list[dict[str, object]] = []

    class ResponsesApi:
        async def create(self, **kwargs):
            responses_calls.append(kwargs)
            return SimpleNamespace(
                output_text="LLM report narrative (responses)",
                usage=SimpleNamespace(input_tokens=12, output_tokens=5),
            )

    cost_tracker = SimpleNamespace(
        ensure_within_budget=AsyncMock(return_value=None),
        record_usage=AsyncMock(return_value=None),
    )
    generator = ReportGenerator(
        session=mock_db_session,
        client=SimpleNamespace(responses=ResponsesApi()),
        report_api_mode="responses",
        cost_tracker=cost_tracker,
    )
    trend = SimpleNamespace(id=uuid4(), name="Signal Watch", description="desc")

    result = await generator._build_narrative(
        trend=trend,
        statistics={
            "current_probability": 0.42,
            "weekly_change": 0.05,
            "direction": "rising",
            "evidence_count_weekly": 4,
        },
        top_events=[],
        period_start=datetime.now(tz=UTC) - timedelta(days=7),
        period_end=datetime.now(tz=UTC),
        prompt_template="prompt",
        report_type="weekly",
    )

    assert result.narrative == "LLM report narrative (responses)"
    assert result.grounding_status == "grounded"
    assert len(responses_calls) == 1
    cost_tracker.ensure_within_budget.assert_awaited_once_with(
        TIER2,
        provider="openai",
        model="gpt-4.1-mini",
    )
    cost_tracker.record_usage.assert_awaited_once_with(
        tier=TIER2,
        input_tokens=12,
        output_tokens=5,
        provider="openai",
        model="gpt-4.1-mini",
    )


@pytest.mark.asyncio
async def test_build_narrative_falls_back_when_grounding_fails(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CompletionsApi:
        async def create(self, **kwargs):
            _ = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="Probability is 90% with 4 updates.")
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=9, completion_tokens=5),
            )

    real_evaluate_narrative_grounding = (
        ReportGenerator._build_fallback_narrative_result.__globals__["evaluate_narrative_grounding"]
    )
    evaluation_calls = 0

    def _evaluate_narrative_grounding_once_failed(**kwargs):
        nonlocal evaluation_calls
        evaluation_calls += 1
        if evaluation_calls == 1:
            return SimpleNamespace(
                is_grounded=False,
                violation_count=1,
                unsupported_claims=("90%",),
            )
        return real_evaluate_narrative_grounding(**kwargs)

    monkeypatch.setattr(
        "src.core.report_generator.evaluate_narrative_grounding",
        _evaluate_narrative_grounding_once_failed,
    )
    cost_tracker = SimpleNamespace(
        ensure_within_budget=AsyncMock(return_value=None),
        record_usage=AsyncMock(return_value=None),
    )
    generator = ReportGenerator(
        session=mock_db_session,
        client=SimpleNamespace(chat=SimpleNamespace(completions=CompletionsApi())),
        report_api_mode="chat_completions",
        cost_tracker=cost_tracker,
    )
    trend = SimpleNamespace(id=uuid4(), name="Signal Watch", description="desc")

    result = await generator._build_narrative(
        trend=trend,
        statistics={
            "current_probability": 0.42,
            "weekly_change": 0.05,
            "direction": "rising",
            "evidence_count_weekly": 4,
        },
        top_events=[],
        period_start=datetime.now(tz=UTC) - timedelta(days=7),
        period_end=datetime.now(tz=UTC),
        prompt_template="prompt",
        report_type="weekly",
    )

    assert result.grounding_status == "fallback"
    assert "Signal Watch is currently at 42.0%" in result.narrative


@pytest.mark.asyncio
async def test_build_narrative_falls_back_when_model_returns_blank_content(mock_db_session) -> None:
    class CompletionsApi:
        async def create(self, **kwargs):
            _ = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=" "))],
                usage=SimpleNamespace(prompt_tokens=9, completion_tokens=5),
            )

    generator = ReportGenerator(
        session=mock_db_session,
        client=SimpleNamespace(chat=SimpleNamespace(completions=CompletionsApi())),
        report_api_mode="chat_completions",
        cost_tracker=SimpleNamespace(
            ensure_within_budget=AsyncMock(return_value=None),
            record_usage=AsyncMock(return_value=None),
        ),
    )
    trend = SimpleNamespace(id=uuid4(), name="Signal Watch", description="desc")

    result = await generator._build_narrative(
        trend=trend,
        statistics={
            "current_probability": 0.42,
            "weekly_change": 0.05,
            "direction": "rising",
            "evidence_count_weekly": 4,
        },
        top_events=[],
        period_start=datetime.now(tz=UTC) - timedelta(days=7),
        period_end=datetime.now(tz=UTC),
        prompt_template="prompt",
        report_type="weekly",
    )

    assert result.grounding_status == "fallback"


@pytest.mark.asyncio
async def test_build_narrative_falls_back_when_all_routes_fail(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_ROUTE_RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "LLM_ROUTE_RETRY_BACKOFF_SECONDS", 0.0)

    class PrimaryCompletions:
        async def create(self, **kwargs):
            _ = kwargs
            raise TimeoutError("primary timeout")

    class SecondaryCompletions:
        async def create(self, **kwargs):
            _ = kwargs
            raise TimeoutError("secondary timeout")

    generator = ReportGenerator(
        session=mock_db_session,
        client=SimpleNamespace(chat=SimpleNamespace(completions=PrimaryCompletions())),
        secondary_client=SimpleNamespace(chat=SimpleNamespace(completions=SecondaryCompletions())),
        secondary_model="gpt-4.1-nano",
        report_api_mode="chat_completions",
        cost_tracker=SimpleNamespace(
            ensure_within_budget=AsyncMock(return_value=None),
            record_usage=AsyncMock(return_value=None),
        ),
    )
    trend = SimpleNamespace(id=uuid4(), name="Signal Watch", description="desc")

    result = await generator._build_narrative(
        trend=trend,
        statistics={
            "current_probability": 0.42,
            "weekly_change": 0.05,
            "direction": "rising",
            "evidence_count_weekly": 4,
        },
        top_events=[],
        period_start=datetime.now(tz=UTC) - timedelta(days=7),
        period_end=datetime.now(tz=UTC),
        prompt_template="prompt",
        report_type="weekly",
    )

    assert "Signal Watch is currently at" in result.narrative
    assert result.grounding_status == "fallback"


@pytest.mark.asyncio
async def test_generate_monthly_reports_updates_existing_report(mock_db_session) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    trend_id = uuid4()
    trend = SimpleNamespace(id=trend_id, name="Signal Watch", description="desc")
    existing = SimpleNamespace(
        statistics={},
        narrative="old",
        grounding_status="fallback",
        grounding_violation_count=1,
        grounding_references=None,
        top_events=None,
    )

    generator._load_active_trends = AsyncMock(return_value=[trend])
    generator._build_monthly_statistics = AsyncMock(return_value={"current_probability": 0.42})
    generator._load_top_events = AsyncMock(return_value=[{"summary": "event"}])
    generator._build_narrative = AsyncMock(
        return_value=NarrativeResult(
            narrative="Updated narrative",
            grounding_status="grounded",
            grounding_violation_count=0,
            grounding_references={"supported_claims": []},
        )
    )
    generator._find_existing_report = AsyncMock(return_value=existing)

    run = await generator.generate_monthly_reports()

    assert run.created == 0
    assert run.updated == 1
    assert existing.narrative == "Updated narrative"
    assert existing.grounding_status == "grounded"
    assert existing.top_events == {"events": [{"summary": "event"}]}


@pytest.mark.asyncio
async def test_generate_weekly_reports_updates_existing_and_skips_idless_trends(
    mock_db_session,
) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    trend = SimpleNamespace(id=uuid4(), name="Signal Watch", description="desc")
    existing = SimpleNamespace(
        statistics={},
        narrative="old",
        grounding_status="fallback",
        grounding_violation_count=1,
        grounding_references=None,
        top_events=None,
    )

    generator._load_active_trends = AsyncMock(return_value=[SimpleNamespace(id=None), trend])
    generator._build_weekly_statistics = AsyncMock(return_value={"current_probability": 0.42})
    generator._load_top_events = AsyncMock(return_value=[{"summary": "event"}])
    generator._build_narrative = AsyncMock(
        return_value=NarrativeResult(
            narrative="Updated weekly narrative",
            grounding_status="grounded",
            grounding_violation_count=0,
            grounding_references={"supported_claims": []},
        )
    )
    generator._find_existing_report = AsyncMock(return_value=existing)

    run = await generator.generate_weekly_reports()

    assert run.scanned == 2
    assert run.created == 0
    assert run.updated == 1
    assert existing.narrative == "Updated weekly narrative"


@pytest.mark.asyncio
async def test_generate_monthly_reports_creates_new_and_skips_idless_trends(
    mock_db_session,
) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    trend_id = uuid4()
    trend = SimpleNamespace(id=trend_id, name="Signal Watch", description="desc")

    generator._load_active_trends = AsyncMock(return_value=[SimpleNamespace(id=None), trend])
    generator._build_monthly_statistics = AsyncMock(return_value={"current_probability": 0.42})
    generator._load_top_events = AsyncMock(return_value=[{"summary": "event"}])
    generator._build_narrative = AsyncMock(
        return_value=NarrativeResult(
            narrative="Monthly narrative",
            grounding_status="grounded",
            grounding_violation_count=0,
            grounding_references=None,
        )
    )
    generator._find_existing_report = AsyncMock(return_value=None)

    run = await generator.generate_monthly_reports()

    assert run.scanned == 2
    assert run.created == 1
    assert run.updated == 0
    persisted = mock_db_session.add.call_args.args[0]
    assert persisted.report_type == "monthly"
    assert persisted.narrative == "Monthly narrative"


@pytest.mark.asyncio
async def test_calculate_previous_period_change_returns_delta_when_snapshots_exist(
    mock_db_session,
) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    trend_engine = SimpleNamespace(
        get_probability_at=AsyncMock(side_effect=[0.45, 0.40]),
    )

    result = await generator._calculate_previous_period_change(
        trend_id=uuid4(),
        trend_engine=trend_engine,
        period_start=datetime(2026, 3, 1, tzinfo=UTC),
        period_end=datetime(2026, 3, 31, tzinfo=UTC),
    )

    assert result == 0.05


@pytest.mark.asyncio
async def test_load_contradiction_analytics_handles_invalid_rows_and_missing_resolution_deltas(
    mock_db_session,
) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    now = datetime.now(tz=UTC)
    valid_event_id = uuid4()
    extra_event_id = uuid4()

    mock_db_session.execute.side_effect = [
        _Result(
            [
                SimpleNamespace(event_id=None, first_contradiction_at=now),
                SimpleNamespace(event_id=valid_event_id, first_contradiction_at=None),
            ]
        ),
        _Result(
            [
                SimpleNamespace(event_id=valid_event_id, first_contradiction_at=now),
            ]
        ),
        _Result(
            [
                SimpleNamespace(target_id=extra_event_id, action="invalidate", created_at=now),
            ]
        ),
    ]

    empty_after_filter = await generator._load_contradiction_analytics(
        trend_id=uuid4(),
        period_start=now - timedelta(days=7),
        period_end=now,
    )
    missing_resolution_delta = await generator._load_contradiction_analytics(
        trend_id=uuid4(),
        period_start=now - timedelta(days=7),
        period_end=now,
    )

    assert empty_after_filter["contradicted_events_count"] == 0
    assert missing_resolution_delta["contradicted_events_count"] == 1
    assert missing_resolution_delta["resolved_events_count"] == 1
    assert missing_resolution_delta["avg_resolution_time_hours"] is None


def test_build_narrative_payload_content_truncates_large_payload(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    monkeypatch.setattr(generator, "_MAX_NARRATIVE_INPUT_TOKENS", 10)
    payload_content = generator._build_narrative_payload_content(
        {"text": "x " * 800},
        report_type="weekly",
    )

    assert payload_content.startswith("<UNTRUSTED_REPORT_PAYLOAD>")
    assert payload_content.endswith("</UNTRUSTED_REPORT_PAYLOAD>")
    assert "[TRUNCATED]" in payload_content


@pytest.mark.asyncio
async def test_generate_weekly_reports_persists_grounding_metadata(mock_db_session) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    trend_id = uuid4()
    trend = SimpleNamespace(
        id=trend_id,
        name="Signal Watch",
        description="desc",
        runtime_trend_id="signal-watch",
        definition={"id": "signal-watch"},
    )

    generator._load_active_trends = AsyncMock(return_value=[trend])
    generator._build_weekly_statistics = AsyncMock(
        return_value={
            "current_probability": 0.42,
            "weekly_change": 0.05,
            "direction": "rising",
            "evidence_count_weekly": 4,
        }
    )
    generator._load_top_events = AsyncMock(return_value=[])
    generator._build_narrative = AsyncMock(
        return_value=NarrativeResult(
            narrative="Grounded narrative",
            grounding_status="grounded",
            grounding_violation_count=0,
            grounding_references=None,
        )
    )
    generator._find_existing_report = AsyncMock(return_value=None)

    run = await generator.generate_weekly_reports()

    assert run.created == 1
    persisted = mock_db_session.add.call_args.args[0]
    assert persisted.narrative == "Grounded narrative"
    assert persisted.grounding_status == "grounded"
    assert persisted.grounding_violation_count == 0
    assert persisted.grounding_references is None
    assert persisted.generation_manifest["report_type"] == "weekly"
    assert persisted.generation_manifest["trend"]["runtime_trend_id"] == "signal-watch"
    assert persisted.generation_manifest["artifact_status"]["provisional"] is False
