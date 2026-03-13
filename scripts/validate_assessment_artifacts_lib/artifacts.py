"""Markdown parsing helpers for assessment artifacts."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .constants import (
    FIELD_ALIASES,
    NON_FIELD_SECTION_ALIASES,
    RE_ALL_CLEAR,
    RE_DAILY_FILENAME_DATE,
    RE_FIELD_LINE,
    RE_PROPOSAL_HEADING,
)
from .models import ParsedArtifact, ProposalBlock


def iter_markdown_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(
                sorted(
                    candidate for candidate in path.rglob("*.md") if "_raw" not in candidate.parts
                )
            )
        else:
            files.append(path)
    return files


def parse_confidence(value: str) -> float | None:
    try:
        confidence = float(value.strip())
    except ValueError:
        return None
    if 0.0 <= confidence <= 1.0:
        return confidence
    return None


def normalize_field_key(raw_key: str) -> str | None:
    normalized = " ".join(raw_key.strip().lower().split())
    return FIELD_ALIASES.get(normalized)


def normalize_non_field_section(raw_key: str) -> str | None:
    normalized = " ".join(raw_key.strip().lower().split())
    if normalized in NON_FIELD_SECTION_ALIASES:
        return normalized.replace(" ", "_")
    return None


def parse_block_content(
    block_lines: list[str],
    start_line_no: int,
) -> tuple[dict[str, str], dict[str, str]]:
    fields: dict[str, str] = {}
    sections: dict[str, str] = {}
    current_kind: str | None = None
    current_key: str | None = None
    current_values: list[str] = []

    def flush() -> None:
        nonlocal current_kind, current_key, current_values
        if current_key is None:
            return
        content = "\n".join(line.rstrip() for line in current_values).strip()
        if content:
            if current_kind == "field":
                fields[current_key] = content
            elif current_kind == "section":
                sections[current_key] = content
        current_kind = None
        current_key = None
        current_values = []

    for _line_no, line in enumerate(block_lines, start=start_line_no + 1):
        field_match = RE_FIELD_LINE.match(line)
        if field_match:
            raw_key = field_match.group(1)
            raw_value = field_match.group(2)
            field_key = normalize_field_key(raw_key)
            non_field_key = normalize_non_field_section(raw_key)

            if field_key is not None:
                flush()
                if raw_value.strip():
                    fields[field_key] = raw_value.strip()
                else:
                    current_kind = "field"
                    current_key = field_key
                continue

            if non_field_key is not None:
                flush()
                current_kind = "section"
                current_key = non_field_key
                if raw_value.strip():
                    current_values.append(raw_value.strip())
                continue

        if current_key is not None:
            if line.strip():
                current_values.append(line)
            else:
                flush()

    flush()
    return fields, sections


def role_from_path(path: Path) -> str | None:
    parts = path.parts
    for index, part in enumerate(parts):
        if part == "assessments" and index + 2 < len(parts):
            return parts[index + 1]
    return None


def parse_artifact(path: Path) -> ParsedArtifact:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    proposal_starts: list[tuple[int, str]] = []
    for idx, line in enumerate(lines, start=1):
        match = RE_PROPOSAL_HEADING.match(line)
        if match:
            proposal_starts.append((idx, match.group(1)))

    proposals: list[ProposalBlock] = []
    for index, (start_line_no, proposal_id) in enumerate(proposal_starts):
        end_line_no = (
            proposal_starts[index + 1][0] - 1 if index + 1 < len(proposal_starts) else len(lines)
        )
        block_lines = lines[start_line_no:end_line_no]
        fields, sections = parse_block_content(block_lines, start_line_no)
        proposals.append(
            ProposalBlock(
                proposal_id=proposal_id,
                line_no=start_line_no,
                fields=fields,
                sections=sections,
            )
        )

    return ParsedArtifact(
        path=path,
        role=role_from_path(path),
        is_all_clear=bool(RE_ALL_CLEAR.search(text)),
        proposals=tuple(proposals),
    )


def artifact_file_date(path: Path) -> date | None:
    match = RE_DAILY_FILENAME_DATE.search(path.name)
    if match is None:
        return None
    return date.fromisoformat(match.group(1))


def proposal_body_text(proposal: ProposalBlock) -> str:
    return "\n".join(
        [
            proposal.sections.get("problem", ""),
            proposal.sections.get("proposed_change", ""),
            proposal.fields.get("verification", ""),
            proposal.fields.get("blast_radius", ""),
        ]
    ).strip()
