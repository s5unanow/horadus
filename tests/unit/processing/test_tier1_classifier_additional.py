from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import src.processing.tier1_classifier as tier1_module
from src.processing.tier1_classifier import Tier1Classifier
from src.storage.models import ProcessingStatus, RawItem

pytestmark = pytest.mark.unit


def _build_cost_tracker() -> SimpleNamespace:
    return SimpleNamespace(
        ensure_within_budget=AsyncMock(return_value=None),
        record_usage=AsyncMock(return_value=None),
    )


def _build_classifier(mock_db_session, **kwargs) -> Tier1Classifier:
    return Tier1Classifier(
        session=mock_db_session,
        client=kwargs.pop("client", SimpleNamespace()),
        cost_tracker=kwargs.pop("cost_tracker", _build_cost_tracker()),
        semantic_cache=kwargs.pop(
            "semantic_cache", SimpleNamespace(get=lambda **_: None, set=lambda **_: None)
        ),
        **kwargs,
    )


def _build_item(*, title: str = "title", raw_content: str = "content", item_id=None) -> RawItem:
    return RawItem(
        id=item_id if item_id is not None else uuid4(),
        source_id=uuid4(),
        external_id=f"item-{uuid4()}",
        title=title,
        raw_content=raw_content,
        content_hash="a" * 64,
        processing_status=ProcessingStatus.PENDING,
    )


def _build_trend(
    *, trend_id: str = "eu-russia", definition: dict[str, object] | None = None, indicators=None
):
    return SimpleNamespace(
        id=uuid4(),
        name="Trend",
        definition={"id": trend_id} if definition is None else definition,
        indicators={"signal": {"keywords": [trend_id, "shared"]}}
        if indicators is None
        else indicators,
    )


def test_create_client_validates_key_and_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    client_factory = MagicMock(side_effect=lambda **kwargs: kwargs)
    monkeypatch.setattr(tier1_module, "AsyncOpenAI", client_factory)

    with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
        Tier1Classifier._create_client(api_key="", base_url=None)

    with_base_url = Tier1Classifier._create_client(
        api_key="stub",  # pragma: allowlist secret
        base_url=" https://api.example ",
    )
    without_base_url = Tier1Classifier._create_client(
        api_key="stub",  # pragma: allowlist secret
        base_url="   ",
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

    monkeypatch.setattr(tier1_module.settings, "LLM_SECONDARY_API_KEY", "")
    monkeypatch.setattr(tier1_module.settings, "OPENAI_API_KEY", "")
    with pytest.raises(ValueError, match="without API key"):
        classifier._build_secondary_client(secondary_client=None)

    monkeypatch.setattr(tier1_module.settings, "OPENAI_API_KEY", "primary")
    monkeypatch.setattr(tier1_module.settings, "LLM_SECONDARY_API_KEY", "secondary")
    classifier.secondary_base_url = "https://secondary.example"
    classifier._create_client = MagicMock(return_value="secondary-client")

    assert classifier._build_secondary_client(secondary_client=None) == "secondary-client"
    classifier._create_client.assert_called_once_with(
        api_key="secondary",  # pragma: allowlist secret
        base_url="https://secondary.example",
    )


@pytest.mark.asyncio
async def test_classify_pending_items_returns_empty_when_no_items(mock_db_session) -> None:
    classifier = _build_classifier(mock_db_session)
    mock_db_session.scalars.return_value = SimpleNamespace(all=list)

    result = await classifier.classify_pending_items(limit=5, trends=[_build_trend()])

    assert result.scanned == 0
    assert result.queued_count == 0
    assert result.noise_count == 0


@pytest.mark.asyncio
async def test_classify_pending_items_raises_when_output_missing_item(mock_db_session) -> None:
    classifier = _build_classifier(mock_db_session)
    item = _build_item()
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [item])
    classifier.classify_items = AsyncMock(return_value=([], tier1_module.Tier1Usage()))

    with pytest.raises(ValueError, match="missing item id"):
        await classifier.classify_pending_items(limit=5, trends=[_build_trend()])


@pytest.mark.asyncio
async def test_classify_items_handles_empty_and_missing_trends(mock_db_session) -> None:
    classifier = _build_classifier(mock_db_session)

    results, usage = await classifier.classify_items([], [_build_trend()])
    assert results == []
    assert usage == tier1_module.Tier1Usage()

    with pytest.raises(ValueError, match="At least one trend"):
        await classifier.classify_items([_build_item()], [])


def test_item_payload_requires_id_and_trend_payload_filters_keywords(mock_db_session) -> None:
    classifier = _build_classifier(mock_db_session)
    missing_id_item = RawItem(
        id=None,
        source_id=uuid4(),
        external_id=f"item-{uuid4()}",
        title="title",
        raw_content="content",
        content_hash="a" * 64,
        processing_status=ProcessingStatus.PENDING,
    )

    with pytest.raises(ValueError, match="must have an id"):
        classifier._item_payload(missing_id_item)

    trend = _build_trend(
        definition={},
        indicators={
            "one": {"keywords": [" alpha ", "alpha", "", 1]},
            "two": {"keywords": "bad"},
            "three": "bad",
        },
    )
    payload = classifier._trend_payload(trend)

    assert payload["trend_id"] == str(trend.id)
    assert payload["keywords"] == ["alpha"]


def test_parse_output_and_alignment_validation_guard_invalid_responses(mock_db_session) -> None:
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

    output = tier1_module._Tier1Output.model_validate(
        {
            "items": [
                {
                    "item_id": str(uuid4()),
                    "trend_scores": [
                        {"trend_id": "eu-russia", "relevance_score": 4, "rationale": "a"},
                        {"trend_id": "eu-russia", "relevance_score": 3, "rationale": "b"},
                    ],
                }
            ]
        }
    )
    item = _build_item()
    trend = _build_trend()
    with pytest.raises(ValueError, match="item ids do not match"):
        classifier._validate_output_alignment(output, items=[item], trends=[trend])

    output = tier1_module._Tier1Output.model_validate(
        {
            "items": [
                {
                    "item_id": str(item.id),
                    "trend_scores": [
                        {"trend_id": "eu-russia", "relevance_score": 4, "rationale": "a"},
                        {"trend_id": "eu-russia", "relevance_score": 3, "rationale": "b"},
                    ],
                }
            ]
        }
    )
    with pytest.raises(ValueError, match="duplicate trend id"):
        classifier._validate_output_alignment(output, items=[item], trends=[trend])


def test_to_item_results_and_parse_json_success(mock_db_session) -> None:
    classifier = _build_classifier(mock_db_session)
    item_id = uuid4()
    raw_payload = {
        "items": [
            {
                "item_id": str(item_id),
                "trend_scores": [
                    {"trend_id": "eu-russia", "relevance_score": 6, "rationale": "match"},
                ],
            }
        ]
    }
    output = classifier._parse_output(
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(raw_payload)))]
        )
    )

    results = classifier._to_item_results(output)

    assert len(results) == 1
    assert results[0].item_id == item_id
    assert results[0].should_queue_tier2 is True


@pytest.mark.asyncio
async def test_classify_batch_ignores_invalid_cached_content_and_skips_cache_store_without_content(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    classifier = _build_classifier(
        mock_db_session,
        client=SimpleNamespace(),
        semantic_cache=SimpleNamespace(get=lambda **_: "{bad", set=MagicMock()),
    )
    item = _build_item()
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
    parsed_output = tier1_module._Tier1Output.model_validate(
        {
            "items": [
                {
                    "item_id": str(item.id),
                    "trend_scores": [
                        {"trend_id": "eu-russia", "relevance_score": 6, "rationale": "match"},
                    ],
                }
            ]
        }
    )

    monkeypatch.setattr(tier1_module, "invoke_with_policy", AsyncMock(return_value=invocation))
    monkeypatch.setattr(classifier, "_parse_output", lambda _response: parsed_output)

    results, usage = await classifier._classify_batch([item], trends)

    assert len(results) == 1
    assert usage.prompt_tokens == 3
    classifier.semantic_cache.set.assert_not_called()

    invocation.response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="   "))]
    )
    await classifier._classify_batch([item], trends)
    classifier.semantic_cache.set.assert_not_called()
