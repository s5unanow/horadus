from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from src.core.trend_config_loader import load_trends_from_config_dir
from src.processing.trend_impact_mapping import map_event_trend_impacts
from src.storage.models import Event

pytestmark = pytest.mark.unit


def _configured_trends():
    return load_trends_from_config_dir(config_dir=Path("config/trends"))


def test_map_event_trend_impacts_maps_retenciones_to_export_tax_tightening() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Argentina raised retenciones on soybean exports.",
        extracted_who=["Argentine government"],
        extracted_where="Argentina",
        extracted_what="Argentina raised retenciones after an export tax increase.",
        extracted_claims={
            "claims": [
                "Argentina raised retenciones on soybean exports after an export tax increase.",
            ],
            "claim_graph": {"nodes": [], "links": []},
        },
    )

    result = map_event_trend_impacts(event=event, trends=_configured_trends())

    assert result.diagnostics["unresolved"] == []
    assert result.impacts[0]["trend_id"] == "south-america-agri-supply-shift"
    assert result.impacts[0]["signal_type"] == "export_tax_or_quota_tightening"
    assert result.impacts[0]["direction"] == "de_escalatory"


def test_map_event_trend_impacts_maps_export_tax_reductions_to_market_access() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Argentina reduced soybean export taxes.",
        extracted_who=["Argentine government"],
        extracted_where="Argentina",
        extracted_what="Argentina reduced soybean export taxes to improve market access.",
        extracted_claims={
            "claims": [
                "Argentina reduced soybean export taxes to improve export competitiveness.",
            ],
            "claim_graph": {"nodes": [], "links": []},
        },
    )

    result = map_event_trend_impacts(event=event, trends=_configured_trends())

    assert result.diagnostics["unresolved"] == []
    assert result.impacts[0]["trend_id"] == "south-america-agri-supply-shift"
    assert result.impacts[0]["signal_type"] == "market_access_or_trade_barrier_easing"
    assert result.impacts[0]["direction"] == "escalatory"


def test_map_event_trend_impacts_maps_deradicalization_program_to_counter_signal() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="France expanded a deradicalization program.",
        extracted_who=["France"],
        extracted_where="Western Europe",
        extracted_what="France expanded a deradicalization program with verified outcomes.",
        extracted_claims={
            "claims": [
                "France expanded a deradicalization program that reduced extremist recruitment.",
            ],
            "claim_graph": {"nodes": [], "links": []},
        },
    )

    result = map_event_trend_impacts(event=event, trends=_configured_trends())

    assert result.diagnostics["unresolved"] == []
    assert result.impacts[0]["trend_id"] == "parallel-enclaves-europe"
    assert result.impacts[0]["signal_type"] == "counter_radicalization_success"
    assert result.impacts[0]["direction"] == "de_escalatory"


def test_map_event_trend_impacts_does_not_map_peace_agreement_to_frozen_conflict() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Ukraine and Russia signed a broad peace agreement.",
        extracted_who=["Ukraine", "Russia"],
        extracted_where="Ukraine",
        extracted_what="A peace agreement ended active hostilities.",
        extracted_claims={
            "claims": ["Ukraine and Russia signed a broad peace agreement."],
            "claim_graph": {"nodes": [], "links": []},
        },
    )

    result = map_event_trend_impacts(event=event, trends=_configured_trends())

    assert all(
        impact["signal_type"] != "frozen_conflict_formalization"
        for impact in result.impacts
        if impact["trend_id"] == "ukraine-security-frontier-model"
    )


def test_map_event_trend_impacts_maps_scoped_child_exploitation_prosecution() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Authorities announced prosecution for child exploitation.",
        extracted_who=["child protection authorities"],
        extracted_where="Europe",
        extracted_what="Authorities announced prosecution for child exploitation.",
        extracted_claims={
            "claims": ["Authorities announced prosecution for child exploitation."],
            "claim_graph": {"nodes": [], "links": []},
        },
    )

    result = map_event_trend_impacts(event=event, trends=_configured_trends())

    assert result.diagnostics["unresolved"] == []
    assert result.impacts[0]["trend_id"] == "normative-deviance-normalization"
    assert result.impacts[0]["signal_type"] == "legal_enforcement_crackdown"
    assert result.impacts[0]["direction"] == "de_escalatory"


def test_map_event_trend_impacts_maps_regenerative_agriculture_to_meat_adaptation() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Livestock producers expanded regenerative agriculture programs.",
        extracted_who=["livestock producers"],
        extracted_where="North America",
        extracted_what="Livestock producers expanded regenerative agriculture programs.",
        extracted_claims={
            "claims": [
                "Livestock producers expanded regenerative agriculture programs to reduce methane intensity.",
            ],
            "claim_graph": {"nodes": [], "links": []},
        },
    )

    result = map_event_trend_impacts(event=event, trends=_configured_trends())

    assert result.diagnostics["unresolved"] == []
    assert result.impacts[0]["trend_id"] == "protein-transition"
    assert result.impacts[0]["signal_type"] == "conventional_meat_adaptation"
    assert result.impacts[0]["direction"] == "de_escalatory"


def test_map_event_trend_impacts_maps_b4u_act_to_academic_legitimation() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="A journal cited B4U-ACT in research reframing minor attraction.",
        extracted_who=["academic publishers", "B4U-ACT"],
        extracted_where="North America",
        extracted_what="A journal cited B4U-ACT in research reframing minor attraction.",
        extracted_claims={
            "claims": [
                "A peer reviewed article cited B4U-ACT in research reframing minor attraction.",
            ],
            "claim_graph": {"nodes": [], "links": []},
        },
    )

    result = map_event_trend_impacts(event=event, trends=_configured_trends())

    assert result.diagnostics["unresolved"] == []
    assert result.impacts[0]["trend_id"] == "normative-deviance-normalization"
    assert result.impacts[0]["signal_type"] == "academic_legitimation"
    assert result.impacts[0]["direction"] == "escalatory"


def test_map_event_trend_impacts_maps_clan_crime_offenses_to_informal_justice() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Authorities reported clan crime offenses and clan mediation.",
        extracted_who=["Germany"],
        extracted_where="Western Europe",
        extracted_what="Authorities reported clan crime offenses and clan mediation.",
        extracted_claims={
            "claims": [
                "Authorities reported clan crime offenses alongside clan mediation networks.",
            ],
            "claim_graph": {"nodes": [], "links": []},
        },
    )

    result = map_event_trend_impacts(event=event, trends=_configured_trends())

    assert result.diagnostics["unresolved"] == []
    assert result.impacts[0]["trend_id"] == "parallel-enclaves-europe"
    assert result.impacts[0]["signal_type"] == "informal_justice_prevalence"
    assert result.impacts[0]["direction"] == "escalatory"


def test_map_event_trend_impacts_does_not_map_proper_nouns_to_integration_gains() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="A report referenced Nahel Merzouk and court proceedings.",
        extracted_who=["France", "European Court of Justice"],
        extracted_where="Western Europe",
        extracted_what="A report referenced Nahel Merzouk and court proceedings.",
        extracted_claims={
            "claims": [
                "A report referenced Nahel Merzouk and European Court of Justice proceedings.",
            ],
            "claim_graph": {"nodes": [], "links": []},
        },
    )

    result = map_event_trend_impacts(event=event, trends=_configured_trends())

    assert all(
        impact["signal_type"] != "integration_policy_gains"
        for impact in result.impacts
        if impact["trend_id"] == "parallel-enclaves-europe"
    )
