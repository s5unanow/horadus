from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.core.trend_config_loader import load_trends_from_config_dir
from src.processing.event_claims import EventClaimSpec
from src.processing.trend_impact_mapping import (
    TREND_IMPACT_MAPPING_KEY,
    _build_impact,
    _Candidate,
    _category_matches_pair,
    _IndicatorContext,
    iter_unresolved_mapping_gaps,
    map_event_trend_impacts,
    taxonomy_gap_reason_for_mapping,
)
from src.storage.models import Event, TaxonomyGapReason

pytestmark = pytest.mark.unit

_UKRAINIAN_MOVEMENT_CLAIM = (
    "\u0420\u0443\u0445 \u0441\u0438\u043b \u0431\u0456\u043b\u044f "
    "\u043a\u043e\u0440\u0434\u043e\u043d\u0443 \u043f\u043e\u0441\u0438\u043b\u0438\u0432\u0441\u044f."
)


def _configured_trends():
    return load_trends_from_config_dir(config_dir=Path("config/trends"))


def _trend(
    *,
    trend_id: str = "eu-russia",
    indicators: dict[str, dict[str, object]] | None = None,
    actors: list[str] | None = None,
    regions: list[str] | None = None,
):
    return SimpleNamespace(
        id=uuid4(),
        name=trend_id,
        definition={
            "id": trend_id,
            "actors": actors or ["NATO", "Russia"],
            "regions": regions or ["Baltic region"],
        },
        indicators=indicators
        or {
            "military_movement": {
                "direction": "escalatory",
                "description": "Force repositioning without direct hostile contact.",
                "keywords": ["troop deployment", "deployment"],
            }
        },
    )


def test_map_event_trend_impacts_maps_keywords_deterministically() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Summary",
        extracted_who=["NATO", "Russia"],
        extracted_where="Baltic region",
        extracted_what="Troop movement near the border",
        extracted_claims={
            "claims": ["Troop deployment increased near the border."],
            "claim_graph": {
                "nodes": [
                    {
                        "claim_id": "claim_1",
                        "text": "Troop deployment increased near the border.",
                    }
                ],
                "links": [],
            },
        },
    )

    result = map_event_trend_impacts(event=event, trends=[_trend()])

    assert result.diagnostics["unresolved"] == []
    assert len(result.impacts) == 1
    assert result.impacts[0]["trend_id"] == "eu-russia"
    assert result.impacts[0]["signal_type"] == "military_movement"
    assert result.impacts[0]["event_claim_key"] == "troop deployment increased near the border"


def test_map_event_trend_impacts_prefers_exact_primary_taxonomy_category() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Diplomatic summit announced troop deployment.",
        extracted_who=["NATO", "Russia"],
        extracted_where="Baltic region",
        extracted_what="A summit announced a troop deployment near the border.",
        categories=[
            "eu-russia:military_movement:escalatory",
            42,
            "eu-russia:military_movement:escalatory",
            "eu-russia:diplomatic_talks:de_escalatory",
        ],
        extracted_claims={
            "claims": [
                "Leaders held a summit.",
                "Troop deployment increased near the border.",
            ],
            "claim_graph": {"nodes": [], "links": []},
        },
    )

    result = map_event_trend_impacts(
        event=event,
        trends=[
            _trend(),
            _trend(
                indicators={
                    "diplomatic_talks": {
                        "direction": "de_escalatory",
                        "description": "Summit or diplomatic talks.",
                        "keywords": ["summit"],
                    }
                }
            ),
        ],
    )

    assert result.impacts[0]["trend_id"] == "eu-russia"
    assert result.impacts[0]["signal_type"] == "military_movement"
    assert result.impacts[0]["direction"] == "escalatory"


def _cultivated_meat_ban_event() -> Event:
    return Event(
        id=uuid4(),
        canonical_summary="A legislature advanced a cultivated meat ban.",
        extracted_who=["state legislature", "cultivated meat producers"],
        extracted_where="United States",
        extracted_what="Lawmakers advanced a cultivated meat ban.",
        extracted_claims={
            "claims": [
                "The state legislature advanced a cultivated meat ban that would restrict sales of cell-based meat.",
            ],
            "claim_graph": {"nodes": [], "links": []},
        },
    )


def _billionaire_wealth_surge_event() -> Event:
    return Event(
        id=uuid4(),
        canonical_summary="Billionaires added record wealth while wages stagnated.",
        extracted_who=["billionaires", "workers"],
        extracted_where="major economies",
        extracted_what="Billionaires added record wealth while workers' wages stagnated.",
        extracted_claims={
            "claims": [
                "Billionaires added record wealth while workers' wages stagnated.",
            ],
            "claim_graph": {"nodes": [], "links": []},
        },
    )


@pytest.mark.parametrize(
    ("event", "expected_trend_id", "expected_signal_type", "expected_direction"),
    [
        (
            Event(
                id=uuid4(),
                canonical_summary="Trilateral patrol in the Philippine exclusive economic zone.",
                extracted_who=["United States", "Japan", "Philippines", "China"],
                extracted_where="Philippine exclusive economic zone",
                extracted_what="The United States, Japan, and the Philippines conducted a joint maritime patrol.",
                categories=["us-china:maritime_rules_of_engagement:escalatory"],
                extracted_claims={
                    "claims": [
                        "The United States, Japan, and the Philippines conducted a joint maritime patrol inside the Philippines' exclusive economic zone.",
                        "The patrol demonstrated a commitment to strengthen regional cooperation and uphold freedom of navigation.",
                    ],
                    "claim_graph": {"nodes": [], "links": []},
                },
            ),
            "us-china",
            "alliance_force_posture_upgrade",
            "escalatory",
        ),
        (
            Event(
                id=uuid4(),
                canonical_summary="Turkey and Russia resumed Astana-format Syria talks.",
                extracted_who=["Turkey", "Russia", "Iran"],
                extracted_where="northeastern Syria",
                extracted_what="Turkey and Russia agreed on continued dialogue and a joint incident prevention mechanism.",
                categories=["russia-turkey:syria_proxy_clash:de_escalatory"],
                extracted_claims={
                    "claims": [
                        "Turkey and Russia resumed Astana-format discussions on Syria's political transition.",
                        "Both Turkey and Russia committed to continued dialogue and agreed on a joint mechanism to prevent incidents between their forces.",
                    ],
                    "claim_graph": {"nodes": [], "links": []},
                },
            ),
            "russia-turkey",
            "hotline_restoration",
            "de_escalatory",
        ),
        (
            Event(
                id=uuid4(),
                canonical_summary="Argentina lowered agricultural export taxes.",
                extracted_who=["Argentine government"],
                extracted_where="Argentina",
                extracted_what="Argentina lowered export taxes and temporarily suspended export duties.",
                categories=["south-america-agri-supply-shift:export_volume_cagr_growth:escalatory"],
                extracted_claims={
                    "claims": [
                        "The Argentine government permanently lowered soybean export taxes from 33% to 26%.",
                        "Argentina temporarily suspended export duties on grains and oilseeds.",
                        "The tax changes boosted Argentina's soybean export competitiveness.",
                    ],
                    "claim_graph": {"nodes": [], "links": []},
                },
            ),
            "south-america-agri-supply-shift",
            "market_access_or_trade_barrier_easing",
            "escalatory",
        ),
        (
            Event(
                id=uuid4(),
                canonical_summary="Paraguay River disruption delayed soybean shipments.",
                extracted_who=["Paraguay", "Argentina"],
                extracted_where="Paraguay River, Rosario, Argentina",
                extracted_what="Sediment buildup disrupted navigation and forced vessels to carry reduced loads.",
                categories=[
                    "south-america-agri-supply-shift:logistics_capacity_expansion:de_escalatory"
                ],
                extracted_claims={
                    "claims": [
                        "Sediment buildup in the Paraguay River disrupted navigation in early 2025.",
                        "Low water levels forced vessels to carry reduced loads, increasing per-ton shipping costs.",
                        "Paraguay's grain export volumes declined by 14% in Q1 2025.",
                    ],
                    "claim_graph": {"nodes": [], "links": []},
                },
            ),
            "south-america-agri-supply-shift",
            "climate_disruption_losses",
            "de_escalatory",
        ),
        (
            Event(
                id=uuid4(),
                canonical_summary="China redirected soybean demand toward Brazil.",
                extracted_who=["United States farmers", "China", "Brazilian soybean exporters"],
                extracted_where="United States, Brazil",
                extracted_what="China used potential soybean purchases as leverage while Brazil set export records.",
                categories=["south-america-agri-supply-shift:export_volume_cagr_growth:escalatory"],
                extracted_claims={
                    "claims": [
                        "Brazil set soybean export records earlier in 2025.",
                        "American farmers feel betrayed as China uses the promise of soybean purchases as leverage in tariff escalation.",
                    ],
                    "claim_graph": {"nodes": [], "links": []},
                },
            ),
            "south-america-agri-supply-shift",
            "china_demand_signal",
            "escalatory",
        ),
        (
            _cultivated_meat_ban_event(),
            "protein-transition",
            "alternative_protein_regulatory_restriction",
            "de_escalatory",
        ),
        (
            _billionaire_wealth_surge_event(),
            "elite-mass-polarization",
            "wealth_concentration_increase",
            "escalatory",
        ),
        (
            Event(
                id=uuid4(),
                canonical_summary="Housing costs and stagnant wages delayed family formation.",
                extracted_who=["young families under 35 in OECD nations"],
                extracted_where="OECD nations, specifically UK, Germany, and the US",
                extracted_what="Rising housing prices and stagnant wages delayed family formation.",
                extracted_claims={
                    "claims": [
                        "Rapidly rising house prices and stagnant real wages for under-35s across OECD nations are delaying family formation.",
                        "Homeownership rates among under-35s in the UK, Germany, and the US have fallen to historic lows.",
                    ],
                    "claim_graph": {"nodes": [], "links": []},
                },
            ),
            "fertility-decline",
            "family_cost_pressure",
            "escalatory",
        ),
    ],
)
def test_map_event_trend_impacts_handles_tier2_quality_regression_rows(
    event: Event,
    expected_trend_id: str,
    expected_signal_type: str,
    expected_direction: str,
) -> None:
    result = map_event_trend_impacts(event=event, trends=_configured_trends())

    assert result.diagnostics["unresolved"] == []
    assert result.impacts[0]["trend_id"] == expected_trend_id
    assert result.impacts[0]["signal_type"] == expected_signal_type
    assert result.impacts[0]["direction"] == expected_direction


def test_map_event_trend_impacts_records_ambiguous_and_no_match_paths() -> None:
    ambiguous_event = Event(
        id=uuid4(),
        canonical_summary="Summary",
        extracted_what="Troop movement near the border",
        extracted_claims={
            "claims": ["Troop deployment increased near the border."],
            "claim_graph": {
                "nodes": [
                    {
                        "claim_id": "claim_1",
                        "text": "Troop deployment increased near the border.",
                    }
                ],
                "links": [],
            },
        },
    )
    ambiguous = map_event_trend_impacts(
        event=ambiguous_event,
        trends=[
            _trend(trend_id="eu-russia", actors=[], regions=[]),
            _trend(trend_id="us-china", actors=[], regions=[]),
        ],
    )
    assert ambiguous.impacts == []
    assert ambiguous.diagnostics["unresolved"][0]["reason"] == "ambiguous_mapping"

    no_match_event = Event(
        id=uuid4(),
        canonical_summary="Summary",
        extracted_what="Economic talks resumed",
        extracted_claims={"claims": [], "claim_graph": {"nodes": [], "links": []}},
    )
    no_match = map_event_trend_impacts(
        event=no_match_event,
        trends=[
            _trend(
                indicators={
                    "incident": {
                        "direction": "escalatory",
                        "keywords": ["fired upon"],
                    }
                }
            )
        ],
    )
    assert no_match.impacts == []
    assert no_match.diagnostics["unresolved"][0]["reason"] == "no_matching_indicator"
    assert no_match.diagnostics["unresolved"][0]["event_claim_key"] == "__event__"


def test_mapping_helpers_expose_unresolved_payloads_and_reason_translation() -> None:
    empty_event = Event(id=uuid4(), extracted_claims={})
    assert iter_unresolved_mapping_gaps(empty_event) == []
    malformed_event = Event(
        id=uuid4(),
        extracted_claims={TREND_IMPACT_MAPPING_KEY: {"unresolved": "bad"}},
    )
    assert iter_unresolved_mapping_gaps(malformed_event) == []

    event = Event(
        id=uuid4(),
        extracted_claims={
            TREND_IMPACT_MAPPING_KEY: {
                "unresolved": [
                    {"reason": "ambiguous_mapping", "trend_id": "a", "signal_type": "b"},
                    "bad",
                ]
            }
        },
    )
    assert iter_unresolved_mapping_gaps(event) == [
        {"reason": "ambiguous_mapping", "trend_id": "a", "signal_type": "b"}
    ]
    assert (
        taxonomy_gap_reason_for_mapping("ambiguous_mapping") == TaxonomyGapReason.AMBIGUOUS_MAPPING
    )
    assert (
        taxonomy_gap_reason_for_mapping("anything-else") == TaxonomyGapReason.NO_MATCHING_INDICATOR
    )


def test_map_event_trend_impacts_uses_description_only_and_skips_invalid_indicators() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Summary",
        extracted_who=["NATO", "Russia"],
        extracted_where="Baltic region",
        extracted_what="Economic support package approval announced",
        extracted_claims={
            "claims": ["Economic support package approval announced"],
            "claim_graph": {
                "nodes": [
                    {"claim_id": "claim_1", "text": "Economic support package approval announced"}
                ],
                "links": [],
            },
        },
    )

    result = map_event_trend_impacts(
        event=event,
        trends=[
            _trend(
                indicators={
                    "ignored_non_mapping": "bad",
                    "ignored_direction": {
                        "direction": "sideways",
                        "keywords": ["approval"],
                    },
                    "economic_support": {
                        "direction": "de_escalatory",
                        "description": "Economic support package approval",
                        "keywords": [],
                    },
                }
            )
        ],
    )

    assert result.diagnostics["unresolved"] == []
    assert result.impacts[0]["signal_type"] == "economic_support"
    assert result.impacts[0]["confidence"] == pytest.approx(0.9)
    assert result.impacts[0]["rationale"].startswith("Matched indicator terms:")


def test_map_event_trend_impacts_uses_canonical_english_context_for_non_english_claims() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Military movement near the border intensified.",
        extracted_who=["NATO", "Russia"],
        extracted_where="Baltic region",
        extracted_what="Cross-border military force movement",
        extracted_claims={
            "claims": ["Розгортання військ біля кордону посилилося."],
            "claim_graph": {
                "nodes": [
                    {"claim_id": "claim_1", "text": "Розгортання військ біля кордону посилилося."}
                ],
                "links": [],
            },
        },
    )

    result = map_event_trend_impacts(
        event=event,
        trends=[
            _trend(
                indicators={
                    "military_movement": {
                        "direction": "escalatory",
                        "description": "Cross-border military force movement near the border",
                        "keywords": [],
                    }
                }
            )
        ],
    )

    assert result.diagnostics["unresolved"] == []
    assert len(result.impacts) == 1
    assert result.impacts[0]["signal_type"] == "military_movement"
    assert "Matched indicator terms" in result.impacts[0]["rationale"]


def test_map_event_trend_impacts_skips_negative_claims() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Troop deployment increased near the border.",
        extracted_who=["NATO", "Russia"],
        extracted_where="Baltic region",
        extracted_what="Troop deployment near the border",
        extracted_claims={
            "claims": ["Officials denied troop deployment near the border."],
            "claim_graph": {
                "nodes": [
                    {
                        "claim_id": "claim_1",
                        "text": "Officials denied troop deployment near the border.",
                    }
                ],
                "links": [],
            },
        },
    )

    result = map_event_trend_impacts(event=event, trends=[_trend()])

    assert len(result.impacts) == 1
    assert result.impacts[0]["event_claim_key"] == "__event__"
    assert result.diagnostics["unresolved"] == []
    assert result.diagnostics["skipped"][0]["reason"] == "negative_claim"
    assert result.diagnostics["skipped"][0]["event_claim_key"] == (
        "officials denied troop deployment near the border"
    )


def test_map_event_trend_impacts_does_not_treat_without_as_negative() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Summary",
        extracted_who=["NATO", "Russia"],
        extracted_where="Baltic region",
        extracted_what="Force repositioning without direct hostile contact",
        extracted_claims={
            "claims": ["Forces repositioned near the border without direct hostile contact."],
            "claim_graph": {
                "nodes": [
                    {
                        "claim_id": "claim_1",
                        "text": "Forces repositioned near the border without direct hostile contact.",
                    }
                ],
                "links": [],
            },
        },
    )

    result = map_event_trend_impacts(event=event, trends=[_trend()])

    assert len(result.impacts) == 1
    assert "skipped" not in result.diagnostics


def test_map_event_trend_impacts_does_not_skip_unknown_language_claims() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Summary",
        extracted_what="Economic talks resumed",
        extracted_claims={
            "claims": ["Déploiement de troupes près de la frontière."],
            "claim_graph": {
                "nodes": [
                    {
                        "claim_id": "claim_1",
                        "text": "Déploiement de troupes près de la frontière.",
                    }
                ],
                "links": [],
            },
        },
    )

    result = map_event_trend_impacts(event=event, trends=[_trend()])

    assert result.impacts == []
    assert result.diagnostics["unresolved"][0]["reason"] == "no_matching_indicator"
    assert "skipped" not in result.diagnostics


def test_map_event_trend_impacts_uses_canonical_context_for_english_paraphrases() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Troop deployment increased near the border.",
        extracted_who=["NATO", "Russia"],
        extracted_where="Baltic region",
        extracted_what="Troop deployment near the border",
        extracted_claims={
            "claims": ["Forces moved again near the frontier."],
            "claim_graph": {
                "nodes": [{"claim_id": "claim_1", "text": "Forces moved again near the frontier."}],
                "links": [],
            },
        },
    )

    result = map_event_trend_impacts(event=event, trends=[_trend()])

    assert len(result.impacts) == 1
    assert result.impacts[0]["event_claim_key"] == "__event__"
    assert result.impacts[0]["signal_type"] == "military_movement"
    assert result.diagnostics["unresolved"] == []


def test_map_event_trend_impacts_deduplicates_duplicate_indicator_matches() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Summary",
        extracted_who=["NATO", "Russia"],
        extracted_where="Baltic region",
        extracted_what="Troop deployment near the border",
        extracted_claims={
            "claims": [
                "Troop deployment increased near the border.",
                "Deployment activity also intensified near the border.",
            ],
            "claim_graph": {
                "nodes": [
                    {
                        "claim_id": "claim_1",
                        "text": "Troop deployment increased near the border.",
                    },
                    {
                        "claim_id": "claim_2",
                        "text": "Deployment activity also intensified near the border.",
                    },
                ],
                "links": [],
            },
        },
    )

    result = map_event_trend_impacts(event=event, trends=[_trend()])

    assert len(result.impacts) == 1
    assert result.impacts[0]["event_claim_key"] == "troop deployment increased near the border"
    assert result.diagnostics["deduplicated"][0]["reason"] == "duplicate_event_indicator"
    assert result.diagnostics["deduplicated"][0]["signal_type"] == "military_movement"


def test_map_event_trend_impacts_replaces_weaker_duplicate_indicator_match() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Troop deployment increased near the border.",
        extracted_who=["NATO", "Russia"],
        extracted_where="Baltic region",
        extracted_what="Troop deployment near the border",
        extracted_claims={
            "claims": [
                _UKRAINIAN_MOVEMENT_CLAIM,
                "Troop deployment increased near the border.",
            ],
            "claim_graph": {
                "nodes": [
                    {"claim_id": "claim_1", "text": _UKRAINIAN_MOVEMENT_CLAIM},
                    {
                        "claim_id": "claim_2",
                        "text": "Troop deployment increased near the border.",
                    },
                ],
                "links": [],
            },
        },
    )

    result = map_event_trend_impacts(event=event, trends=[_trend()])

    assert len(result.impacts) == 1
    assert result.impacts[0]["event_claim_key"] == "troop deployment increased near the border"
    assert result.diagnostics["deduplicated"][0]["event_claim_key"] == (
        "\u0440\u0443\u0445 \u0441\u0438\u043b \u0431\u0456\u043b\u044f "
        "\u043a\u043e\u0440\u0434\u043e\u043d\u0443 \u043f\u043e\u0441\u0438\u043b\u0438\u0432\u0441\u044f"
    )
    assert result.diagnostics["deduplicated"][0]["details"]["kept_event_claim_key"] == (
        "troop deployment increased near the border"
    )


def test_map_event_trend_impacts_prefers_direct_statement_over_fallback_event_claim() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Troop deployment increased near the border.",
        extracted_who=["NATO", "Russia"],
        extracted_where="Baltic region",
        extracted_what="Troop deployment near the border",
        extracted_claims={
            "claims": [
                "Budget talks continued among ministers.",
                "Troop deployment increased near the border.",
            ],
            "claim_graph": {
                "nodes": [
                    {"claim_id": "claim_1", "text": "Budget talks continued among ministers."},
                    {
                        "claim_id": "claim_2",
                        "text": "Troop deployment increased near the border.",
                    },
                ],
                "links": [],
            },
        },
    )

    result = map_event_trend_impacts(event=event, trends=[_trend()])

    assert len(result.impacts) == 1
    assert result.impacts[0]["event_claim_key"] == "troop deployment increased near the border"
    assert all(
        diagnostic["event_claim_key"] != "budget talks continued among ministers"
        for diagnostic in result.diagnostics.get("deduplicated", [])
    )


def test_map_event_trend_impacts_uses_default_indicator_description_and_multi_keyword_signal() -> (
    None
):
    event = Event(
        id=uuid4(),
        canonical_summary="Summary",
        extracted_who=["NATO", "Russia"],
        extracted_where="Baltic region",
        extracted_what="Aid package financial support expanded",
        extracted_claims={
            "claims": ["Aid package financial support expanded"],
            "claim_graph": {
                "nodes": [
                    {"claim_id": "claim_1", "text": "Aid package financial support expanded"}
                ],
                "links": [],
            },
        },
    )

    result = map_event_trend_impacts(
        event=event,
        trends=[
            _trend(
                indicators={
                    "": {
                        "direction": "escalatory",
                        "keywords": ["aid package", "financial support"],
                    }
                }
            )
        ],
    )

    assert result.diagnostics["unresolved"] == []
    assert result.impacts[0]["signal_type"] == ""
    assert result.impacts[0]["severity"] == pytest.approx(0.8)
    assert result.impacts[0]["confidence"] == pytest.approx(0.95)


def test_build_impact_skips_runner_up_bonus_when_gap_is_below_ten() -> None:
    claim = EventClaimSpec(
        claim_key="claim",
        normalized_text="claim text",
        claim_text="Claim text",
        claim_type="statement",
        claim_order=1,
    )
    indicator = _IndicatorContext(
        trend_id="eu-russia",
        trend_name="EU-Russia",
        signal_type="military_movement",
        signal_phrase="military movement",
        direction="escalatory",
        description="Force repositioning",
        keywords=("deployment",),
        description_terms=("force", "repositioning"),
        actor_phrases=(),
        region_phrases=(),
    )
    best = _Candidate(
        indicator=indicator,
        claim=claim,
        score=100,
        matched_keywords=("deployment",),
        description_overlap=("force",),
        category_matches=(),
        trend_category_matches=(),
        actor_matches=(),
        region_matches=(),
    )
    runner_up = _Candidate(
        indicator=indicator,
        claim=claim,
        score=94,
        matched_keywords=("deployment",),
        description_overlap=("force",),
        category_matches=(),
        trend_category_matches=(),
        actor_matches=(),
        region_matches=(),
    )

    impact = _build_impact(best=best, runner_up=runner_up)

    assert impact["confidence"] == pytest.approx(0.8)


def test_category_pair_matching_requires_direction_segment() -> None:
    indicator = _IndicatorContext(
        trend_id="eu-russia",
        trend_name="EU-Russia",
        signal_type="military_movement",
        signal_phrase="military movement",
        direction="escalatory",
        description="Force repositioning",
        keywords=("deployment",),
        description_terms=("force", "repositioning"),
        actor_phrases=(),
        region_phrases=(),
    )

    assert _category_matches_pair(
        category="eu russia military movement escalatory",
        indicator=indicator,
    )
    assert not _category_matches_pair(
        category="eu russia military movement de escalatory",
        indicator=indicator,
    )
