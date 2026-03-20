from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

import src.processing.tier2_classifier as tier2_classifier_module
from src.processing.tier2_classifier import Tier2Classifier, _Tier2Output
from src.storage.models import Event

pytestmark = pytest.mark.unit


def test_apply_output_does_not_override_retracted_event_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    classifier = object.__new__(Tier2Classifier)
    event = Event(
        id=uuid4(),
        canonical_summary="Retracted event",
        lifecycle_status="archived",
        epistemic_state="retracted",
        activity_state="closed",
    )
    output = _Tier2Output(
        summary="Updated summary",
        extracted_who=["Country A"],
        extracted_what="Updated detail",
        claims=["Claim one"],
        categories=["military"],
        has_contradictions=False,
    )

    monkeypatch.setattr(
        tier2_classifier_module,
        "map_event_trend_impacts",
        lambda **_: SimpleNamespace(impacts=[], diagnostics={}),
    )
    monkeypatch.setattr(
        tier2_classifier_module,
        "assign_claim_keys_to_impacts",
        lambda **_: [],
    )

    classifier._apply_output(event=event, output=output, trends=[])

    assert event.epistemic_state == "retracted"
    assert event.activity_state == "closed"
