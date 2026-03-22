from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import src.processing.event_clusterer as event_clusterer_module
import src.processing.tier2_classifier as tier2_module
from src.core.trend_config_loader import load_trends_from_config_dir
from src.processing.event_clusterer import EventClusterer
from src.processing.tier2_classifier import Tier2Classifier
from src.storage.models import Event, RawItem

pytestmark = pytest.mark.unit


def _build_cost_tracker() -> SimpleNamespace:
    return SimpleNamespace(
        ensure_within_budget=AsyncMock(return_value=None),
        record_usage=AsyncMock(return_value=None),
    )


def _build_classifier(mock_db_session, **kwargs) -> Tier2Classifier:
    return Tier2Classifier(
        session=mock_db_session,
        client=kwargs.pop("client", SimpleNamespace()),
        cost_tracker=kwargs.pop("cost_tracker", _build_cost_tracker()),
        semantic_cache=kwargs.pop(
            "semantic_cache", SimpleNamespace(get=lambda **_: None, set=lambda **_: None)
        ),
        **kwargs,
    )


def _build_trend(
    *, trend_id: str = "eu-russia", definition: dict[str, object] | None = None, indicators=None
):
    return SimpleNamespace(
        id=uuid4(),
        name="Trend",
        runtime_trend_id=trend_id,
        definition={"id": trend_id} if definition is None else definition,
        indicators=(
            {
                "military_movement": {
                    "direction": "escalatory",
                    "description": "Force repositioning",
                    "keywords": [" troops ", "troops", "", 1],
                }
            }
            if indicators is None
            else indicators
        ),
    )


def test_create_client_validates_key_and_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    client_factory = MagicMock(side_effect=lambda **kwargs: kwargs)
    monkeypatch.setattr(tier2_module, "AsyncOpenAI", client_factory)

    with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
        Tier2Classifier._create_client(api_key="", base_url=None)

    with_base_url = Tier2Classifier._create_client(
        api_key="stub",  # pragma: allowlist secret
        base_url=" https://api.example ",
    )
    without_base_url = Tier2Classifier._create_client(
        api_key="stub",  # pragma: allowlist secret
        base_url=" ",
    )

    assert with_base_url == {
        "api_key": "stub",  # pragma: allowlist secret
        "base_url": "https://api.example",
    }
    assert without_base_url == {"api_key": "stub"}  # pragma: allowlist secret


def test_build_secondary_client_covers_all_paths(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    classifier = _build_classifier(mock_db_session, secondary_model=None)
    assert classifier._build_secondary_client(secondary_client=None) is None

    supplied = object()
    classifier.secondary_model = "secondary"
    assert classifier._build_secondary_client(secondary_client=supplied) is supplied

    monkeypatch.setattr(tier2_module.settings, "LLM_SECONDARY_API_KEY", "")
    monkeypatch.setattr(tier2_module.settings, "OPENAI_API_KEY", "")
    with pytest.raises(ValueError, match="without API key"):
        classifier._build_secondary_client(secondary_client=None)

    monkeypatch.setattr(tier2_module.settings, "OPENAI_API_KEY", "primary")
    monkeypatch.setattr(tier2_module.settings, "LLM_SECONDARY_API_KEY", "secondary")
    classifier.secondary_base_url = "https://secondary.example"
    classifier._create_client = MagicMock(return_value="secondary-client")

    assert classifier._build_secondary_client(secondary_client=None) == "secondary-client"
    classifier._create_client.assert_called_once_with(
        api_key="secondary",  # pragma: allowlist secret
        base_url="https://secondary.example",
    )


@pytest.mark.asyncio
async def test_classify_events_handles_empty_and_missing_trends(mock_db_session) -> None:
    classifier = _build_classifier(mock_db_session)
    mock_db_session.scalars.return_value = SimpleNamespace(all=list)

    result = await classifier.classify_events(limit=5, trends=[_build_trend()])
    assert result.scanned == 0
    assert result.classified == 0

    event = Event(id=uuid4(), canonical_summary="summary")
    mock_db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [event]),
        SimpleNamespace(all=list),
    ]
    with pytest.raises(ValueError, match="No active trends"):
        await classifier.classify_events(limit=5, trends=None)


@pytest.mark.asyncio
async def test_classify_events_aggregates_usage_metadata(mock_db_session) -> None:
    classifier = _build_classifier(mock_db_session)
    first_event = Event(id=uuid4(), canonical_summary="one")
    second_event = Event(id=uuid4(), canonical_summary="two")
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [first_event, second_event])
    classifier._load_event_context = AsyncMock(return_value=["context"])
    classifier.classify_event = AsyncMock(
        side_effect=[
            (
                tier2_module.Tier2EventResult(
                    event_id=first_event.id, categories_count=1, trend_impacts_count=1
                ),
                tier2_module.Tier2Usage(
                    prompt_tokens=2,
                    completion_tokens=3,
                    api_calls=1,
                    estimated_cost_usd=0.1,
                    active_provider="provider-a",
                ),
            ),
            (
                tier2_module.Tier2EventResult(
                    event_id=second_event.id, categories_count=1, trend_impacts_count=1
                ),
                tier2_module.Tier2Usage(
                    prompt_tokens=5,
                    completion_tokens=7,
                    api_calls=1,
                    estimated_cost_usd=0.2,
                    active_provider="provider-b",
                    active_model="model-b",
                    active_reasoning_effort="low",
                ),
            ),
        ]
    )

    result = await classifier.classify_events(limit=5, trends=[_build_trend()])

    assert result.classified == 2
    assert result.usage.prompt_tokens == 7
    assert result.usage.completion_tokens == 10
    assert result.usage.active_provider == "provider-b"
    assert result.usage.active_model == "model-b"
    assert result.usage.active_reasoning_effort == "low"


@pytest.mark.asyncio
async def test_classify_event_validates_event_id_and_trends(mock_db_session) -> None:
    classifier = _build_classifier(mock_db_session)

    with pytest.raises(ValueError, match="must have an id"):
        await classifier.classify_event(
            event=Event(id=None, canonical_summary="summary"),
            trends=[_build_trend()],
            context_chunks=["context"],
        )

    with pytest.raises(ValueError, match="At least one trend"):
        await classifier.classify_event(
            event=Event(id=uuid4(), canonical_summary="summary"),
            trends=[],
            context_chunks=["context"],
        )


@pytest.mark.asyncio
async def test_load_event_context_skips_empty_and_truncates_long_chunks(mock_db_session) -> None:
    classifier = _build_classifier(mock_db_session)
    mock_db_session.execute.return_value = SimpleNamespace(
        all=lambda: [
            ("Title", "content"),
            ("", ""),
            ("Long", "x" * 3000),
        ]
    )

    chunks = await classifier._load_event_context(uuid4(), max_items=3)

    assert chunks[0] == "Title\n\ncontent"
    assert chunks[1].startswith("Long\n\n")
    assert chunks[1].endswith("...")
    assert len(chunks) == 2


def test_build_payload_budget_behaviour_without_taxonomy_context(
    mock_db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    classifier = _build_classifier(mock_db_session)
    classifier._MAX_REQUEST_INPUT_TOKENS = 220
    classifier._PAYLOAD_HEADROOM_TOKENS = 0
    classifier._MIN_CONTEXT_CHUNK_TOKENS = 1
    event = Event(id=uuid4(), canonical_summary="summary")
    original_estimate = classifier._estimate_payload_tokens

    payload = classifier._build_payload(
        event=event,
        trends=[_build_trend()],
        context_chunks=["first chunk", "second chunk"],
    )

    assert "trends" not in payload
    assert len(payload["context_chunks"]) == 2
    assert payload["context_chunks"][0].startswith("<UNTRUSTED_EVENT_CONTEXT>")
    assert original_estimate(payload) <= classifier._MAX_REQUEST_INPUT_TOKENS

    classifier._MAX_REQUEST_INPUT_TOKENS = 80
    payload = classifier._build_payload(
        event=event, trends=[_build_trend()], context_chunks=["   "]
    )
    assert "[TRUNCATED]" in payload["context_chunks"][0]

    payload = {"context_chunks": "bad"}
    classifier._enforce_payload_budget(payload)
    assert payload == {"context_chunks": "bad"}

    payload = {"context_chunks": ["one", "two"]}

    estimates = iter([999, 999, 999, 1])
    monkeypatch.setattr(classifier, "_estimate_payload_tokens", lambda _payload: next(estimates))
    classifier._enforce_payload_budget(payload)
    assert payload["context_chunks"] == ["one"]


def test_build_payload_raises_when_wrapped_context_pushes_payload_over_budget(
    mock_db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    classifier = _build_classifier(mock_db_session)
    event = Event(id=uuid4(), canonical_summary="summary")
    trend = _build_trend()
    estimates = iter([1, classifier._MAX_REQUEST_INPUT_TOKENS + 1])
    monkeypatch.setattr(classifier, "_estimate_payload_tokens", lambda _payload: next(estimates))

    with pytest.raises(ValueError, match="exceeds safe input budget"):
        classifier._build_payload(
            event=event,
            trends=[trend],
            context_chunks=["context"],
        )


def test_enforce_payload_budget_raises_when_truncation_still_cannot_fit(
    mock_db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    classifier = _build_classifier(mock_db_session)
    classifier._MAX_REQUEST_INPUT_TOKENS = 10
    classifier._PAYLOAD_HEADROOM_TOKENS = 0
    payload = {"context_chunks": ["one", "two"]}
    estimates = iter([999, 999, 999, 999])
    monkeypatch.setattr(classifier, "_estimate_payload_tokens", lambda _payload: next(estimates))

    with pytest.raises(ValueError, match="exceeds safe input budget"):
        classifier._enforce_payload_budget(payload)


def test_enforce_payload_budget_returns_when_context_chunks_is_not_a_list(
    mock_db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    classifier = _build_classifier(mock_db_session)
    classifier._MAX_REQUEST_INPUT_TOKENS = 10
    classifier._PAYLOAD_HEADROOM_TOKENS = 0
    payload = {"context_chunks": "bad"}
    monkeypatch.setattr(classifier, "_estimate_payload_tokens", lambda _payload: 999)

    classifier._enforce_payload_budget(payload)

    assert payload["context_chunks"] == "bad"


def test_build_payload_current_taxonomy_stays_within_safe_budget(mock_db_session) -> None:
    classifier = _build_classifier(mock_db_session)
    trends = load_trends_from_config_dir(config_dir=Path("config/trends"))
    event = Event(
        id=uuid4(),
        canonical_summary="Representative summary covering a plausible geopolitical development.",
    )
    payload = classifier._build_payload(
        event=event,
        trends=trends,
        context_chunks=[" ".join(["Representative context sentence."] * 200)],
    )

    assert classifier._estimate_payload_tokens(payload) <= classifier._MAX_REQUEST_INPUT_TOKENS
    assert "trends" not in payload


def test_parse_output_and_alignment_guard_invalid_responses(mock_db_session) -> None:
    classifier = _build_classifier(mock_db_session)

    with pytest.raises(ValueError, match="missing choices"):
        classifier._parse_output(SimpleNamespace(choices=[]))

    with pytest.raises(ValueError, match="missing message content"):
        classifier._parse_output(
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=" "))])
        )

    with pytest.raises(ValueError, match="not valid JSON"):
        classifier._parse_output(
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{bad"))])
        )

    output = tier2_module._Tier2Output.model_validate(
        {
            "summary": "summary",
            "extracted_who": [],
            "extracted_what": "   ",
            "extracted_where": None,
            "extracted_when": None,
            "claims": [],
            "categories": [],
            "has_contradictions": False,
            "contradiction_notes": None,
        }
    )
    with pytest.raises(ValueError, match="extracted_what or at least one claim"):
        classifier._validate_output_alignment(output, trends=[_build_trend()])
    with pytest.raises(ValueError, match="At least one trend"):
        classifier._validate_output_alignment(output, trends=[])


def test_apply_output_and_claim_helpers_cover_fallbacks(mock_db_session) -> None:
    classifier = _build_classifier(mock_db_session)
    event = Event(id=uuid4(), canonical_summary="summary")
    output = tier2_module._Tier2Output.model_validate(
        {
            "summary": " updated summary ",
            "extracted_who": [" NATO ", "NATO", ""],
            "extracted_what": " activity ",
            "extracted_where": "  ",
            "extracted_when": "2026-02-07T12:00:00",
            "claims": ["A", "A", "B"],
            "categories": [" military ", "military", ""],
            "has_contradictions": True,
            "contradiction_notes": " ",
        }
    )

    classifier._apply_output(event=event, output=output, trends=[_build_trend()])

    assert event.canonical_summary == "summary"
    assert event.event_summary == "updated summary"
    assert event.extracted_who == ["NATO"]
    assert event.extracted_where == ""
    assert event.extracted_when == datetime(2026, 2, 7, 12, 0, tzinfo=UTC)
    assert event.categories == ["military"]
    assert event.contradiction_notes == "Potential contradiction detected across source claims."
    assert event.extracted_claims["trend_impacts"] == []
    assert classifier._dedupe_strings([" a ", "a", "b", ""]) == ["a", "b"]
    assert classifier._claim_relation("Alpha moved", "Beta stayed") is None
    assert (
        classifier._claim_relation("Forces crossed border", "Forces did not cross border")
        == "contradict"
    )
    assert (
        classifier._claim_relation("Forces crossed border", "Forces crossed border yesterday")
        == "support"
    )
    assert classifier._claim_tokens("the forces crossed border", language="en") == {
        "forces",
        "crossed",
        "border",
    }


@pytest.mark.asyncio
async def test_classify_event_preserves_primary_item_summary_after_cluster_merge(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clusterer = EventClusterer(session=mock_db_session)
    event = Event(
        id=uuid4(),
        canonical_summary="Primary source title",
        source_count=1,
        unique_source_count=1,
        primary_item_id=uuid4(),
    )
    merged_item = RawItem(
        id=uuid4(),
        source_id=uuid4(),
        external_id=f"item-{uuid4()}",
        title="Later lower-credibility mention",
        raw_content="Follow-up report body",
        content_hash="b" * 64,
    )

    clusterer._update_primary_item = AsyncMock(return_value=False)
    clusterer._count_unique_sources = AsyncMock(return_value=2)
    clusterer._refresh_event_provenance = AsyncMock()
    clusterer.lifecycle_manager = SimpleNamespace(on_event_mention=lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        event_clusterer_module,
        "resolve_cluster_health",
        AsyncMock(
            return_value={
                "cluster_cohesion_score": 0.8,
                "split_risk_score": 0.2,
            }
        ),
    )

    await clusterer._merge_into_event(event, merged_item)

    class _ChatCompletions:
        async def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=(
                                '{"summary":"Synthesized event summary. Secondary sentence.",'
                                '"extracted_who":["NATO"],'
                                '"extracted_what":"Troop movement near the border",'
                                '"extracted_where":"Baltic region",'
                                '"extracted_when":"2026-02-07T12:00:00Z",'
                                '"claims":["Troop deployment increased near the border."],'
                                '"categories":["military"],'
                                '"has_contradictions":false,'
                                '"contradiction_notes":null}'
                            )
                        )
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10),
            )

    classifier = _build_classifier(
        mock_db_session,
        client=SimpleNamespace(chat=SimpleNamespace(completions=_ChatCompletions())),
    )
    result, _usage = await classifier.classify_event(
        event=event,
        trends=[_build_trend()],
        context_chunks=["Context paragraph"],
    )

    assert result.event_id == event.id
    assert event.canonical_summary == "Primary source title"
    assert event.event_summary == "Synthesized event summary. Secondary sentence."
    assert event.extracted_what == "Troop movement near the border"


def test_build_payload_prefers_persisted_event_summary(mock_db_session) -> None:
    classifier = _build_classifier(mock_db_session)
    event = Event(
        id=uuid4(),
        canonical_summary="Primary item title",
        event_summary="Synthesized event summary",
    )

    payload = classifier._build_payload(
        event=event,
        trends=[_build_trend()],
        context_chunks=["Context paragraph"],
    )

    assert payload["summary"] == "Synthesized event summary"
    long_claim = ("forces crossed border repeatedly near northern checkpoint " * 8).strip()
    assert "checkpoint" in classifier._claim_tokens(long_claim, language="en")
    assert classifier._claim_polarity("forces did not cross", language="en") == "negative"
    assert classifier._claim_language("plain ascii") == "en"
    assert classifier._claim_language("текст") == "ru"
    assert classifier._claim_language("текст ї") == "uk"
    assert classifier._claim_language("текст ы") == "ru"
    assert classifier._claim_language("é") == "unknown"
    assert classifier._parse_datetime(None) is None
    assert classifier._parse_datetime(" ") is None
    aware = classifier._parse_datetime("2026-02-07T12:00:00Z")
    assert aware == datetime(2026, 2, 7, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_classify_event_ignores_invalid_cached_content_and_skips_cache_store_without_content(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    classifier = _build_classifier(
        mock_db_session,
        client=SimpleNamespace(),
        semantic_cache=SimpleNamespace(get=lambda **_: "{bad", set=MagicMock()),
    )
    event = Event(id=uuid4(), canonical_summary="summary")
    trends = [_build_trend()]
    invocation = SimpleNamespace(
        response=SimpleNamespace(choices="bad"),
        prompt_tokens=3,
        completion_tokens=4,
        estimated_cost_usd=0.01,
        active_provider="openai",
        active_model="model",
        active_reasoning_effort="medium",
        used_secondary_route=False,
    )
    parsed_output = tier2_module._Tier2Output.model_validate(
        {
            "summary": "summary",
            "extracted_who": [],
            "extracted_what": "what",
            "extracted_where": None,
            "extracted_when": None,
            "claims": [],
            "categories": [],
            "has_contradictions": False,
            "contradiction_notes": None,
        }
    )

    monkeypatch.setattr(tier2_module, "invoke_with_policy", AsyncMock(return_value=invocation))
    monkeypatch.setattr(classifier, "_parse_output", lambda _response: parsed_output)

    result, usage = await classifier.classify_event(
        event=event,
        trends=trends,
        context_chunks=["context"],
    )

    assert result.event_id == event.id
    assert usage.prompt_tokens == 3
    classifier.semantic_cache.set.assert_not_called()

    invocation.response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="   "))]
    )
    await classifier.classify_event(
        event=event,
        trends=trends,
        context_chunks=["context"],
    )
    classifier.semantic_cache.set.assert_not_called()
