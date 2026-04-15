#!/usr/bin/env python3
# ruff: noqa: E402
"""Validate docstring requirements for selected high-value Python surfaces."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.horadus.python.horadus_workflow.docstring_policy import (
    render_docstring_policy_issues,
    run_docstring_policy_check,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check docstring policy for selected high-value Python surfaces."
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root path (defaults to current directory).",
    )
    parser.add_argument(
        "--policy-file",
        default="config/quality/docstring_policy.toml",
        help="Path to the docstring policy TOML file.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    result = run_docstring_policy_check(
        repo_root=repo_root,
        policy_path=(repo_root / args.policy_file).resolve(),
    )

    for line in render_docstring_policy_issues(result):
        print(line)

    if result.errors:
        return 2

    print("Docstring policy check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
