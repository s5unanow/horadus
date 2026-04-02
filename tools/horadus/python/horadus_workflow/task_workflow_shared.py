from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess  # nosec B404
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.horadus.python.horadus_workflow import review_defaults, task_repo
from tools.horadus.python.horadus_workflow.result import ExitCode

TASK_BRANCH_PATTERN = re.compile(r"^codex/task-(?P<number>\d{3})-[a-z0-9][a-z0-9._-]*$")
DEFAULT_CHECKS_TIMEOUT_SECONDS = 1800
DEFAULT_CHECKS_POLL_SECONDS = 10
DEFAULT_REVIEW_POLL_SECONDS = 10
DEFAULT_REVIEW_BOT_LOGIN = "chatgpt-codex-connector[bot]"
DEFAULT_REVIEW_TIMEOUT_POLICY = "allow"
DEFAULT_REVIEW_TIMEOUT_SECONDS = review_defaults.DEFAULT_REVIEW_TIMEOUT_SECONDS
REVIEW_TIMEOUT_OVERRIDE_APPROVAL_ENV = "HORADUS_HUMAN_APPROVED_REVIEW_TIMEOUT_OVERRIDE"
FINISH_DEBUG_ENV = "HORADUS_FINISH_DEBUG"
DEFAULT_FINISH_REVIEW_GATE_GRACE_SECONDS = 30
DEFAULT_FINISH_MERGE_COMMAND_TIMEOUT_SECONDS = 120
DEFAULT_DOCKER_READY_TIMEOUT_SECONDS = 120
DEFAULT_DOCKER_READY_POLL_SECONDS = 2
FRICTION_LOG_DIRECTORY = Path("artifacts/agent/horadus-cli-feedback")
FRICTION_LOG_FILENAME = "entries.jsonl"
FRICTION_SUMMARY_DIRECTORY = FRICTION_LOG_DIRECTORY / "daily"
INTAKE_LOG_DIRECTORY = Path("artifacts/agent/task-intake")
INTAKE_LOG_FILENAME = "entries.jsonl"
VALID_FRICTION_TYPES: tuple[str, ...] = (
    "missing_cli_surface",
    "forced_fallback",
    "docs_gap",
    "confusing_output",
    "unexpected_blocker",
)


class CommandTimeoutError(RuntimeError):
    def __init__(
        self,
        command: list[str],
        timeout_seconds: float,
        *,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        self.command = list(command)
        self.timeout_seconds = timeout_seconds
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(f"Command timed out after {timeout_seconds}s: {shlex.join(self.command)}")

    def output_lines(self) -> list[str]:
        text = "\n".join(
            part.strip() for part in (self.stdout, self.stderr) if part is not None and part.strip()
        )
        return text.splitlines() if text else []


@dataclass(slots=True)
class FinishContext:
    branch_name: str
    branch_task_id: str
    task_id: str
    current_branch: str | None = None
    recovered_pr_url: str | None = None
    recovered_pr_state: str | None = None


@dataclass(slots=True)
class FinishConfig:
    gh_bin: str
    git_bin: str
    python_bin: str
    checks_timeout_seconds: int
    checks_poll_seconds: int
    review_timeout_seconds: int
    review_poll_seconds: int
    review_bot_login: str
    review_timeout_policy: str


@dataclass(slots=True)
class ReviewGateResult:
    status: str
    reason: str
    reviewer_login: str
    reviewed_head_oid: str
    current_head_oid: str
    clean_current_head_review: bool
    summary_thumbs_up: bool
    actionable_comment_count: int
    actionable_review_count: int
    timeout_seconds: int
    timed_out: bool
    summary: str
    informational_lines: list[str]
    actionable_lines: list[str]
    wait_window_started_at: str | None = None
    deadline_at: str | None = None
    remaining_seconds: int | None = None


@dataclass(slots=True)
class DockerStartPlan:
    description: str
    argv: list[str] | None = None
    shell_command: str | None = None


@dataclass(slots=True)
class DockerReadiness:
    ready: bool
    attempted_start: bool
    supported_auto_start: bool
    lines: list[str]


@dataclass(slots=True)
class TaskIntakeEntry:
    intake_id: str
    recorded_at: str
    title: str
    note: str
    refs: list[str]
    source_task_id: str | None
    status: str
    groom_notes: list[str]
    promoted_task_id: str | None


def _run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = False,
    timeout_seconds: float | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # nosec B603
            args,
            cwd=cwd or task_repo.repo_root(),
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        if timeout_seconds is None:
            raise RuntimeError("subprocess timed out without an explicit timeout value") from exc
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        raise CommandTimeoutError(
            args,
            timeout_seconds,
            stdout=stdout,
            stderr=stderr,
        ) from exc


def _run_command_with_timeout(
    args: list[str],
    *,
    timeout_seconds: float,
    cwd: Path | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return _run_command(
        args,
        cwd=cwd,
        check=check,
        timeout_seconds=timeout_seconds,
    )


def _run_shell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603
        ["/bin/bash", "-lc", command],
        cwd=task_repo.repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )


def _result_message(result: subprocess.CompletedProcess[str], fallback: str) -> str:
    return result.stderr.strip() or result.stdout.strip() or fallback


def _output_lines(result: subprocess.CompletedProcess[str]) -> list[str]:
    text = "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part is not None and part.strip()
    )
    return text.splitlines() if text else []


def _task_blocked(
    message: str,
    *,
    next_action: str,
    data: dict[str, object] | None = None,
    exit_code: int = ExitCode.VALIDATION_ERROR,
    extra_lines: list[str] | None = None,
) -> tuple[int, dict[str, object], list[str]]:
    lines = [f"Task finish blocked: {message}", f"Next action: {next_action}"]
    if extra_lines:
        lines.extend(extra_lines)
    return (exit_code, data or {}, lines)


def getenv(name: str) -> str | None:
    return os.environ.get(name)


def _truthy_env(name: str) -> bool:
    raw = getenv(name)
    return raw is not None and raw.strip().lower() in {"1", "true", "yes", "on"}


def _finish_debug_enabled() -> bool:
    return _truthy_env(FINISH_DEBUG_ENV)


def _finish_debug_line(message: str) -> str:
    timestamp = datetime.now(tz=UTC).isoformat(timespec="seconds")
    return f"[finish-debug {timestamp}] {message}"


def _compat_attr(name: str, fallback_module: object) -> Any:
    compat = sys.modules.get("tools.horadus.python.horadus_cli.task_workflow_core")
    if compat is not None and hasattr(compat, name):
        return getattr(compat, name)
    return getattr(fallback_module, name)  # pragma: no cover


def _read_int_env(name: str, default: int) -> int:
    raw = getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value < 0:
        raise ValueError(f"{name} must be non-negative.")
    return value


def _read_positive_int_env(name: str, default: int, *, command_name: str) -> int:
    value = _read_int_env(name, default)
    if value == 0:
        raise ValueError(f"{name} must be positive for `{command_name}`.")
    return value


def _read_review_timeout_seconds_env() -> int:
    value = _read_positive_int_env(
        "REVIEW_TIMEOUT_SECONDS",
        DEFAULT_REVIEW_TIMEOUT_SECONDS,
        command_name="horadus tasks finish",
    )
    if value == DEFAULT_REVIEW_TIMEOUT_SECONDS:
        return value

    approval_raw = getenv(REVIEW_TIMEOUT_OVERRIDE_APPROVAL_ENV)
    approval = approval_raw.strip().lower() if approval_raw is not None else ""
    if approval not in {"1", "true", "yes"}:
        raise ValueError(
            "REVIEW_TIMEOUT_SECONDS may differ from the default "
            f"{DEFAULT_REVIEW_TIMEOUT_SECONDS}s "
            f"({DEFAULT_REVIEW_TIMEOUT_SECONDS // 60} minutes) only when "
            f"{REVIEW_TIMEOUT_OVERRIDE_APPROVAL_ENV}=1 confirms an explicit human request."
        )
    return value


def _read_review_timeout_policy_env() -> str:
    raw = getenv("REVIEW_TIMEOUT_POLICY")
    if raw is None or not raw.strip():
        return DEFAULT_REVIEW_TIMEOUT_POLICY

    value = raw.strip().lower()
    if value != DEFAULT_REVIEW_TIMEOUT_POLICY:
        raise ValueError("REVIEW_TIMEOUT_POLICY must remain `allow` for `horadus tasks finish`.")
    return value


def _ensure_command_available(command: str) -> str | None:
    return shutil.which(command)


def _finish_config(*, enforce_review_timeout_override_policy: bool = True) -> FinishConfig:
    return FinishConfig(
        gh_bin=getenv("GH_BIN") or "gh",
        git_bin=getenv("GIT_BIN") or "git",
        python_bin=getenv("PYTHON_BIN") or sys.executable or "python3",
        checks_timeout_seconds=_read_int_env(
            "CHECKS_TIMEOUT_SECONDS", DEFAULT_CHECKS_TIMEOUT_SECONDS
        ),
        checks_poll_seconds=_read_int_env("CHECKS_POLL_SECONDS", DEFAULT_CHECKS_POLL_SECONDS),
        review_timeout_seconds=(
            _read_review_timeout_seconds_env()
            if enforce_review_timeout_override_policy
            else _read_positive_int_env(
                "REVIEW_TIMEOUT_SECONDS",
                DEFAULT_REVIEW_TIMEOUT_SECONDS,
                command_name="horadus tasks finish",
            )
        ),
        review_poll_seconds=_read_int_env("REVIEW_POLL_SECONDS", DEFAULT_REVIEW_POLL_SECONDS),
        review_bot_login=getenv("REVIEW_BOT_LOGIN") or DEFAULT_REVIEW_BOT_LOGIN,
        review_timeout_policy=_read_review_timeout_policy_env(),
    )


def _summarize_output_lines(lines: list[str], *, max_lines: int = 80) -> list[str]:
    if len(lines) <= max_lines:
        return lines
    head_count = 30
    tail_count = 30
    omitted = len(lines) - head_count - tail_count
    return [
        *lines[:head_count],
        f"... ({omitted} lines omitted) ...",
        *lines[-tail_count:],
    ]


def _task_id_from_branch_name(branch_name: str) -> str | None:
    match = TASK_BRANCH_PATTERN.match(branch_name)
    if match is None:
        return None
    return f"TASK-{match.group('number')}"


def _task_branch_pattern(task_id: str) -> str:
    return f"codex/task-{task_id[5:]}-*"


def _parse_git_branch_lines(text: str) -> list[str]:
    branches: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("*"):
            line = line[1:].strip()
        branches.append(line)
    return branches


def _parse_remote_branch_lines(text: str) -> list[str]:
    branches: list[str] = []
    for raw_line in text.splitlines():
        parts = raw_line.strip().split()
        if len(parts) != 2:
            continue
        ref = parts[1]
        if ref.startswith("refs/heads/"):
            branches.append(ref.removeprefix("refs/heads/"))
    return branches


def _check_rollup_state(entries: object) -> str:
    if not isinstance(entries, list) or not entries:
        return "none"

    has_pending = False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status") or "")
        conclusion = str(entry.get("conclusion") or "")
        if status != "COMPLETED":
            has_pending = True
            continue
        if conclusion and conclusion not in {"SUCCESS", "NEUTRAL", "SKIPPED"}:
            return "fail"
        if not conclusion:
            has_pending = True
    if has_pending:
        return "pending"
    return "pass"


def _docker_ready_timeout_seconds() -> int:
    return _read_int_env("DOCKER_READY_TIMEOUT_SECONDS", DEFAULT_DOCKER_READY_TIMEOUT_SECONDS)


def _docker_ready_poll_seconds() -> int:
    return _read_int_env("DOCKER_READY_POLL_SECONDS", DEFAULT_DOCKER_READY_POLL_SECONDS)


def _docker_start_plan() -> DockerStartPlan | None:
    override = getenv("HORADUS_DOCKER_START_CMD")
    if override and override.strip():
        return DockerStartPlan(
            description=f"custom start command `{override.strip()}`",
            shell_command=override.strip(),
        )
    if sys.platform == "darwin" and _ensure_command_available("open") is not None:
        return DockerStartPlan(description="macOS Docker Desktop", argv=["open", "-a", "Docker"])
    if _ensure_command_available("docker-desktop") is not None:
        return DockerStartPlan(
            description="docker-desktop CLI",
            argv=["docker-desktop", "start"],
        )
    return None


def _docker_info_result() -> subprocess.CompletedProcess[str]:
    return _run_command(["docker", "info"])


def ensure_docker_ready(*, reason: str) -> DockerReadiness:
    if _ensure_command_available("docker") is None:
        return DockerReadiness(
            ready=False,
            attempted_start=False,
            supported_auto_start=False,
            lines=[
                f"Docker readiness failed: docker CLI is required for {reason}.",
            ],
        )

    info_result = _docker_info_result()
    if info_result.returncode == 0:
        return DockerReadiness(
            ready=True,
            attempted_start=False,
            supported_auto_start=True,
            lines=[f"Docker is ready for {reason}."],
        )

    plan = _docker_start_plan()
    if plan is None:
        return DockerReadiness(
            ready=False,
            attempted_start=False,
            supported_auto_start=False,
            lines=[
                f"Docker daemon is not reachable for {reason}.",
                "Auto-start is unsupported on this environment; start Docker manually and retry.",
            ],
        )

    lines = [
        f"Docker daemon is not reachable for {reason}.",
        f"Attempting Docker auto-start via {plan.description}.",
    ]
    try:
        timeout_seconds = _docker_ready_timeout_seconds()
        poll_seconds = _docker_ready_poll_seconds()
    except ValueError as exc:
        return DockerReadiness(
            ready=False,
            attempted_start=False,
            supported_auto_start=True,
            lines=[f"Docker readiness failed: {exc}"],
        )

    if plan.shell_command is not None:
        start_result = _run_shell(plan.shell_command)
    else:
        assert plan.argv is not None
        start_result = _run_command(plan.argv)
    if start_result.returncode != 0:
        return DockerReadiness(
            ready=False,
            attempted_start=True,
            supported_auto_start=True,
            lines=[*lines, "Docker auto-start command failed.", *_output_lines(start_result)],
        )

    deadline = time.time() + timeout_seconds
    while True:
        info_result = _docker_info_result()
        if info_result.returncode == 0:
            return DockerReadiness(
                ready=True,
                attempted_start=True,
                supported_auto_start=True,
                lines=[*lines, "Docker became ready after auto-start."],
            )
        if time.time() >= deadline:
            return DockerReadiness(
                ready=False,
                attempted_start=True,
                supported_auto_start=True,
                lines=[
                    *lines,
                    "Docker auto-start did not make the daemon ready before timeout.",
                    *_output_lines(info_result),
                ],
            )
        if poll_seconds:
            time.sleep(poll_seconds)


__all__ = [
    "DEFAULT_CHECKS_POLL_SECONDS",
    "DEFAULT_CHECKS_TIMEOUT_SECONDS",
    "DEFAULT_DOCKER_READY_POLL_SECONDS",
    "DEFAULT_DOCKER_READY_TIMEOUT_SECONDS",
    "DEFAULT_FINISH_MERGE_COMMAND_TIMEOUT_SECONDS",
    "DEFAULT_FINISH_REVIEW_GATE_GRACE_SECONDS",
    "DEFAULT_REVIEW_BOT_LOGIN",
    "DEFAULT_REVIEW_POLL_SECONDS",
    "DEFAULT_REVIEW_TIMEOUT_POLICY",
    "DEFAULT_REVIEW_TIMEOUT_SECONDS",
    "FINISH_DEBUG_ENV",
    "FRICTION_LOG_DIRECTORY",
    "FRICTION_LOG_FILENAME",
    "FRICTION_SUMMARY_DIRECTORY",
    "INTAKE_LOG_DIRECTORY",
    "INTAKE_LOG_FILENAME",
    "REVIEW_TIMEOUT_OVERRIDE_APPROVAL_ENV",
    "TASK_BRANCH_PATTERN",
    "VALID_FRICTION_TYPES",
    "CommandTimeoutError",
    "DockerReadiness",
    "DockerStartPlan",
    "FinishConfig",
    "FinishContext",
    "ReviewGateResult",
    "TaskIntakeEntry",
    "_check_rollup_state",
    "_compat_attr",
    "_docker_info_result",
    "_docker_ready_poll_seconds",
    "_docker_ready_timeout_seconds",
    "_docker_start_plan",
    "_ensure_command_available",
    "_finish_config",
    "_finish_debug_enabled",
    "_finish_debug_line",
    "_output_lines",
    "_parse_git_branch_lines",
    "_parse_remote_branch_lines",
    "_read_int_env",
    "_read_positive_int_env",
    "_read_review_timeout_policy_env",
    "_read_review_timeout_seconds_env",
    "_result_message",
    "_run_command",
    "_run_command_with_timeout",
    "_run_shell",
    "_summarize_output_lines",
    "_task_blocked",
    "_task_branch_pattern",
    "_task_id_from_branch_name",
    "_truthy_env",
    "ensure_docker_ready",
    "getenv",
]
