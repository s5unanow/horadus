#!/usr/bin/env python3
# ruff: noqa: E402
"""
Validate repo code-shape budgets and legacy-ratchet overrides.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.horadus.python.horadus_workflow.code_shape import (
    render_code_shape_issues,
    run_code_shape_check,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check repo code-shape budgets and ratchets.")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root path (defaults to current directory).",
    )
    parser.add_argument(
        "--policy-file",
        default="config/quality/code_shape.toml",
        help="Path to the code-shape policy TOML file.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    result = run_code_shape_check(
        repo_root=repo_root,
        policy_path=(repo_root / args.policy_file).resolve(),
    )

    for line in render_code_shape_issues(result):
        print(line)

    if result.errors:
        return 2

    print("Code shape check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
