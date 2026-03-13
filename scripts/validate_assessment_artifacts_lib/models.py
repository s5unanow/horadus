"""Data models shared across assessment validation passes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    path: Path
    line_no: int
    message: str


@dataclass(frozen=True)
class ProposalBlock:
    proposal_id: str
    line_no: int
    fields: dict[str, str]
    sections: dict[str, str]


@dataclass(frozen=True)
class ParsedArtifact:
    path: Path
    role: str | None
    is_all_clear: bool
    proposals: tuple[ProposalBlock, ...]
