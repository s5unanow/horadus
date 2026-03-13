"""Core schema and formatting validation for assessment artifacts."""

from __future__ import annotations

from pathlib import Path

from .artifacts import parse_artifact, parse_block_content, parse_confidence
from .constants import (
    ALLOWED_AREAS,
    ALLOWED_GATES,
    RE_DAILY_FILENAME_DATE,
    RE_FORBIDDEN_TASK_HEADING,
    RE_PRIORITY,
    RE_PROPOSAL_DATE,
    RE_TITLE_DATE,
    REQUIRED_FIELDS,
)
from .models import Finding


def validate_file(path: Path) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    artifact = parse_artifact(path)

    findings: list[Finding] = []

    filename_date_match = RE_DAILY_FILENAME_DATE.search(path.name)
    filename_date = filename_date_match.group(1) if filename_date_match else None
    title_date: str | None = None
    if filename_date is not None:
        for idx, line in enumerate(lines, start=1):
            title_match = RE_TITLE_DATE.match(line.strip())
            if title_match:
                title_date = title_match.group(1)
                if title_date != filename_date:
                    findings.append(
                        Finding(
                            path=path,
                            line_no=idx,
                            message=(
                                "daily report title date mismatch: "
                                f"expected {filename_date}, found {title_date}"
                            ),
                        )
                    )
                break
        if title_date is None:
            findings.append(
                Finding(
                    path=path,
                    line_no=1,
                    message=(
                        "daily report title missing date: "
                        f"expected {filename_date} in top heading"
                    ),
                )
            )

    for idx, line in enumerate(lines, start=1):
        if RE_FORBIDDEN_TASK_HEADING.match(line):
            findings.append(
                Finding(
                    path=path,
                    line_no=idx,
                    message="forbidden heading: do not allocate TASK-### ids in assessment artifacts",
                )
            )

    proposal_starts = [(proposal.line_no, proposal.proposal_id) for proposal in artifact.proposals]
    for line_no, proposal_id in proposal_starts:
        if filename_date is None:
            continue
        date_match = RE_PROPOSAL_DATE.match(proposal_id)
        if date_match is None:
            findings.append(
                Finding(
                    path=path,
                    line_no=line_no,
                    message=(
                        f"{proposal_id}: missing YYYY-MM-DD segment matching "
                        f"filename date {filename_date}"
                    ),
                )
            )
        elif date_match.group(1) != filename_date:
            findings.append(
                Finding(
                    path=path,
                    line_no=line_no,
                    message=(
                        f"{proposal_id}: proposal date mismatch "
                        f"(expected {filename_date}, found {date_match.group(1)})"
                    ),
                )
            )

    if not proposal_starts:
        if artifact.is_all_clear:
            return findings
        findings.append(
            Finding(
                path=path,
                line_no=1,
                message="no proposals found (expected ### PROPOSAL-* or ### FINDING-*, or an explicit 'All clear')",
            )
        )
        return findings

    for index, (start_line_no, proposal_id) in enumerate(proposal_starts):
        end_line_no = (
            proposal_starts[index + 1][0] - 1 if index + 1 < len(proposal_starts) else len(lines)
        )
        block_lines = lines[start_line_no:end_line_no]
        fields, _sections = parse_block_content(block_lines, start_line_no)

        missing = sorted(REQUIRED_FIELDS - set(fields.keys()))
        if missing:
            findings.append(
                Finding(
                    path=path,
                    line_no=start_line_no,
                    message=f"{proposal_id}: missing required fields: {', '.join(missing)}",
                )
            )
            continue

        area = fields["area"].strip().lower()
        if area not in ALLOWED_AREAS:
            findings.append(
                Finding(
                    path=path,
                    line_no=start_line_no,
                    message=(
                        f"{proposal_id}: invalid area '{fields['area']}' "
                        f"(allowed: {', '.join(sorted(ALLOWED_AREAS))})"
                    ),
                )
            )

        priority = fields["priority"].strip().upper()
        if not RE_PRIORITY.match(priority):
            findings.append(
                Finding(
                    path=path,
                    line_no=start_line_no,
                    message=f"{proposal_id}: invalid priority '{fields['priority']}' (expected P0..P3)",
                )
            )

        confidence = parse_confidence(fields["confidence"])
        if confidence is None:
            findings.append(
                Finding(
                    path=path,
                    line_no=start_line_no,
                    message=(
                        f"{proposal_id}: invalid confidence '{fields['confidence']}' "
                        "(expected float in [0,1])"
                    ),
                )
            )

        gate = fields["recommended_gate"].strip().upper()
        if gate not in ALLOWED_GATES:
            findings.append(
                Finding(
                    path=path,
                    line_no=start_line_no,
                    message=(
                        f"{proposal_id}: invalid recommended_gate "
                        f"'{fields['recommended_gate']}' (allowed: {', '.join(sorted(ALLOWED_GATES))})"
                    ),
                )
            )

        for non_empty_key in ("estimate", "verification", "blast_radius"):
            if not fields[non_empty_key].strip():
                findings.append(
                    Finding(
                        path=path,
                        line_no=start_line_no,
                        message=f"{proposal_id}: '{non_empty_key}' must be non-empty",
                    )
                )

    return findings
