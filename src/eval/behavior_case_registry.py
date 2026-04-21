"""Registry for deterministic behavior-eval case definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.eval.behavior_cases import behavior_case_definitions as base_behavior_case_definitions
from src.eval.behavior_cases_retrieval import retrieval_behavior_case_definitions

if TYPE_CHECKING:
    from src.eval.behavior_types import BehaviorEvalCaseDefinition


def behavior_case_definitions() -> tuple[BehaviorEvalCaseDefinition, ...]:
    """Return the full behavior-eval case registry."""

    return (
        *base_behavior_case_definitions(),
        *retrieval_behavior_case_definitions(),
    )
