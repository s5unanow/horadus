"""Dataclasses shared by behavior-eval runner and scenario definitions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class BehaviorEvalCaseDefinition:
    """Static definition for one deterministic behavior-eval case."""

    case_id: str
    title: str
    suite: str
    tags: tuple[str, ...]
    production_contract: str
    expected_behavior: str
    surface_paths: tuple[str, ...]
    runner: Callable[[], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class BehaviorEvalCaseResult:
    """Serializable result for one executed behavior-eval case."""

    case_id: str
    title: str
    suite: str
    tags: tuple[str, ...]
    production_contract: str
    expected_behavior: str
    surface_paths: tuple[str, ...]
    passed: bool
    duration_ms: int
    evidence: dict[str, Any] | None = None
    failure_message: str | None = None


@dataclass(frozen=True, slots=True)
class BehaviorEvalRunResult:
    """Summary handle for a completed behavior-eval run."""

    output_path: Path
    passes_validation: bool
    total_cases: int
    selected_cases: int
    passed_cases: int
    failed_cases: int
    selected_suites: tuple[str, ...]
    selected_tags: tuple[str, ...]
    case_results: tuple[BehaviorEvalCaseResult, ...]
