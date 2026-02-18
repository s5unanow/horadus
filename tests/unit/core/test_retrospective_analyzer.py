from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.retrospective_analyzer import RetrospectiveAnalyzer
from src.processing.cost_tracker import TIER2, BudgetExceededError

pytestmark = pytest.mark.unit


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
