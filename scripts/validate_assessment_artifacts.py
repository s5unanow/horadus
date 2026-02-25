#!/usr/bin/env python3
"""
Validate assessment artifacts under artifacts/assessments/ against a minimal schema.

This is intentionally lightweight: it enforces a stable "proposal block" format
that can be produced by role agents and consumed by triage automation.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

ALLOWED_AREAS = {
    "api",
    "core",
    "storage",
    "ingestion",
    "processing",
    "workers",
    "repo",
    "docs",
    "security",
    "ops",
}

ALLOWED_GATES = {"AUTO_OK", "HUMAN_REVIEW", "REQUIRES_HUMAN"}

RE_PROPOSAL_HEADING = re.compile(r"^###\s+((?:PROPOSAL|FINDING)-[A-Za-z0-9._:-]+)\s*$")
RE_FORBIDDEN_TASK_HEADING = re.compile(r"^###\s+TASK-\d{3}\b")
RE_KV = re.compile(r"^\s*([a-z_]+)\s*:\s*(.+?)\s*$", re.IGNORECASE)

RE_PRIORITY = re.compile(r"^P[0-3]$")

RE_ALL_CLEAR = re.compile(r"\ball clear\b", re.IGNORECASE)

REQUIRED_FIELDS = {
    "area",
    "priority",
    "confidence",
    "estimate",
    "verification",
    "blast_radius",
    "recommended_gate",
}


@dataclass(frozen=True)
class Finding:
    path: Path
    line_no: int
    message: str


def _iter_markdown_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("*.md")))
        else:
            files.append(path)
    return files


def _parse_confidence(value: str) -> float | None:
    try:
        confidence = float(value.strip())
    except ValueError:
        return None
    if 0.0 <= confidence <= 1.0:
        return confidence
    return None


def validate_file(path: Path) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    findings: list[Finding] = []

    for idx, line in enumerate(lines, start=1):
        if RE_FORBIDDEN_TASK_HEADING.match(line):
            findings.append(
                Finding(
                    path=path,
                    line_no=idx,
                    message="forbidden heading: do not allocate TASK-### ids in assessment artifacts",
                )
            )

    proposal_starts: list[tuple[int, str]] = []
    for idx, line in enumerate(lines, start=1):
        match = RE_PROPOSAL_HEADING.match(line)
        if match:
            proposal_starts.append((idx, match.group(1)))

    if not proposal_starts:
        # Allow a deliberate "no findings" report.
        if RE_ALL_CLEAR.search(text):
            return findings
        findings.append(
            Finding(
                path=path,
                line_no=1,
                message="no proposals found (expected ### PROPOSAL-* or ### FINDING-*, or an explicit 'All clear')",
            )
        )
        return findings

    # Parse each proposal block until next ### heading (or EOF).
    for i, (start_line_no, proposal_id) in enumerate(proposal_starts):
        end_line_no = proposal_starts[i + 1][0] - 1 if i + 1 < len(proposal_starts) else len(lines)
        block_lines = lines[start_line_no:end_line_no]

        fields: dict[str, str] = {}
        for _line_no, line in enumerate(block_lines, start=start_line_no + 1):
            kv = RE_KV.match(line)
            if not kv:
                continue
            key = kv.group(1).strip().lower()
            value = kv.group(2).strip()
            fields[key] = value

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
                    message=f"{proposal_id}: invalid area '{fields['area']}' (allowed: {', '.join(sorted(ALLOWED_AREAS))})",
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

        confidence = _parse_confidence(fields["confidence"])
        if confidence is None:
            findings.append(
                Finding(
                    path=path,
                    line_no=start_line_no,
                    message=f"{proposal_id}: invalid confidence '{fields['confidence']}' (expected float in [0,1])",
                )
            )

        gate = fields["recommended_gate"].strip().upper()
        if gate not in ALLOWED_GATES:
            findings.append(
                Finding(
                    path=path,
                    line_no=start_line_no,
                    message=f"{proposal_id}: invalid recommended_gate '{fields['recommended_gate']}' (allowed: {', '.join(sorted(ALLOWED_GATES))})",
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "paths",
        nargs="*",
        default=["artifacts/assessments"],
        help="Files or directories to validate (default: artifacts/assessments).",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Exit 0 even if violations are found.",
    )
    args = parser.parse_args(argv)

    paths = [Path(p) for p in args.paths]
    files = [p for p in _iter_markdown_files(paths) if p.exists()]
    if not files:
        # Nothing to validate is not an error; it might simply be early adoption.
        print("No assessment artifacts found to validate.")
        return 0

    all_findings: list[Finding] = []
    for file_path in files:
        all_findings.extend(validate_file(file_path))

    if all_findings:
        for finding in all_findings:
            rel = finding.path.as_posix()
            print(f"{rel}:{finding.line_no}: {finding.message}")
        print(f"Found {len(all_findings)} violation(s) across {len(files)} file(s).")
        return 0 if args.warn_only else 2

    print(f"Assessment validation passed: {len(files)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
