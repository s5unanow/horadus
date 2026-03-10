#!/usr/bin/env python3
"""
Validate docs freshness and runtime-consistency invariants.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.core.docs_freshness import run_docs_freshness_check


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check docs freshness and drift invariants.")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root path (defaults to current directory).",
    )
    parser.add_argument(
        "--override-file",
        default="docs/DOCS_FRESHNESS_OVERRIDES.json",
        help="Path to docs-freshness override JSON file.",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=45,
        help="Maximum allowed age for Last Verified/Last Updated markers.",
    )
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Treat warnings (e.g., active overrides) as CI failures.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    override_path = repo_root / args.override_file
    result = run_docs_freshness_check(
        repo_root=repo_root,
        override_path=override_path,
        max_age_days=max(1, args.max_age_days),
    )

    if result.warnings:
        print("Docs freshness warnings:")
        for issue in result.warnings:
            path_fragment = f" ({issue.path})" if issue.path else ""
            print(f"- [{issue.rule_id}] {issue.message}{path_fragment}")

    if result.errors:
        print("Docs freshness errors:")
        for issue in result.errors:
            path_fragment = f" ({issue.path})" if issue.path else ""
            print(f"- [{issue.rule_id}] {issue.message}{path_fragment}")
        return 2

    if args.fail_on_warnings and result.warnings:
        print("Failing due to --fail-on-warnings.")
        return 2

    print("Docs freshness check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
