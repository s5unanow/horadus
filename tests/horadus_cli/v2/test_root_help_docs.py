from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from tools.horadus.python.horadus_cli.app import _build_parser

pytestmark = pytest.mark.unit


def _root_command_help() -> dict[str, str]:
    parser = _build_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    return {action.dest: action.help for action in subparsers._choices_actions}


def test_root_help_describes_all_command_groups() -> None:
    help_text = " ".join(_build_parser().format_help().split())
    expected_descriptions = {
        "trends": "Inspect trend probabilities.",
        "dashboard": "Export dashboard artifacts.",
        "eval": "Run offline evals and validation checks.",
        "pipeline": "Run pipeline fixture exercises.",
        "agent": "Run local agent smoke checks.",
        "doctor": "Run local runtime diagnostics (hooks, config, DB, Redis, migration parity).",
        "tasks": "Repo task and sprint workflow helpers.",
        "triage": "Structured triage input collection.",
    }

    assert expected_descriptions == _root_command_help()
    for description in expected_descriptions.values():
        assert description in help_text


def test_runbook_root_command_surface_matches_parser() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    runbook = (repo_root / "docs" / "AGENT_RUNBOOK.md").read_text(encoding="utf-8")

    for command, description in _root_command_help().items():
        assert f"horadus {command}" in runbook
        assert description[:1].lower() + description[1:] in runbook
