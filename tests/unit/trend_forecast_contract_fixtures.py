from __future__ import annotations

from copy import deepcopy
from typing import Any

import yaml


def sample_binary_forecast_contract(**overrides: Any) -> dict[str, Any]:
    contract = {
        "question": "Will a test conflict occur by 2030-12-31?",
        "horizon": {"kind": "fixed_date", "fixed_date": "2030-12-31"},
        "resolution_basis": ("Binary event question resolved against confirmed direct conflict."),
        "resolver_source": "Official statements plus multi-source corroborated reporting.",
        "resolver_basis": "Resolve yes on confirmed conflict; otherwise resolve no at horizon.",
        "closure_rule": "binary_event_by_horizon",
        "occurrence_definition": "Confirmed direct conflict occurs.",
        "non_occurrence_definition": "No confirmed direct conflict occurs by the horizon date.",
    }
    contract.update(overrides)
    return contract


def sample_threshold_forecast_contract(**overrides: Any) -> dict[str, Any]:
    contract = {
        "question": "Will a tracked structural state still hold on 2035-12-31?",
        "horizon": {"kind": "fixed_date", "fixed_date": "2035-12-31"},
        "resolution_basis": (
            "Threshold-state question resolved at horizon using tracked public data "
            "and corroborated reporting."
        ),
        "resolver_source": "Public datasets, official releases, and corroborated reporting.",
        "resolver_basis": "Resolve yes if the tracked state is present at horizon; otherwise no.",
        "closure_rule": "threshold_state_at_horizon",
    }
    contract.update(overrides)
    return contract


def sample_forecast_contract_yaml(contract: dict[str, Any] | None = None) -> str:
    payload = {"forecast_contract": deepcopy(contract or sample_binary_forecast_contract())}
    return yaml.safe_dump(payload, sort_keys=False).rstrip()
