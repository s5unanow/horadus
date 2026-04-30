from __future__ import annotations

import pytest

from tools.horadus.python.horadus_cli.app import _build_parser

pytestmark = pytest.mark.unit


def test_build_parser_accepts_eval_benchmark_tier1_scope() -> None:
    parser = _build_parser()
    args = parser.parse_args(["eval", "benchmark", "--tier-scope", "tier1"])

    assert args.command == "eval"
    assert args.eval_command == "benchmark"
    assert args.tier_scope == "tier1"
