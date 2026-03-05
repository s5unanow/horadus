"""Unit tests for scripts/prepush_integration_gate.sh."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "prepush_integration_gate.sh"


def _run(*, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_prepush_gate_skips_when_skip_env_set() -> None:
    result = _run(extra_env={"HORADUS_SKIP_INTEGRATION_TESTS": "1"})
    assert result.returncode == 0
    assert "skipping integration test gate" in result.stdout


def test_prepush_gate_runs_runner_cmd_when_docker_check_disabled() -> None:
    result = _run(
        extra_env={
            "HORADUS_INTEGRATION_PREPUSH_REQUIRE_DOCKER": "false",
            "HORADUS_INTEGRATION_PREPUSH_CMD": "true",
        }
    )
    assert result.returncode == 0
    assert "running integration test gate" in result.stdout


def test_prepush_gate_fails_when_runner_cmd_fails_and_docker_check_disabled() -> None:
    result = _run(
        extra_env={
            "HORADUS_INTEGRATION_PREPUSH_REQUIRE_DOCKER": "false",
            "HORADUS_INTEGRATION_PREPUSH_CMD": "false",
        }
    )
    assert result.returncode != 0
