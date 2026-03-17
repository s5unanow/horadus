"""Focused recovery tests for scripts/check_pr_review_gate.py."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_pr_review_gate.py"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run_gate(
    *, env: dict[str, str], args: list[str] | None = None
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env.update(env)
    return subprocess.run(
        ["python", str(SCRIPT_PATH), *(args or [])],
        cwd=REPO_ROOT,
        env=merged_env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_review_gate_single_poll_reports_wait_status_with_deadline(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "gh",
        """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  repo)
    echo '{"nameWithOwner":"example/repo"}'
    ;;
  pr)
    echo '{"number":215,"headRefOid":"head-sha-215","url":"https://example.invalid/pr/215"}'
    ;;
  api)
    if [[ "${2:-}" == "repos/example/repo/pulls/215/reviews" ]]; then
      echo '[]'
      exit 0
    fi
    if [[ "${2:-}" == "repos/example/repo/pulls/215/comments" ]]; then
      echo '[]'
      exit 0
    fi
    if [[ "${2:-}" == "repos/example/repo/issues/215/comments" ]]; then
      echo '[]'
      exit 0
    fi
    if [[ "${2:-}" == "repos/example/repo/issues/215/reactions" ]]; then
      echo '[]'
      exit 0
    fi
    exit 1
    ;;
  *)
    exit 1
    ;;
esac
""",
    )

    result = _run_gate(
        env={
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "HORADUS_REVIEW_GATE_STATE_PATH": str(tmp_path / "review-gate-state.json"),
        },
        args=[
            "--pr-url",
            "https://example.invalid/pr/215",
            "--timeout-seconds",
            "30",
            "--poll-seconds",
            "0",
            "--single-poll",
            "--format",
            "json",
        ],
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "waiting"
    assert payload["reviewed_head_oid"] == "head-sha-215"
    assert payload["remaining_seconds"] > 0
    assert payload["deadline_at"]
    assert "Waiting for review gate" in payload["summary"]


def test_review_gate_single_poll_reuses_persisted_wait_window(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state_path = tmp_path / "review-gate-state.json"
    state_path.write_text(
        json.dumps(
            {
                "example/repo#215#chatgpt-codex-connector[bot]": {
                    "head_oid": "head-sha-215",
                    "started_at": "2020-01-01T00:00:00+00:00",
                }
            }
        )
    )
    _write_executable(
        bin_dir / "gh",
        """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  repo)
    echo '{"nameWithOwner":"example/repo"}'
    ;;
  pr)
    echo '{"number":215,"headRefOid":"head-sha-215","url":"https://example.invalid/pr/215"}'
    ;;
  api)
    echo '[]'
    ;;
  *)
    exit 1
    ;;
esac
""",
    )

    result = _run_gate(
        env={
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "HORADUS_REVIEW_GATE_STATE_PATH": str(state_path),
        },
        args=[
            "--pr-url",
            "https://example.invalid/pr/215",
            "--timeout-seconds",
            "1",
            "--poll-seconds",
            "0",
            "--single-poll",
            "--format",
            "json",
        ],
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["reason"] == "silent_timeout_allow"
    assert payload["timed_out"] is True


def test_review_gate_retries_unreadable_reaction_payload(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    reactions_count = tmp_path / "reactions.count"
    _write_executable(
        bin_dir / "gh",
        f"""#!/usr/bin/env bash
set -euo pipefail
case "${{1:-}}" in
  repo)
    echo '{{"nameWithOwner":"example/repo"}}'
    ;;
  pr)
    echo '{{"number":215,"headRefOid":"head-sha-215","url":"https://example.invalid/pr/215"}}'
    ;;
  api)
    if [[ "${{2:-}}" == "repos/example/repo/pulls/215/reviews" ]]; then
      echo '[]'
      exit 0
    fi
    if [[ "${{2:-}}" == "repos/example/repo/pulls/215/comments" ]]; then
      echo '[]'
      exit 0
    fi
    if [[ "${{2:-}}" == "repos/example/repo/issues/215/comments" ]]; then
      echo '[]'
      exit 0
    fi
    if [[ "${{2:-}}" == "repos/example/repo/issues/215/reactions" ]]; then
      count=0
      if [[ -f "{reactions_count}" ]]; then
        count="$(cat "{reactions_count}")"
      fi
      count="$((count + 1))"
      echo "$count" > "{reactions_count}"
      if [[ "$count" == "1" ]]; then
        echo '{{bad'
      else
        echo '[]'
      fi
      exit 0
    fi
    exit 1
    ;;
  *)
    exit 1
    ;;
esac
""",
    )

    result = _run_gate(
        env={
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "HORADUS_REVIEW_GATE_STATE_PATH": str(tmp_path / "review-gate-state.json"),
        },
        args=[
            "--pr-url",
            "https://example.invalid/pr/215",
            "--timeout-seconds",
            "30",
            "--poll-seconds",
            "0",
            "--single-poll",
            "--format",
            "json",
        ],
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "waiting"


def test_review_gate_reports_concrete_reaction_payload_failure(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "gh",
        """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  repo)
    echo '{"nameWithOwner":"example/repo"}'
    ;;
  pr)
    echo '{"number":215,"headRefOid":"head-sha-215","url":"https://example.invalid/pr/215"}'
    ;;
  api)
    if [[ "${2:-}" == "repos/example/repo/pulls/215/reviews" ]]; then
      echo '[]'
      exit 0
    fi
    if [[ "${2:-}" == "repos/example/repo/pulls/215/comments" ]]; then
      echo '[]'
      exit 0
    fi
    if [[ "${2:-}" == "repos/example/repo/issues/215/comments" ]]; then
      echo '[]'
      exit 0
    fi
    if [[ "${2:-}" == "repos/example/repo/issues/215/reactions" ]]; then
      echo '{bad'
      exit 0
    fi
    exit 1
    ;;
  *)
    exit 1
    ;;
esac
""",
    )

    result = _run_gate(
        env={
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "HORADUS_REVIEW_GATE_STATE_PATH": str(tmp_path / "review-gate-state.json"),
        },
        args=[
            "--pr-url",
            "https://example.invalid/pr/215",
            "--timeout-seconds",
            "30",
            "--poll-seconds",
            "0",
            "--single-poll",
            "--format",
            "json",
        ],
    )

    assert result.returncode == 1
    assert "Unable to parse PR summary reactions from gh output" in result.stderr
