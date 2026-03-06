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
from datetime import date, timedelta
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
RE_FIELD_LINE = re.compile(r"^\s*([A-Za-z_ ]+)\s*:\s*(.*?)\s*$")
RE_DAILY_FILENAME_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})\.md$")
RE_TITLE_DATE = re.compile(r"^#\s+.+?(\d{4}-\d{2}-\d{2})\s*$")
RE_PROPOSAL_DATE = re.compile(r"^(?:PROPOSAL|FINDING)-(\d{4}-\d{2}-\d{2})-")
RE_TASK_REFERENCE = re.compile(r"\bTASK-\d{3}\b")
RE_SPRINT_DATES = re.compile(
    r"^\*\*Sprint Dates\*\*:\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})\s*$"
)
RE_ACTIVE_SPRINT_TASK = re.compile(r"^-\s+`(TASK-\d{3})`")

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

FIELD_ALIASES = {
    "proposal_id": "proposal_id",
    "area": "area",
    "priority": "priority",
    "confidence": "confidence",
    "estimate": "estimate",
    "recommended_gate": "recommended_gate",
    "verification": "verification",
    "blast_radius": "blast_radius",
    "blast radius": "blast_radius",
}
NON_FIELD_SECTION_ALIASES = {
    "problem",
    "proposed_change",
    "proposed change",
    "summary",
    "delta",
    "delta since prior report",
    "delta_since_prior_report",
    "new evidence",
    "new_evidence",
    "change since last report",
    "change_since_last_report",
    "updated scope",
    "updated_scope",
    "scope reviewed",
    "scope_reviewed",
}
TOKEN_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}
DELTA_HINT_PATTERN = re.compile(
    r"\b(delta since prior report|new evidence|change since last report|updated scope)\b",
    re.IGNORECASE,
)
CURRENT_TASK_ASSERTION_PATTERN = re.compile(
    r"\b(active|current|remaining|open|overdue|blocker|blockers|human-gated|"
    r"launch blocker|still|today|next_action|decision required)\b",
    re.IGNORECASE,
)
HISTORICAL_TASK_MARKER_PATTERN = re.compile(
    r"(?:\[(?:historical|completed|closed)\]|"
    r"\b(?:historical|completed|closed|prior|previous|earlier|former|formerly|"
    r"past|reference(?:d)?|carryover|already implemented)\b)",
    re.IGNORECASE,
)
ROLE_PREFIXES = {"po", "ba", "sa", "security", "agents"}
RE_TASK_TITLE = re.compile(r"^###\s+(TASK-\d+):\s+(.+?)\s*$")
RE_COMPLETED_TASK = re.compile(r"^-\s+(TASK-\d+):\s+(.+?)\s+✅\s*$")
SLUG_SIMILARITY_THRESHOLD = 0.6
BODY_SIMILARITY_THRESHOLD = 0.72


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


def _iter_markdown_files(paths: list[Path]) -> list[Path]:
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


def _parse_confidence(value: str) -> float | None:
    try:
        confidence = float(value.strip())
    except ValueError:
        return None
    if 0.0 <= confidence <= 1.0:
        return confidence
    return None


def _normalize_field_key(raw_key: str) -> str | None:
    normalized = " ".join(raw_key.strip().lower().split())
    return FIELD_ALIASES.get(normalized)


def _normalize_non_field_section(raw_key: str) -> str | None:
    normalized = " ".join(raw_key.strip().lower().split())
    if normalized in NON_FIELD_SECTION_ALIASES:
        return normalized.replace(" ", "_")
    return None


def _parse_block_content(
    block_lines: list[str], start_line_no: int
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
            field_key = _normalize_field_key(raw_key)
            non_field_key = _normalize_non_field_section(raw_key)

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


def _role_from_path(path: Path) -> str | None:
    parts = path.parts
    for index, part in enumerate(parts):
        if part == "assessments" and index + 2 < len(parts):
            return parts[index + 1]
    return None


def _parse_artifact(path: Path) -> ParsedArtifact:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    proposal_starts: list[tuple[int, str]] = []
    for idx, line in enumerate(lines, start=1):
        match = RE_PROPOSAL_HEADING.match(line)
        if match:
            proposal_starts.append((idx, match.group(1)))

    proposals: list[ProposalBlock] = []
    for i, (start_line_no, proposal_id) in enumerate(proposal_starts):
        end_line_no = proposal_starts[i + 1][0] - 1 if i + 1 < len(proposal_starts) else len(lines)
        block_lines = lines[start_line_no:end_line_no]
        fields, sections = _parse_block_content(block_lines, start_line_no)
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
        role=_role_from_path(path),
        is_all_clear=bool(RE_ALL_CLEAR.search(text)),
        proposals=tuple(proposals),
    )


def _normalize_slug(proposal_id: str) -> str:
    match = RE_PROPOSAL_DATE.match(proposal_id)
    slug = proposal_id
    if match:
        slug = proposal_id.split("-", 4)[4]
    parts = [part for part in slug.split("-") if part]
    if parts and parts[0] in ROLE_PREFIXES:
        parts = parts[1:]
    return "-".join(parts)


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in TOKEN_STOPWORDS and len(token) > 1
    }


def _token_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    intersection = left & right
    union = left | right
    return len(intersection) / len(union)


def _proposal_body_text(proposal: ProposalBlock) -> str:
    return "\n".join(
        [
            proposal.sections.get("problem", ""),
            proposal.sections.get("proposed_change", ""),
            proposal.fields.get("verification", ""),
            proposal.fields.get("blast_radius", ""),
        ]
    ).strip()


def _proposal_has_explicit_delta(proposal: ProposalBlock) -> bool:
    for key in (
        "delta",
        "delta_since_prior_report",
        "new_evidence",
        "change_since_last_report",
        "updated_scope",
    ):
        if proposal.sections.get(key, "").strip():
            return True
    return bool(DELTA_HINT_PATTERN.search(_proposal_body_text(proposal)))


def _artifact_file_date(path: Path) -> date | None:
    match = RE_DAILY_FILENAME_DATE.search(path.name)
    if match is None:
        return None
    return date.fromisoformat(match.group(1))


def _load_task_titles(repo_root: Path) -> list[tuple[str, str]]:
    titles: list[tuple[str, str]] = []
    for relative_path in ("tasks/BACKLOG.md", "tasks/COMPLETED.md"):
        path = repo_root / relative_path
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            backlog_match = RE_TASK_TITLE.match(line.strip())
            if backlog_match:
                titles.append((backlog_match.group(1), backlog_match.group(2).strip()))
                continue
            completed_match = RE_COMPLETED_TASK.match(line.strip())
            if completed_match:
                titles.append((completed_match.group(1), completed_match.group(2).strip()))
    return titles


def _load_current_sprint_truth(
    repo_root: Path,
) -> tuple[dict[str, int], tuple[date, date] | None]:
    sprint_path = repo_root / "tasks/CURRENT_SPRINT.md"
    if not sprint_path.exists():
        return {}, None

    active_tasks: dict[str, int] = {}
    sprint_window: tuple[date, date] | None = None
    in_active_tasks = False

    for line_no, line in enumerate(sprint_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        sprint_match = RE_SPRINT_DATES.match(stripped)
        if sprint_match:
            sprint_window = (
                date.fromisoformat(sprint_match.group(1)),
                date.fromisoformat(sprint_match.group(2)),
            )
            continue

        if stripped == "## Active Tasks":
            in_active_tasks = True
            continue

        if in_active_tasks and stripped.startswith("## "):
            break

        if not in_active_tasks:
            continue

        task_match = RE_ACTIVE_SPRINT_TASK.match(stripped)
        if task_match:
            active_tasks[task_match.group(1)] = line_no

    return active_tasks, sprint_window


def _history_artifacts_for_file(
    artifact: ParsedArtifact,
    *,
    lookback_days: int,
    all_files: list[Path],
    repo_root: Path,
    include_same_role: bool,
) -> list[ParsedArtifact]:
    normalized_target_path = artifact.path.resolve()
    file_date = _artifact_file_date(artifact.path)
    cutoff = file_date - timedelta(days=lookback_days) if file_date is not None else None
    assessments_root = repo_root / "artifacts" / "assessments"
    candidate_history_files = (
        _iter_markdown_files([assessments_root]) if assessments_root.exists() else all_files
    )

    history: list[ParsedArtifact] = []
    for candidate in candidate_history_files:
        if candidate.resolve() == normalized_target_path:
            continue

        candidate_artifact = _parse_artifact(candidate)
        if artifact.role is None or candidate_artifact.role is None:
            continue

        same_role = candidate_artifact.role == artifact.role
        if include_same_role and not same_role:
            continue
        if not include_same_role and same_role:
            continue

        candidate_date = _artifact_file_date(candidate)
        if cutoff is not None and candidate_date is not None and candidate_date < cutoff:
            continue
        if file_date is not None and candidate_date is not None and candidate_date > file_date:
            continue

        history.append(candidate_artifact)

    return history


def _similar_history_match(
    proposal: ProposalBlock,
    *,
    history: list[ParsedArtifact],
) -> tuple[ProposalBlock, Path, float] | None:
    slug_tokens = _tokenize(_normalize_slug(proposal.proposal_id))
    body_tokens = _tokenize(_proposal_body_text(proposal))

    prior_match: tuple[ProposalBlock, Path, float] | None = None
    for previous in history:
        for previous_proposal in previous.proposals:
            prev_slug_tokens = _tokenize(_normalize_slug(previous_proposal.proposal_id))
            prev_body_tokens = _tokenize(_proposal_body_text(previous_proposal))
            slug_similarity = _token_similarity(slug_tokens, prev_slug_tokens)
            body_similarity = _token_similarity(body_tokens, prev_body_tokens)
            if (
                slug_similarity >= SLUG_SIMILARITY_THRESHOLD
                or body_similarity >= BODY_SIMILARITY_THRESHOLD
            ):
                score = max(slug_similarity, body_similarity)
                if prior_match is None or score > prior_match[2]:
                    prior_match = (previous_proposal, previous.path, score)

    return prior_match


def _grounding_findings_for_file(path: Path, *, repo_root: Path) -> list[Finding]:
    file_date = _artifact_file_date(path)
    active_tasks, sprint_window = _load_current_sprint_truth(repo_root)
    if file_date is None or sprint_window is None:
        return []

    sprint_start, sprint_end = sprint_window
    if not (sprint_start <= file_date <= sprint_end):
        return []

    findings: list[Finding] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        task_ids = RE_TASK_REFERENCE.findall(line)
        if not task_ids:
            continue
        if not CURRENT_TASK_ASSERTION_PATTERN.search(line):
            continue
        if HISTORICAL_TASK_MARKER_PATTERN.search(line):
            continue

        for task_id in task_ids:
            if task_id in active_tasks:
                continue
            findings.append(
                Finding(
                    path=path,
                    line_no=line_no,
                    message=(
                        f"{task_id}: referenced as current/active/blocking but not present in "
                        "tasks/CURRENT_SPRINT.md Active Tasks. Use current sprint truth for live "
                        "references, or mark historical references explicitly with "
                        "[historical]/[completed]."
                    ),
                )
            )

    return findings


def _novelty_findings_for_file(
    path: Path,
    *,
    lookback_days: int,
    all_files: list[Path],
    repo_root: Path,
) -> list[Finding]:
    artifact = _parse_artifact(path)
    if artifact.is_all_clear or not artifact.proposals or artifact.role is None:
        return []

    history = _history_artifacts_for_file(
        artifact,
        lookback_days=lookback_days,
        all_files=all_files,
        repo_root=repo_root,
        include_same_role=True,
    )

    task_titles = _load_task_titles(repo_root)
    findings: list[Finding] = []
    novel_count = 0

    for proposal in artifact.proposals:
        if _proposal_has_explicit_delta(proposal):
            novel_count += 1
            continue

        slug_tokens = _tokenize(_normalize_slug(proposal.proposal_id))
        prior_match = _similar_history_match(proposal, history=history)

        if prior_match is not None:
            findings.append(
                Finding(
                    path=path,
                    line_no=proposal.line_no,
                    message=(
                        f"{proposal.proposal_id}: non-novel within {lookback_days} days; "
                        f"matches prior same-role proposal {prior_match[0].proposal_id} in "
                        f"{prior_match[1].as_posix()} (similarity {prior_match[2]:.2f}). "
                        "Add an explicit delta section or emit 'All clear'."
                    ),
                )
            )
            continue

        task_match: tuple[str, str, float] | None = None
        for task_id, task_title in task_titles:
            task_tokens = _tokenize(task_title)
            score = _token_similarity(slug_tokens, task_tokens)
            if (
                score >= SLUG_SIMILARITY_THRESHOLD
                or (len(slug_tokens & task_tokens) >= 2 and score >= 0.5)
            ) and (task_match is None or score > task_match[2]):
                task_match = (task_id, task_title, score)

        if task_match is not None:
            findings.append(
                Finding(
                    path=path,
                    line_no=proposal.line_no,
                    message=(
                        f"{proposal.proposal_id}: already captured in task ledger by "
                        f"{task_match[0]} ({task_match[1]}) (similarity {task_match[2]:.2f}); "
                        "adjust the proposal with an explicit delta or emit 'All clear'."
                    ),
                )
            )
            continue

        novel_count += 1

    if novel_count == 0:
        findings.append(
            Finding(
                path=path,
                line_no=1,
                message=(
                    f"no materially new proposals remain after {lookback_days}-day novelty "
                    "check; emit an explicit 'All clear' report instead."
                ),
            )
        )

    return findings


def _cross_role_overlap_findings_for_file(
    path: Path,
    *,
    lookback_days: int,
    all_files: list[Path],
    repo_root: Path,
) -> list[Finding]:
    artifact = _parse_artifact(path)
    if artifact.is_all_clear or not artifact.proposals or artifact.role is None:
        return []

    history = _history_artifacts_for_file(
        artifact,
        lookback_days=lookback_days,
        all_files=all_files,
        repo_root=repo_root,
        include_same_role=False,
    )
    if not history:
        return []

    findings: list[Finding] = []
    novel_count = 0
    for proposal in artifact.proposals:
        if _proposal_has_explicit_delta(proposal):
            novel_count += 1
            continue

        prior_match = _similar_history_match(proposal, history=history)
        if prior_match is None:
            novel_count += 1
            continue

        prior_role = _role_from_path(prior_match[1]) or "unknown"
        findings.append(
            Finding(
                path=path,
                line_no=proposal.line_no,
                message=(
                    f"{proposal.proposal_id}: overlaps with recent {prior_role} proposal "
                    f"{prior_match[0].proposal_id} in {prior_match[1].as_posix()} "
                    f"(similarity {prior_match[2]:.2f}). Suppress the duplicate, record the "
                    "suppression in automation memory/log output, add an explicit delta, or "
                    "emit 'All clear'."
                ),
            )
        )

    if novel_count == 0:
        findings.append(
            Finding(
                path=path,
                line_no=1,
                message=(
                    f"no materially new cross-role proposals remain after {lookback_days}-day "
                    "overlap check; emit an explicit 'All clear' report instead."
                ),
            )
        )

    return findings


def validate_file(path: Path) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    artifact = _parse_artifact(path)

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
        # Allow a deliberate "no findings" report.
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

    # Parse each proposal block until next ### heading (or EOF).
    for i, (start_line_no, proposal_id) in enumerate(proposal_starts):
        end_line_no = proposal_starts[i + 1][0] - 1 if i + 1 < len(proposal_starts) else len(lines)
        block_lines = lines[start_line_no:end_line_no]

        fields, _sections = _parse_block_content(block_lines, start_line_no)

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
    parser.add_argument(
        "--check-novelty",
        action="store_true",
        help="Check whether proposal blocks are materially new versus recent same-role history.",
    )
    parser.add_argument(
        "--check-sprint-grounding",
        action="store_true",
        help=(
            "Check TASK-### references against tasks/CURRENT_SPRINT.md when the artifact date "
            "falls inside the current sprint window."
        ),
    )
    parser.add_argument(
        "--check-cross-role-overlap",
        action="store_true",
        help=("Check whether proposal blocks duplicate recent other-role assessment coverage."),
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=7,
        help="Lookback window for novelty checks (default: 7).",
    )
    args = parser.parse_args(argv)

    if args.lookback_days < 0:
        parser.error("--lookback-days must be non-negative")

    paths = [Path(p) for p in args.paths]
    files = [p for p in _iter_markdown_files(paths) if p.exists()]
    if not files:
        # Nothing to validate is not an error; it might simply be early adoption.
        print("No assessment artifacts found to validate.")
        return 0

    all_findings: list[Finding] = []
    for file_path in files:
        all_findings.extend(validate_file(file_path))
        if args.check_novelty:
            all_findings.extend(
                _novelty_findings_for_file(
                    file_path,
                    lookback_days=args.lookback_days,
                    all_files=files,
                    repo_root=Path.cwd(),
                )
            )
        if args.check_sprint_grounding:
            all_findings.extend(_grounding_findings_for_file(file_path, repo_root=Path.cwd()))
        if args.check_cross_role_overlap:
            all_findings.extend(
                _cross_role_overlap_findings_for_file(
                    file_path,
                    lookback_days=args.lookback_days,
                    all_files=files,
                    repo_root=Path.cwd(),
                )
            )

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
