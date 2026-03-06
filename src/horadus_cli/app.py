from __future__ import annotations

import argparse
from collections.abc import Sequence

from src.horadus_cli.legacy import register_legacy_commands
from src.horadus_cli.result import emit_result
from src.horadus_cli.task_commands import register_task_commands
from src.horadus_cli.triage_commands import register_triage_commands


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="horadus")
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=["text", "json"],
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and describe the command without making changes.",
    )
    subparsers = parser.add_subparsers(dest="command")
    register_legacy_commands(subparsers)
    register_task_commands(subparsers)
    register_triage_commands(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1
    result = handler(args)
    return emit_result(result, getattr(args, "output_format", "text"))
