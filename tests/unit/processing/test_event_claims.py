from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.processing.event_claims import (
    FALLBACK_EVENT_CLAIM_KEY,
    _decorate_event_claim_payload,
    _decorate_impact_payload,
    assign_claim_keys_to_impacts,
    build_event_claim_specs,
    fallback_event_claim_id,
    sync_event_claims,
)
from src.storage.models import Event, EventClaim

pytestmark = pytest.mark.unit


def test_build_event_claim_specs_covers_graph_and_claim_list_paths() -> None:
    graph_event = Event(
        extracted_what="Border clash",
        extracted_claims={
            "claim_graph": {
                "nodes": [
                    {"text": " Border clashes intensify "},
                    "skip-me",
                    {"text": "   "},
                    {"text": "Border clashes intensify"},
                    {"text": "Ceasefire talks resume"},
                ]
            }
        },
    )

    graph_specs = build_event_claim_specs(graph_event)

    assert [spec.claim_key for spec in graph_specs] == [
        FALLBACK_EVENT_CLAIM_KEY,
        "border clashes intensify",
        "ceasefire talks resume",
    ]

    claims_event = Event(
        canonical_summary="Fallback summary",
        extracted_claims={
            "claim_graph": "bad",
            "claims": [" First claim ", "!!!", None, "Second claim"],
        },
    )

    claim_specs = build_event_claim_specs(claims_event)

    assert [spec.claim_key for spec in claim_specs] == [
        FALLBACK_EVENT_CLAIM_KEY,
        "first claim",
        "second claim",
    ]

    non_list_claims_event = Event(
        canonical_summary="Fallback summary",
        extracted_claims={"claim_graph": {}, "claims": "bad"},
    )

    assert [spec.claim_key for spec in build_event_claim_specs(non_list_claims_event)] == [
        FALLBACK_EVENT_CLAIM_KEY
    ]


def test_assign_claim_keys_to_impacts_covers_selection_paths() -> None:
    multi_claim_event = Event(
        extracted_what="Fallback summary",
        extracted_claims={
            "claim_graph": {
                "nodes": [
                    {"text": "Border clashes intensify"},
                    {"text": "Ceasefire talks resume"},
                ]
            }
        },
    )

    assigned = assign_claim_keys_to_impacts(
        event=multi_claim_event,
        impacts=[
            "passthrough",
            {"event_claim_key": "ceasefire talks resume", "signal_type": "diplomacy"},
            {
                "signal_type": "military_movement",
                "direction": "escalatory",
                "rationale": "Border clashes intensify along the frontier",
            },
            {"signal_type": "", "direction": ""},
        ],
    )

    assert assigned[0] == "passthrough"
    assert assigned[1]["event_claim_key"] == "ceasefire talks resume"
    assert assigned[2]["event_claim_key"] == "border clashes intensify"
    assert assigned[3]["event_claim_key"] == FALLBACK_EVENT_CLAIM_KEY

    single_claim_event = Event(
        extracted_what="Fallback summary",
        extracted_claims={"claims": ["Single tracked statement"]},
    )

    single_assigned = assign_claim_keys_to_impacts(
        event=single_claim_event,
        impacts=[{"signal_type": "diplomacy", "direction": "de_escalatory"}],
    )

    assert single_assigned[0]["event_claim_key"] == "single tracked statement"


@pytest.mark.asyncio
async def test_sync_event_claims_requires_event_id() -> None:
    with pytest.raises(ValueError, match="Event must have an id"):
        await sync_event_claims(session=AsyncMock(), event=Event())


@pytest.mark.asyncio
async def test_sync_event_claims_updates_existing_rows_and_decorates_payload() -> None:
    event_id = uuid4()
    fallback_claim = EventClaim(
        id=uuid4(),
        event_id=event_id,
        claim_key=FALLBACK_EVENT_CLAIM_KEY,
        claim_text="Old fallback",
        claim_type="fallback",
        claim_order=9,
        is_active=False,
    )
    statement_claim = EventClaim(
        id=uuid4(),
        event_id=event_id,
        claim_key="border clashes intensify",
        claim_text="Old statement",
        claim_type="statement",
        claim_order=8,
        is_active=False,
    )
    retired_claim = EventClaim(
        id=uuid4(),
        event_id=event_id,
        claim_key="retired statement",
        claim_text="Retired",
        claim_type="statement",
        claim_order=7,
        is_active=True,
    )
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.scalars = AsyncMock(
        return_value=SimpleNamespace(all=lambda: [fallback_claim, statement_claim, retired_claim])
    )
    event = Event(
        id=event_id,
        extracted_what="New fallback",
        extracted_claims={
            "claim_graph": {"nodes": ["skip-me", {"text": "Border clashes intensify"}]},
            "trend_impacts": [
                {"signal_type": "military_movement", "direction": "escalatory"},
                "raw-impact",
            ],
        },
    )

    resolved = await sync_event_claims(session=session, event=event)

    assert session.add.call_count == 0
    assert session.flush.await_count == 1
    assert fallback_claim.claim_text == "New fallback"
    assert fallback_claim.claim_order == 0
    assert fallback_claim.is_active is True
    assert statement_claim.claim_text == "Border clashes intensify"
    assert statement_claim.claim_order == 1
    assert statement_claim.is_active is True
    assert retired_claim.is_active is False
    assert set(resolved) == {
        FALLBACK_EVENT_CLAIM_KEY,
        "border clashes intensify",
    }
    extracted_claims = event.extracted_claims or {}
    assert extracted_claims["claim_graph"]["nodes"][0] == "skip-me"
    assert extracted_claims["claim_graph"]["nodes"][1]["event_claim_id"] == str(statement_claim.id)
    assert extracted_claims["trend_impacts"][0]["event_claim_id"] == str(statement_claim.id)
    assert extracted_claims["trend_impacts"][1] == "raw-impact"
    assert extracted_claims["event_claims"][0]["event_claim_id"] == str(fallback_claim.id)


def test_decorate_helpers_and_fallback_lookup_cover_guard_paths() -> None:
    fallback_with_id = EventClaim(
        id=uuid4(),
        event_id=uuid4(),
        claim_key=FALLBACK_EVENT_CLAIM_KEY,
        claim_text="Cluster event",
        claim_type="fallback",
        claim_order=0,
        is_active=True,
    )
    statement_without_id = EventClaim(
        id=None,
        event_id=uuid4(),
        claim_key="tracked statement",
        claim_text="Tracked statement",
        claim_type="statement",
        claim_order=1,
        is_active=True,
    )

    non_dict_graph_event = Event(
        extracted_claims={"claim_graph": "bad", "trend_impacts": "bad"},
    )
    _decorate_event_claim_payload(
        event=non_dict_graph_event,
        claim_by_key={FALLBACK_EVENT_CLAIM_KEY: fallback_with_id},
    )
    assert non_dict_graph_event.extracted_claims == {
        "claim_graph": "bad",
        "trend_impacts": "bad",
        "event_claims": [
            {
                "event_claim_id": str(fallback_with_id.id),
                "event_claim_key": FALLBACK_EVENT_CLAIM_KEY,
                "claim_text": "Cluster event",
                "claim_type": "fallback",
                "is_active": True,
            }
        ],
    }

    non_list_nodes_event = Event(
        extracted_claims={"claim_graph": {"nodes": "bad"}, "trend_impacts": []},
    )
    _decorate_event_claim_payload(
        event=non_list_nodes_event,
        claim_by_key={FALLBACK_EVENT_CLAIM_KEY: fallback_with_id},
    )
    assert non_list_nodes_event.extracted_claims["claim_graph"]["nodes"] == "bad"

    undecorated_statement_event = Event(
        extracted_claims={
            "claim_graph": {"nodes": ["skip-me", {"text": "Tracked statement"}]},
            "trend_impacts": [],
        },
    )
    _decorate_event_claim_payload(
        event=undecorated_statement_event,
        claim_by_key={
            FALLBACK_EVENT_CLAIM_KEY: fallback_with_id,
            "tracked statement": statement_without_id,
        },
    )
    assert undecorated_statement_event.extracted_claims["claim_graph"]["nodes"][0] == "skip-me"
    assert undecorated_statement_event.extracted_claims["claim_graph"]["nodes"][1] == {
        "text": "Tracked statement"
    }

    missing_key_payload = _decorate_impact_payload(
        payload={"signal_type": "military_movement", "event_claim_key": "missing"},
        claim_by_key={
            FALLBACK_EVENT_CLAIM_KEY: EventClaim(
                id=None,
                event_id=uuid4(),
                claim_key=FALLBACK_EVENT_CLAIM_KEY,
                claim_text="Cluster event",
                claim_type="fallback",
                claim_order=0,
            )
        },
    )
    assert missing_key_payload["event_claim_key"] == FALLBACK_EVENT_CLAIM_KEY
    assert "event_claim_id" not in missing_key_payload

    assert fallback_event_claim_id(claims_payload={"event_claims": "bad"}) is None
    assert (
        fallback_event_claim_id(
            claims_payload={
                "event_claims": [
                    {"event_claim_key": "other", "event_claim_id": "claim-999"},
                    {"event_claim_key": FALLBACK_EVENT_CLAIM_KEY, "event_claim_id": "   "},
                ]
            }
        )
        is None
    )
    assert (
        fallback_event_claim_id(
            claims_payload={
                "event_claims": [
                    "skip-me",
                    {"event_claim_key": FALLBACK_EVENT_CLAIM_KEY, "event_claim_id": "   "},
                    {"event_claim_key": FALLBACK_EVENT_CLAIM_KEY, "event_claim_id": "claim-123"},
                ]
            }
        )
        == "claim-123"
    )
