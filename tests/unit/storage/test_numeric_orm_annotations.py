from __future__ import annotations

import sys
import typing
from decimal import Decimal
from typing import get_args, get_origin, get_type_hints

import pytest
from sqlalchemy.orm import Mapped

from src.storage.models import ApiUsage, Event, Source, Trend, TrendEvidence, TrendSnapshot
from src.storage.restatement_models import TrendRestatement
from src.storage.trend_state_models import TrendStateVersion

pytestmark = pytest.mark.unit


def test_numeric_orm_annotations_use_decimal_runtime_types() -> None:
    annotation_cases = (
        (Source, "credibility_score", Decimal),
        (Event, "corroboration_score", Decimal),
        (Trend, "baseline_log_odds", Decimal),
        (Trend, "current_log_odds", Decimal),
        (TrendEvidence, "base_weight", Decimal | None),
        (TrendEvidence, "direction_multiplier", Decimal | None),
        (TrendEvidence, "delta_log_odds", Decimal),
        (TrendSnapshot, "log_odds", Decimal),
        (TrendStateVersion, "current_log_odds", Decimal),
        (TrendRestatement, "compensation_delta_log_odds", Decimal),
        (ApiUsage, "estimated_cost_usd", Decimal),
    )

    for model, field_name, expected_type in annotation_cases:
        annotation = get_type_hints(
            model,
            globalns={
                **typing.__dict__,
                **sys.modules[model.__module__].__dict__,
                "Decimal": Decimal,
                "Trend": Trend,
            },
            include_extras=True,
        )
        field_annotation = annotation[field_name]
        assert get_origin(field_annotation) is Mapped
        assert get_args(field_annotation) == (expected_type,)
