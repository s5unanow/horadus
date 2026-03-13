"""CLI orchestration and result assembly for assessment artifact validation."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from .artifacts import iter_markdown_files
from .grounding import grounding_findings_for_file
from .novelty import novelty_findings_for_file
from .overlap import cross_role_overlap_findings_for_file
from .schema_validation import validate_file

if TYPE_CHECKING:
    from .models import Finding


def build_parser() -> argparse.ArgumentParser:
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
    return parser


def collect_findings(
    files: list[Path],
    *,
    check_novelty: bool,
    check_sprint_grounding: bool,
    check_cross_role_overlap: bool,
    lookback_days: int,
    repo_root: Path,
) -> list[Finding]:
    all_findings: list[Finding] = []
    for file_path in files:
        all_findings.extend(validate_file(file_path))
        if check_novelty:
            all_findings.extend(
                novelty_findings_for_file(
                    file_path,
                    lookback_days=lookback_days,
                    all_files=files,
                    repo_root=repo_root,
                )
            )
        if check_sprint_grounding:
            all_findings.extend(grounding_findings_for_file(file_path, repo_root=repo_root))
        if check_cross_role_overlap:
            all_findings.extend(
                cross_role_overlap_findings_for_file(
                    file_path,
                    lookback_days=lookback_days,
                    all_files=files,
                    repo_root=repo_root,
                )
            )
    return all_findings


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.lookback_days < 0:
        parser.error("--lookback-days must be non-negative")

    paths = [Path(path_arg) for path_arg in args.paths]
    files = [path for path in iter_markdown_files(paths) if path.exists()]
    if not files:
        print("No assessment artifacts found to validate.")
        return 0

    all_findings = collect_findings(
        files,
        check_novelty=args.check_novelty,
        check_sprint_grounding=args.check_sprint_grounding,
        check_cross_role_overlap=args.check_cross_role_overlap,
        lookback_days=args.lookback_days,
        repo_root=Path.cwd(),
    )

    if all_findings:
        for finding in all_findings:
            rel = finding.path.as_posix()
            print(f"{rel}:{finding.line_no}: {finding.message}")
        print(f"Found {len(all_findings)} violation(s) across {len(files)} file(s).")
        return 0 if args.warn_only else 2

    print(f"Assessment validation passed: {len(files)} file(s).")
    return 0
