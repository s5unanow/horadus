from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class DocsFreshnessIssue:
    level: str
    rule_id: str
    message: str
    path: str | None = None


@dataclass(frozen=True, slots=True)
class DocsFreshnessResult:
    errors: tuple[DocsFreshnessIssue, ...]
    warnings: tuple[DocsFreshnessIssue, ...]

    @property
    def is_ok(self) -> bool:
        return len(self.errors) == 0


@dataclass(frozen=True, slots=True)
class _MarkerRequirement:
    path: str
    label: str


@dataclass(frozen=True, slots=True)
class _ConflictRule:
    rule_id: str
    pattern: str
    description: str


@dataclass(frozen=True, slots=True)
class _Override:
    rule_id: str
    path: str
    reason: str
    expires_on: date
