from __future__ import annotations

from typing import Any

from tools.horadus.python.horadus_cli.task_query import handle_context_pack


def register_context_pack_parser(tasks_subparsers: Any, add_leaf_cli_options: Any) -> None:
    context_pack_parser = tasks_subparsers.add_parser(
        "context-pack",
        help="Show the task backlog/spec/sprint context pack.",
    )
    add_leaf_cli_options(context_pack_parser)
    context_pack_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    context_pack_parser.add_argument(
        "--include-archive",
        action="store_true",
        help="Allow archived backlog lookup when the task is no longer live.",
    )
    context_pack_parser.add_argument(
        "--mode",
        choices=["default", "implement"],
        default="default",
        help="Context-pack payload mode. Default preserves the broad legacy output.",
    )
    context_pack_parser.set_defaults(handler=handle_context_pack)


__all__ = ["register_context_pack_parser"]
