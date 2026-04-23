from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.workflow.test_docs_freshness import _seed_repo_layout
from tools.horadus.python.horadus_workflow.docs_freshness import run_docs_freshness_check

pytestmark = pytest.mark.unit


def test_docs_freshness_flags_stale_agent_runbook_marker(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    stale_date = (datetime.now(tz=UTC) - timedelta(days=120)).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "docs" / "AGENT_RUNBOOK.md").write_text(
        f"**Last Verified**: {stale_date}\n",
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
        max_age_days=30,
    )

    assert any(
        issue.rule_id == "required_marker_stale" and issue.path == "docs/AGENT_RUNBOOK.md"
        for issue in result.errors
    )
