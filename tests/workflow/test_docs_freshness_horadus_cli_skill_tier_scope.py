from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.workflow.test_docs_freshness import _seed_repo_layout
from tests.workflow.test_docs_freshness_horadus_cli_skill import _activate_horadus_cli_skill
from tools.horadus.python.horadus_workflow.docs_freshness import run_docs_freshness_check

pytestmark = pytest.mark.unit


def test_horadus_cli_skill_freshness_flags_missing_tier1_scope_token(
    tmp_path: Path,
) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    _activate_horadus_cli_skill(tmp_path)
    commands_path = tmp_path / "ops" / "skills" / "horadus-cli" / "references" / "commands.md"
    commands_path.write_text(
        commands_path.read_text(encoding="utf-8").replace("--tier-scope tier1", ""),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert any(
        issue.rule_id == "horadus_cli_skill_command_reference_missing"
        and "--tier-scope tier1" in issue.message
        for issue in result.errors
    )
