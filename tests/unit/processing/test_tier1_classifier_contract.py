from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import src.processing.tier1_classifier as tier1_module
from src.core.config import settings
from src.processing.tier1_classifier import Tier1Classifier
from src.processing.tier1_contract import (
    canonical_trend_id,
    normalize_output_payload,
    optional_text,
    strict_response_format,
    trend_list_field,
    unique_strings,
)
from src.processing.tier1_taxonomy_floor import (
    non_operational_score_cap,
    taxonomy_keyword_floors,
)
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


def _build_item(title: str, *, raw_content: str = "content") -> RawItem:
    return RawItem(
        id=uuid4(),
        source_id=uuid4(),
        external_id=f"item-{uuid4()}",
        title=title,
        raw_content=raw_content,
        content_hash="a" * 64,
        processing_status=ProcessingStatus.PENDING,
    )


def _build_trend(trend_id: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        description=f"Tracks current material developments for {name}.",
        definition={"id": trend_id},
        indicators={
            "signal": {
                "direction": "escalatory",
                "type": "leading",
                "description": f"{name} signal context",
                "keywords": [trend_id, "shared"],
            }
        },
        regions=["Global"],
        actors=[name],
    )


class _Completions:
    def __init__(self, *, item_id, trend_scores, extra_payload=None) -> None:
        self.item_id = item_id
        self.trend_scores = trend_scores
        self.extra_payload = extra_payload or {}

    async def create(self, **kwargs):
        _ = kwargs
        payload = {
            "items": [{"item_id": str(self.item_id), "trend_scores": self.trend_scores}],
            **self.extra_payload,
        }
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5),
        )


@pytest.mark.asyncio
async def test_classify_batch_deduplicates_and_ignores_unknown_trend_ids(mock_db_session) -> None:
    classifier = _build_classifier(mock_db_session, batch_size=10)
    item = _build_item("eu-russia escalation")
    trends = [_build_trend("eu-russia", "EU-Russia"), _build_trend("us-china", "US-China")]
    trend_scores = [
        {"trend_id": "eu-russia", "relevance_score": 7, "rationale": "match"},
        {"trend_id": "eu-russia", "relevance_score": 3, "rationale": "duplicate"},
        {"trend_id": "parallell-enclaves-europe", "relevance_score": 9, "rationale": "typo"},
    ]
    classifier.client = SimpleNamespace(
        chat=SimpleNamespace(completions=_Completions(item_id=item.id, trend_scores=trend_scores))
    )

    results, _usage = await classifier.classify_items([item], trends)

    assert {score.trend_id: score.relevance_score for score in results[0].trend_scores} == {
        "eu-russia": 7,
        "us-china": 0,
    }


@pytest.mark.asyncio
async def test_classify_batch_canonicalizes_alias_and_accepts_empty_scores(mock_db_session) -> None:
    classifier = _build_classifier(mock_db_session, batch_size=10)
    item = _build_item("nuclear doctrine update")
    trends = [
        _build_trend("eu-russia", "Russia-Europe Direct Conflict Escalation"),
        _build_trend("us-china", "US-China"),
    ]
    classifier.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=_Completions(
                item_id=item.id,
                trend_scores=[
                    {
                        "trend_id": "russia-european-escalation",
                        "relevance_score": 9,
                        "rationale": "alias",
                    }
                ],
            )
        )
    )

    results, _usage = await classifier.classify_items([item], trends)

    assert {score.trend_id: score.relevance_score for score in results[0].trend_scores} == {
        "eu-russia": 9,
        "us-china": 0,
    }

    classifier.client.chat.completions = _Completions(item_id=item.id, trend_scores=[])
    results, _usage = await classifier.classify_items([item], trends)

    assert results[0].max_relevance == 0


@pytest.mark.asyncio
async def test_classify_batch_normalizes_fallback_payload_and_applies_floor(
    mock_db_session,
) -> None:
    classifier = _build_classifier(mock_db_session, batch_size=10)
    item = _build_item(
        "chip controls",
        raw_content="China retaliates with rare earth controls after new chip restrictions.",
    )
    trends = [_build_trend("eu-russia", "EU-Russia"), _build_trend("us-china", "US-China")]
    trends[1].indicators["signal"]["keywords"].extend(["rare earth controls", "chip restrictions"])
    classifier.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=_Completions(
                item_id=item.id,
                trend_scores=[{"trend_id": "us-china", "relevance_score": 1}],
                extra_payload={"trend_scores": []},
            )
        )
    )

    results, _usage = await classifier.classify_items([item], trends)

    assert results[0].should_queue_tier2 is True
    assert {score.trend_id: score.relevance_score for score in results[0].trend_scores}[
        "us-china"
    ] == settings.TIER1_RELEVANCE_THRESHOLD


def test_trend_payload_includes_taxonomy_context(mock_db_session) -> None:
    classifier = _build_classifier(mock_db_session, batch_size=1)
    trend = _build_trend("eu-russia", "EU-Russia")
    trend.indicators["four"] = {"keywords": ["eu-russia", " beta "]}

    payload = classifier._trend_payload(trend)

    assert payload["description"] == "Tracks current material developments for EU-Russia."
    assert payload["regions"] == ["Global"]
    assert payload["actors"] == ["EU-Russia"]
    assert payload["keywords"] == ["eu-russia", "shared", "beta"]


def test_tier1_contract_helpers_cover_edge_branches() -> None:
    trend = _build_trend("eu-russia", "EU Russia")
    trend.description = "European escalation risk"

    assert optional_text("  text ") == "text"
    assert optional_text("   ") is None
    assert unique_strings([" a ", "a", "", 1]) == ["a"]
    assert unique_strings("bad") == []
    assert trend_list_field(trend, "regions") == ["Global"]
    assert trend_list_field(SimpleNamespace(definition={"regions": [" Europe "]}), "regions") == [
        "Europe"
    ]
    assert trend_list_field(SimpleNamespace(definition="bad"), "regions") == []
    assert (
        canonical_trend_id(
            "russia-european-escalation",
            trends=[trend],
            trend_identifier=Tier1Classifier._trend_identifier,
        )
        == "eu-russia"
    )
    assert (
        canonical_trend_id(
            "eu",
            trends=[trend],
            trend_identifier=Tier1Classifier._trend_identifier,
        )
        is None
    )
    trend_without_description = _build_trend("us-china", "US China")
    delattr(trend_without_description, "description")
    assert (
        canonical_trend_id(
            "china-us-escalation",
            trends=[trend_without_description],
            trend_identifier=Tier1Classifier._trend_identifier,
        )
        == "us-china"
    )
    assert (
        canonical_trend_id(
            123,  # type: ignore[arg-type]
            trends=[trend],
            trend_identifier=Tier1Classifier._trend_identifier,
        )
        is None
    )

    base_format = tier1_module._Tier1Output.model_json_schema()
    response_format = strict_response_format(
        {"json_schema": {"schema": base_format}},
        items=[SimpleNamespace(id="item-1")],
        trends=[trend],
        trend_identifier=Tier1Classifier._trend_identifier,
    )
    schema = response_format["json_schema"]["schema"]
    assert schema["properties"]["items"]["minItems"] == 1
    score_schema = schema["$defs"].get("_TrendScoreOutput") or schema["$defs"]["TrendScoreOutput"]
    assert score_schema["properties"]["trend_id"]["enum"] == ["eu-russia"]

    assert normalize_output_payload(["bad"]) == ["bad"]
    assert normalize_output_payload({"items": "bad"}) == {"items": "bad"}
    assert normalize_output_payload(
        {
            "items": [
                "bad",
                {"item_id": "item-1", "trend_scores": "bad"},
                {
                    "item_id": "item-2",
                    "trend_scores": [
                        "bad",
                        {"trend_scores": [{"trend_id": "eu-russia", "relevance_score": 3}]},
                    ],
                },
            ]
        }
    ) == {
        "items": [
            {"item_id": "item-1", "trend_scores": []},
            {
                "item_id": "item-2",
                "trend_scores": [{"trend_id": "eu-russia", "relevance_score": 3}],
            },
        ]
    }


def test_taxonomy_and_result_helpers_cover_edge_branches(mock_db_session) -> None:
    classifier = _build_classifier(mock_db_session)
    item = _build_item("documentary on EU Russia", raw_content="shared signal")
    trend = _build_trend("eu-russia", "EU-Russia")
    trend.indicators = {"bad": "value", "signal": {"keywords": ["abc", "shared signal"]}}
    output = tier1_module._Tier1Output.model_validate(
        {
            "items": [
                {
                    "item_id": str(item.id),
                    "trend_scores": [
                        {"trend_id": "eu-russia", "relevance_score": 9, "rationale": "high"}
                    ],
                }
            ]
        }
    )

    floors = taxonomy_keyword_floors(
        title=item.title,
        content=item.raw_content,
        trends=[trend],
        trend_identifier=Tier1Classifier._trend_identifier,
        threshold=5,
    )
    assert floors["eu-russia"][0] == 5
    assert (
        taxonomy_keyword_floors(
            title="usable signal",
            content="content",
            trends=[SimpleNamespace(indicators="bad")],
            trend_identifier=lambda _trend: "bad",
            threshold=5,
        )
        == {}
    )
    assert non_operational_score_cap(title="A documentary", content="") == 4
    assert non_operational_score_cap(title="Research finds operational risk", content="") is None
    assert (
        classifier._to_item_results(output, items=[item], trends=[trend])[0]
        .trend_scores[0]
        .relevance_score
        == 4
    )

    output.items[0].trend_scores = []
    item.title = "EU Russia"
    assert (
        classifier._to_item_results(output, items=[item], trends=[trend])[0]
        .trend_scores[0]
        .relevance_score
        == 5
    )

    duplicate_item_output = tier1_module._Tier1Output.model_validate(
        {
            "items": [
                {"item_id": str(item.id), "trend_scores": []},
                {"item_id": str(item.id), "trend_scores": []},
            ]
        }
    )
    with pytest.raises(ValueError, match="duplicate item id"):
        classifier._validate_output_alignment(duplicate_item_output, items=[item])


@pytest.mark.asyncio
async def test_classify_batch_normalizes_cached_fallback_payload(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _build_item("cached")
    cached_payload = {
        "items": [
            {
                "item_id": str(item.id),
                "trend_scores": [
                    {
                        "trend_scores": [
                            {
                                "trend_id": "eu-russia",
                                "relevance_score": 6,
                                "rationale": "cached",
                            }
                        ]
                    }
                ],
            }
        ],
        "trend_scores": [],
    }
    classifier = _build_classifier(
        mock_db_session,
        client=SimpleNamespace(),
        semantic_cache=SimpleNamespace(
            get=lambda **_: json.dumps(cached_payload),
            set=lambda **_: None,
        ),
    )
    call_mock = AsyncMock()
    monkeypatch.setattr(tier1_module, "invoke_with_policy", call_mock)
    results, usage = await classifier._classify_batch([item], [_build_trend("eu-russia", "EU")])

    assert results[0].max_relevance == 6
    assert usage == tier1_module.Tier1Usage()
    call_mock.assert_not_called()
