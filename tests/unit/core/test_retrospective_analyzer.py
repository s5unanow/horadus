from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.retrospective_analyzer import NarrativeResult, RetrospectiveAnalyzer
from src.processing.cost_tracker import TIER2, BudgetExceededError

pytestmark = pytest.mark.unit


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def test_fallback_narrative_reports_sparse_coverage() -> None:
    narrative = RetrospectiveAnalyzer._fallback_narrative(
        trend_name="EU-Russia Escalation",
        pivotal_events=[{"event_id": "e1"}],
        predictive_signals=[{"signal_type": "military_movement"}],
        accuracy_assessment={
            "mean_brier_score": 0.22,
            "resolved_rate": 0.25,
        },
    )

    assert "military_movement" in narrative
    assert "25%" in narrative
    assert "Confidence is low" in narrative


def test_fallback_narrative_reports_moderate_coverage() -> None:
    narrative = RetrospectiveAnalyzer._fallback_narrative(
        trend_name="EU-Russia Escalation",
        pivotal_events=[{"event_id": "e1"}, {"event_id": "e2"}],
        predictive_signals=[],
        accuracy_assessment={
            "mean_brier_score": None,
            "resolved_rate": 0.8,
        },
    )

    assert "'none'" in narrative
    assert "80%" in narrative
    assert "Confidence is moderate" in narrative


def test_fallback_narrative_reports_unknown_coverage() -> None:
    narrative = RetrospectiveAnalyzer._fallback_narrative(
        trend_name="EU-Russia Escalation",
        pivotal_events=[],
        predictive_signals=[],
        accuracy_assessment={
            "mean_brier_score": None,
            "resolved_rate": "unknown",
        },
    )

    assert "resolved coverage at unknown" in narrative
    assert "Conclusions should be treated as provisional" in narrative


def test_retrospective_prompt_contract_requires_grounded_provisional_language() -> None:
    prompt = Path("ai/prompts/retrospective_analysis.md").read_text(encoding="utf-8")

    assert (
        "Every narrative claim must be directly supported by the provided structured payload"
        in prompt
    )
    assert "explicitly framed as uncertainty/inference" in prompt
    assert "Do not add unsupported causal explanations, locations, or confidence claims" in prompt
    assert "keep the narrative explicitly provisional" in prompt


@pytest.mark.asyncio
async def test_build_narrative_uses_fallback_when_budget_denied(mock_db_session) -> None:
    create_mock = AsyncMock()
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock)))
    analyzer = RetrospectiveAnalyzer(
        session=mock_db_session,
        client=client,
        cost_tracker=SimpleNamespace(
            ensure_within_budget=AsyncMock(side_effect=BudgetExceededError("budget denied")),
            record_usage=AsyncMock(return_value=None),
        ),
    )
    trend = SimpleNamespace(id=uuid4(), name="EU-Russia Escalation", description="desc")

    result = await analyzer._build_narrative(
        trend=trend,
        period_start=datetime.now(tz=UTC) - timedelta(days=7),
        period_end=datetime.now(tz=UTC),
        pivotal_events=[],
        predictive_signals=[],
        accuracy_assessment={"mean_brier_score": 0.2, "resolved_rate": 0.5},
    )

    assert "Retrospective analysis for EU-Russia Escalation" in result.narrative
    assert result.grounding_status == "fallback"
    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_narrative_uses_fallback_when_client_missing(mock_db_session) -> None:
    analyzer = RetrospectiveAnalyzer(session=mock_db_session, client=None)
    analyzer.client = None
    trend = SimpleNamespace(id=uuid4(), name="EU-Russia Escalation", description="desc")

    result = await analyzer._build_narrative(
        trend=trend,
        period_start=datetime.now(tz=UTC) - timedelta(days=7),
        period_end=datetime.now(tz=UTC),
        pivotal_events=[],
        predictive_signals=[],
        accuracy_assessment={"mean_brier_score": None, "resolved_rate": None},
    )

    assert result.grounding_status in {"fallback", "flagged"}
    assert "Retrospective analysis for EU-Russia Escalation" in result.narrative


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
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content="Retrospective narrative"))
                ],
                usage=SimpleNamespace(prompt_tokens=18, completion_tokens=7),
            )

    cost_tracker = SimpleNamespace(
        ensure_within_budget=AsyncMock(return_value=None),
        record_usage=AsyncMock(return_value=None),
    )
    analyzer = RetrospectiveAnalyzer(
        session=mock_db_session,
        client=SimpleNamespace(chat=SimpleNamespace(completions=PrimaryCompletions())),
        secondary_client=SimpleNamespace(chat=SimpleNamespace(completions=SecondaryCompletions())),
        secondary_model="gpt-4.1-nano",
        cost_tracker=cost_tracker,
        primary_provider="openai",
        secondary_provider="openai-secondary",
    )
    trend = SimpleNamespace(id=uuid4(), name="EU-Russia Escalation", description="desc")

    result = await analyzer._build_narrative(
        trend=trend,
        period_start=datetime.now(tz=UTC) - timedelta(days=7),
        period_end=datetime.now(tz=UTC),
        pivotal_events=[],
        predictive_signals=[],
        accuracy_assessment={"mean_brier_score": 0.2, "resolved_rate": 0.5},
    )

    assert result.narrative == "Retrospective narrative"
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
        input_tokens=18,
        output_tokens=7,
        provider="openai-secondary",
        model="gpt-4.1-nano",
    )


@pytest.mark.asyncio
async def test_build_narrative_uses_fallback_when_grounding_fails(mock_db_session) -> None:
    class CompletionsApi:
        async def create(self, **kwargs):
            _ = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="Resolved coverage reached 95%.")
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=8, completion_tokens=4),
            )

    analyzer = RetrospectiveAnalyzer(
        session=mock_db_session,
        client=SimpleNamespace(chat=SimpleNamespace(completions=CompletionsApi())),
        cost_tracker=SimpleNamespace(
            ensure_within_budget=AsyncMock(return_value=None),
            record_usage=AsyncMock(return_value=None),
        ),
    )
    trend = SimpleNamespace(id=uuid4(), name="EU-Russia Escalation", description="desc")

    result = await analyzer._build_narrative(
        trend=trend,
        period_start=datetime.now(tz=UTC) - timedelta(days=7),
        period_end=datetime.now(tz=UTC),
        pivotal_events=[],
        predictive_signals=[],
        accuracy_assessment={"mean_brier_score": 0.2, "resolved_rate": 0.5},
    )

    assert result.grounding_status == "fallback"
    assert "Retrospective analysis for EU-Russia Escalation" in result.narrative


@pytest.mark.asyncio
async def test_build_narrative_uses_fallback_when_model_returns_blank_content(
    mock_db_session,
) -> None:
    class CompletionsApi:
        async def create(self, **kwargs):
            _ = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="   "))],
                usage=SimpleNamespace(prompt_tokens=8, completion_tokens=4),
            )

    analyzer = RetrospectiveAnalyzer(
        session=mock_db_session,
        client=SimpleNamespace(chat=SimpleNamespace(completions=CompletionsApi())),
        cost_tracker=SimpleNamespace(
            ensure_within_budget=AsyncMock(return_value=None),
            record_usage=AsyncMock(return_value=None),
        ),
    )
    trend = SimpleNamespace(id=uuid4(), name="EU-Russia Escalation", description="desc")

    result = await analyzer._build_narrative(
        trend=trend,
        period_start=datetime.now(tz=UTC) - timedelta(days=7),
        period_end=datetime.now(tz=UTC),
        pivotal_events=[],
        predictive_signals=[],
        accuracy_assessment={"mean_brier_score": 0.2, "resolved_rate": 0.5},
    )

    assert result.grounding_status == "fallback"


@pytest.mark.asyncio
async def test_build_narrative_uses_fallback_when_model_raises_generic_error(
    mock_db_session,
) -> None:
    class CompletionsApi:
        async def create(self, **kwargs):
            _ = kwargs
            raise RuntimeError("boom")

    analyzer = RetrospectiveAnalyzer(
        session=mock_db_session,
        client=SimpleNamespace(chat=SimpleNamespace(completions=CompletionsApi())),
        cost_tracker=SimpleNamespace(
            ensure_within_budget=AsyncMock(return_value=None),
            record_usage=AsyncMock(return_value=None),
        ),
    )
    trend = SimpleNamespace(id=uuid4(), name="EU-Russia Escalation", description="desc")

    result = await analyzer._build_narrative(
        trend=trend,
        period_start=datetime.now(tz=UTC) - timedelta(days=7),
        period_end=datetime.now(tz=UTC),
        pivotal_events=[],
        predictive_signals=[],
        accuracy_assessment={"mean_brier_score": 0.2, "resolved_rate": 0.5},
    )

    assert result.grounding_status == "fallback"


def test_build_narrative_payload_content_truncates_large_payload(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyzer = RetrospectiveAnalyzer(session=mock_db_session, client=None)
    monkeypatch.setattr(analyzer, "_MAX_NARRATIVE_INPUT_TOKENS", 10)
    payload_content = analyzer._build_narrative_payload_content({"text": "x " * 900})

    assert payload_content.startswith("<UNTRUSTED_RETROSPECTIVE_PAYLOAD>")
    assert payload_content.endswith("</UNTRUSTED_RETROSPECTIVE_PAYLOAD>")
    assert "[TRUNCATED]" in payload_content


def test_create_client_optional_handles_empty_and_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[dict[str, str]] = []

    class FakeClient:
        def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
            created.append({"token_value": api_key, "base_url": base_url or ""})

    monkeypatch.setattr("src.core.retrospective_analyzer.AsyncOpenAI", FakeClient)

    assert RetrospectiveAnalyzer._create_client_optional(api_key="   ") is None
    client = RetrospectiveAnalyzer._create_client_optional(
        api_key="unit-test-key",  # pragma: allowlist secret
        base_url=" https://api.example.test/v1 ",
    )
    default_client = RetrospectiveAnalyzer._create_client_optional(
        api_key="unit-test-key-no-base",  # pragma: allowlist secret
    )

    assert isinstance(client, FakeClient)
    assert isinstance(default_client, FakeClient)
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


def test_build_secondary_client_handles_none_explicit_client_and_missing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyzer = RetrospectiveAnalyzer.__new__(RetrospectiveAnalyzer)
    analyzer.secondary_model = None
    analyzer.secondary_base_url = None

    assert analyzer._build_secondary_client(secondary_client=None) is None

    analyzer.secondary_model = "secondary-model"
    explicit = object()
    assert analyzer._build_secondary_client(secondary_client=explicit) is explicit

    monkeypatch.setattr(settings, "LLM_SECONDARY_API_KEY", "   ")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "   ")
    with pytest.raises(ValueError, match="without API key"):
        analyzer._build_secondary_client(secondary_client=None)


def test_build_secondary_client_constructs_from_secondary_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyzer = RetrospectiveAnalyzer.__new__(RetrospectiveAnalyzer)
    analyzer.secondary_model = "secondary-model"
    analyzer.secondary_base_url = "https://secondary.example.test/v1"
    monkeypatch.setattr(settings, "LLM_SECONDARY_API_KEY", "test-value-2")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-value-1")
    monkeypatch.setattr(
        analyzer,
        "_create_client_optional",
        lambda *, api_key, base_url=None: {"api_key": api_key, "base_url": base_url},
    )

    client = analyzer._build_secondary_client(secondary_client=None)

    assert client == {
        "api_key": "test-value-2",  # pragma: allowlist secret
        "base_url": "https://secondary.example.test/v1",
    }


def test_as_utc_normalizes_naive_and_aware_datetimes() -> None:
    naive = datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC).replace(tzinfo=None)
    aware = datetime(2026, 3, 7, 14, 0, 0, tzinfo=UTC)

    assert RetrospectiveAnalyzer._as_utc(naive).tzinfo is UTC
    assert RetrospectiveAnalyzer._as_utc(aware) == aware


@pytest.mark.asyncio
async def test_load_pivotal_events_maps_direction_and_defaults(mock_db_session) -> None:
    analyzer = RetrospectiveAnalyzer(session=mock_db_session, client=None)
    mock_db_session.execute.return_value = _Result(
        [
            (uuid4(), " rising ", ["military", ""], 2, 0.3, 0.9),
            (uuid4(), None, None, 1, -0.4, 0.4),
            (uuid4(), "steady", ["diplomatic"], 3, 0.0, 0.2),
        ]
    )

    events = await analyzer._load_pivotal_events(
        trend_id=uuid4(),
        period_start=datetime(2026, 3, 1, tzinfo=UTC),
        period_end=datetime(2026, 3, 7, tzinfo=UTC),
        limit=3,
    )

    assert events[0]["summary"] == "rising"
    assert events[0]["direction"] == "up"
    assert events[1]["direction"] == "down"
    assert events[1]["categories"] == []
    assert events[2]["direction"] == "mixed"


def test_category_breakdown_from_events_ignores_invalid_categories() -> None:
    counts = RetrospectiveAnalyzer._category_breakdown_from_events(
        [
            {"categories": ["military", "diplomatic", " "]},
            {"categories": ["military"]},
            {"categories": "not-a-list"},
        ]
    )

    assert counts == {"military": 2, "diplomatic": 1}


@pytest.mark.asyncio
async def test_load_predictive_signals_rounds_values(mock_db_session) -> None:
    analyzer = RetrospectiveAnalyzer(session=mock_db_session, client=None)
    mock_db_session.execute.return_value = _Result(
        [
            ("military_movement", 2, 0.3333333, 0.4444444),
            ("sanctions", None, None, None),
        ]
    )

    signals = await analyzer._load_predictive_signals(
        trend_id=uuid4(),
        period_start=datetime(2026, 3, 1, tzinfo=UTC),
        period_end=datetime(2026, 3, 7, tzinfo=UTC),
    )

    assert signals == [
        {
            "signal_type": "military_movement",
            "evidence_count": 2,
            "net_delta_log_odds": 0.333333,
            "abs_delta_log_odds": 0.444444,
        },
        {
            "signal_type": "sanctions",
            "evidence_count": 0,
            "net_delta_log_odds": 0.0,
            "abs_delta_log_odds": 0.0,
        },
    ]


@pytest.mark.asyncio
async def test_load_accuracy_assessment_handles_empty_and_scored_rows(mock_db_session) -> None:
    analyzer = RetrospectiveAnalyzer(session=mock_db_session, client=None)
    mock_db_session.execute.return_value = _Result([(0.2, "occurred"), (None, None)])

    assessment = await analyzer._load_accuracy_assessment(
        trend_id=uuid4(),
        period_start=datetime(2026, 3, 1, tzinfo=UTC),
        period_end=datetime(2026, 3, 7, tzinfo=UTC),
    )

    assert assessment == {
        "outcome_count": 2,
        "resolved_outcomes": 1,
        "scored_outcomes": 1,
        "mean_brier_score": 0.2,
        "resolved_rate": 0.5,
    }

    mock_db_session.execute.return_value = _Result([])
    empty = await analyzer._load_accuracy_assessment(
        trend_id=uuid4(),
        period_start=datetime(2026, 3, 1, tzinfo=UTC),
        period_end=datetime(2026, 3, 7, tzinfo=UTC),
    )

    assert empty["mean_brier_score"] is None
    assert empty["resolved_rate"] is None


@pytest.mark.asyncio
async def test_analyze_requires_trend_id(mock_db_session) -> None:
    analyzer = RetrospectiveAnalyzer(session=mock_db_session, client=None)

    with pytest.raises(ValueError, match="Trend id is required"):
        await analyzer.analyze(
            trend=SimpleNamespace(id=None, name="Trend"),
            start_date=datetime(2026, 3, 1, tzinfo=UTC),
            end_date=datetime(2026, 3, 7, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_analyze_assembles_report_from_loaded_sections(mock_db_session) -> None:
    analyzer = RetrospectiveAnalyzer(session=mock_db_session, client=None)
    trend_id = uuid4()
    trend = SimpleNamespace(id=trend_id, name="Trend", description="desc")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        analyzer,
        "_load_pivotal_events",
        AsyncMock(return_value=[{"event_id": "e1"}]),
    )
    monkeypatch.setattr(
        analyzer,
        "_category_breakdown_from_events",
        lambda events: {"military": len(events)},
    )
    monkeypatch.setattr(
        analyzer,
        "_load_predictive_signals",
        AsyncMock(return_value=[{"signal_type": "military_movement"}]),
    )
    monkeypatch.setattr(
        analyzer,
        "_load_accuracy_assessment",
        AsyncMock(return_value={"mean_brier_score": 0.2}),
    )
    monkeypatch.setattr(
        analyzer,
        "_build_narrative",
        AsyncMock(
            return_value=NarrativeResult(
                narrative="Narrative",
                grounding_status="grounded",
                grounding_violation_count=0,
                grounding_references={"supported_claims": []},
            )
        ),
    )

    result = await analyzer.analyze(
        trend=trend,
        start_date=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC).replace(tzinfo=None),
        end_date=datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC).replace(tzinfo=None),
    )

    monkeypatch.undo()

    assert result["trend_id"] == trend_id
    assert result["trend_name"] == "Trend"
    assert result["category_breakdown"] == {"military": 1}
    assert result["predictive_signals"] == [{"signal_type": "military_movement"}]
    assert result["narrative"] == "Narrative"
    assert result["grounding_status"] == "grounded"
