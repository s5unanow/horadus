from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess  # nosec B404
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from src.core.repo_workflow import canonical_task_workflow_commands_for_task
from src.horadus_cli.result import CommandResult, ExitCode
from src.horadus_cli.task_repo import (
    CLOSED_TASK_ARCHIVE_GUIDANCE,
    active_section_text,
    archived_task_record,
    backlog_path,
    closed_tasks_archive_path,
    completed_path,
    current_date,
    current_sprint_path,
    normalize_task_id,
    parse_active_tasks,
    parse_human_blockers,
    repo_root,
    search_task_records,
    slugify_name,
    task_block_match,
    task_record,
)

TASK_BRANCH_PATTERN = re.compile(r"^codex/task-(?P<number>\d{3})-[a-z0-9][a-z0-9._-]*$")
DEFAULT_CHECKS_TIMEOUT_SECONDS = 1800
DEFAULT_CHECKS_POLL_SECONDS = 10
DEFAULT_REVIEW_TIMEOUT_SECONDS = 600
DEFAULT_REVIEW_POLL_SECONDS = 10
DEFAULT_REVIEW_BOT_LOGIN = "chatgpt-codex-connector[bot]"
DEFAULT_REVIEW_TIMEOUT_POLICY = "allow"
REVIEW_TIMEOUT_OVERRIDE_APPROVAL_ENV = "HORADUS_HUMAN_APPROVED_REVIEW_TIMEOUT_OVERRIDE"
DEFAULT_FINISH_REVIEW_GATE_GRACE_SECONDS = 30
DEFAULT_FINISH_MERGE_COMMAND_TIMEOUT_SECONDS = 120
DEFAULT_DOCKER_READY_TIMEOUT_SECONDS = 120
DEFAULT_DOCKER_READY_POLL_SECONDS = 2
FRICTION_LOG_DIRECTORY = Path("artifacts/agent/horadus-cli-feedback")
FRICTION_LOG_FILENAME = "entries.jsonl"
FRICTION_SUMMARY_DIRECTORY = FRICTION_LOG_DIRECTORY / "daily"
VALID_FRICTION_TYPES: tuple[str, ...] = (
    "missing_cli_surface",
    "forced_fallback",
    "docs_gap",
    "confusing_output",
    "unexpected_blocker",
)
_CURRENT_SPRINT_PLACEHOLDER_PATTERN = re.compile(
    r"^-\s+Sprint opened on .*no Sprint .* tasks are complete yet\.$",
    re.MULTILINE,
)
_COMPLETED_TASKS_HEADER = "# Completed Tasks"
_CLOSED_TASK_ARCHIVE_STATUS_LINE = "**Status**: Archived closed-task ledger (non-authoritative)"
_SPRINT_NUMBER_PATTERN = re.compile(r"^\*\*Sprint Number\*\*:\s*(?P<number>\d+)\s*$", re.MULTILINE)


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
            cwd=cwd or repo_root(),
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
        cwd=repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )


@dataclass(slots=True)
class FinishContext:
    branch_name: str
    branch_task_id: str
    task_id: str
    current_branch: str | None = None


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
class LocalGateStep:
    name: str
    command: str


@dataclass(slots=True)
class DockerStartPlan:
    description: str
    argv: list[str] | None = None
    shell_command: str | None = None


@dataclass(slots=True)
class TaskPullRequest:
    number: int
    url: str
    state: str
    is_draft: bool
    head_ref_name: str
    head_ref_oid: str | None
    merge_commit_oid: str | None
    check_state: str


@dataclass(slots=True)
class TaskLifecycleSnapshot:
    task_id: str
    current_branch: str
    branch_name: str | None
    local_branch_names: list[str]
    remote_branch_names: list[str]
    remote_branch_exists: bool
    working_tree_clean: bool
    pr: TaskPullRequest | None
    local_main_sha: str | None
    remote_main_sha: str | None
    local_main_synced: bool | None
    merge_commit_available_locally: bool | None
    merge_commit_on_main: bool | None
    lifecycle_state: str
    strict_complete: bool


@dataclass(slots=True)
class DockerReadiness:
    ready: bool
    attempted_start: bool
    supported_auto_start: bool
    lines: list[str]


@dataclass(slots=True)
class WorkflowFrictionEntry:
    recorded_at: str
    task_id: str
    command_attempted: str
    fallback_used: str
    friction_type: str
    note: str
    suggested_improvement: str


@dataclass(slots=True)
class WorkflowFrictionPatternSummary:
    friction_type: str
    command_attempted: str
    fallback_used: str
    suggested_improvement: str
    count: int
    task_ids: list[str]
    notes: list[str]
    first_recorded_at: str
    last_recorded_at: str


@dataclass(slots=True)
class WorkflowFrictionImprovementSummary:
    suggested_improvement: str
    count: int
    task_ids: list[str]
    command_attempts: list[str]
    fallback_paths: list[str]
    friction_type_counts: dict[str, int]


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
    data: dict[str, Any] | None = None,
    exit_code: int = ExitCode.VALIDATION_ERROR,
    extra_lines: list[str] | None = None,
) -> tuple[int, dict[str, Any], list[str]]:
    lines = [f"Task finish blocked: {message}", f"Next action: {next_action}"]
    if extra_lines:
        lines.extend(extra_lines)
    return (exit_code, data or {}, lines)


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
            "REVIEW_TIMEOUT_SECONDS may differ from the default 600s (10 minutes) only when "
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


def _friction_log_path() -> Path:
    return repo_root() / FRICTION_LOG_DIRECTORY / FRICTION_LOG_FILENAME


def _friction_summary_path(report_date: date) -> Path:
    return repo_root() / FRICTION_SUMMARY_DIRECTORY / f"{report_date.isoformat()}.md"


def _parse_report_date(report_date_input: str | None) -> date:
    if report_date_input is None:
        return datetime.now(tz=UTC).date()
    try:
        return date.fromisoformat(report_date_input)
    except ValueError as exc:
        raise ValueError(
            f"Invalid report date {report_date_input!r}. Expected YYYY-MM-DD."
        ) from exc


def _parse_recorded_at(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _relative_display_path(path: Path) -> str:
    try:
        return str(path.relative_to(repo_root()))
    except ValueError:
        return str(path)


def _load_workflow_friction_entries(log_path: Path) -> list[WorkflowFrictionEntry]:
    if not log_path.exists():
        return []

    entries: list[WorkflowFrictionEntry] = []
    required_fields = {
        "recorded_at",
        "task_id",
        "command_attempted",
        "fallback_used",
        "friction_type",
        "note",
        "suggested_improvement",
    }
    for line_number, raw_line in enumerate(
        log_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid workflow friction JSON at line {line_number}: {exc.msg}."
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError(
                f"Invalid workflow friction entry at line {line_number}: expected a JSON object."
            )
        missing_fields = sorted(required_fields - payload.keys())
        if missing_fields:
            raise ValueError(
                "Invalid workflow friction entry at line "
                f"{line_number}: missing fields {', '.join(missing_fields)}."
            )
        entry = WorkflowFrictionEntry(
            recorded_at=str(payload["recorded_at"]),
            task_id=str(payload["task_id"]),
            command_attempted=str(payload["command_attempted"]),
            fallback_used=str(payload["fallback_used"]),
            friction_type=str(payload["friction_type"]),
            note=str(payload["note"]),
            suggested_improvement=str(payload["suggested_improvement"]),
        )
        _parse_recorded_at(entry.recorded_at)
        entries.append(entry)
    return entries


def _entries_for_report_date(
    entries: list[WorkflowFrictionEntry], report_date: date
) -> list[WorkflowFrictionEntry]:
    return [
        entry for entry in entries if _parse_recorded_at(entry.recorded_at).date() == report_date
    ]


def _summarize_workflow_friction(
    entries: list[WorkflowFrictionEntry],
) -> tuple[
    list[WorkflowFrictionPatternSummary],
    list[WorkflowFrictionImprovementSummary],
    Counter[str],
]:
    pattern_groups: dict[tuple[str, str, str, str], list[WorkflowFrictionEntry]] = {}
    improvement_groups: dict[str, list[WorkflowFrictionEntry]] = {}
    friction_type_counts: Counter[str] = Counter()

    for entry in entries:
        friction_type_counts[entry.friction_type] += 1
        pattern_key = (
            entry.friction_type,
            entry.command_attempted,
            entry.fallback_used,
            entry.suggested_improvement,
        )
        pattern_groups.setdefault(pattern_key, []).append(entry)
        improvement_groups.setdefault(entry.suggested_improvement, []).append(entry)

    pattern_summaries: list[WorkflowFrictionPatternSummary] = []
    for pattern_entries in pattern_groups.values():
        sorted_entries = sorted(
            pattern_entries, key=lambda item: _parse_recorded_at(item.recorded_at)
        )
        first_entry = sorted_entries[0]
        unique_notes: list[str] = []
        for item in sorted_entries:
            note = item.note.strip()
            if note and note not in unique_notes:
                unique_notes.append(note)
        pattern_summaries.append(
            WorkflowFrictionPatternSummary(
                friction_type=first_entry.friction_type,
                command_attempted=first_entry.command_attempted,
                fallback_used=first_entry.fallback_used,
                suggested_improvement=first_entry.suggested_improvement,
                count=len(sorted_entries),
                task_ids=sorted({item.task_id for item in sorted_entries}),
                notes=unique_notes[:3],
                first_recorded_at=sorted_entries[0].recorded_at,
                last_recorded_at=sorted_entries[-1].recorded_at,
            )
        )

    pattern_summaries.sort(
        key=lambda item: (-item.count, item.last_recorded_at, item.suggested_improvement)
    )

    improvement_summaries: list[WorkflowFrictionImprovementSummary] = []
    for suggested_improvement, grouped_entries in improvement_groups.items():
        type_counter = Counter(item.friction_type for item in grouped_entries)
        improvement_summaries.append(
            WorkflowFrictionImprovementSummary(
                suggested_improvement=suggested_improvement,
                count=len(grouped_entries),
                task_ids=sorted({item.task_id for item in grouped_entries}),
                command_attempts=sorted({item.command_attempted for item in grouped_entries}),
                fallback_paths=sorted({item.fallback_used for item in grouped_entries}),
                friction_type_counts=dict(sorted(type_counter.items())),
            )
        )

    improvement_summaries.sort(key=lambda item: (-item.count, item.suggested_improvement.lower()))
    return pattern_summaries, improvement_summaries, friction_type_counts


def _render_workflow_friction_summary(
    *,
    report_date: date,
    log_path: Path,
    report_path: Path,
    entries: list[WorkflowFrictionEntry],
    patterns: list[WorkflowFrictionPatternSummary],
    improvements: list[WorkflowFrictionImprovementSummary],
    friction_type_counts: Counter[str],
    missing_log: bool,
) -> str:
    window_start = datetime.combine(report_date, datetime.min.time(), tzinfo=UTC)
    window_end = window_start + timedelta(days=1)
    lines = [
        f"# Horadus Workflow Friction Summary - {report_date.isoformat()}",
        "",
        f"- Report date (UTC): `{report_date.isoformat()}`",
        f"- Summary window: `{window_start.isoformat().replace('+00:00', 'Z')}` to `{window_end.isoformat().replace('+00:00', 'Z')}`",
        f"- Source log: `{_relative_display_path(log_path)}`",
        f"- Summary path: `{_relative_display_path(report_path)}`",
        f"- Entries summarized: `{len(entries)}`",
        f"- Distinct grouped patterns: `{len(patterns)}`",
        "",
        "## Highlights",
    ]
    if missing_log:
        lines.append(
            "- No workflow friction log exists yet; this report is an empty daily checkpoint."
        )
    elif not entries:
        lines.append("- No workflow friction entries were recorded for this UTC day.")
    else:
        top_type, top_count = friction_type_counts.most_common(1)[0]
        lines.extend(
            [
                f"- Most common friction type: `{top_type}` (`{top_count}` entries).",
                f"- Candidate CLI/skill improvements surfaced: `{len(improvements)}`.",
                "- Human review is required before turning any candidate below into a backlog task.",
            ]
        )

    lines.extend(["", "## Grouped Patterns"])
    if not patterns:
        lines.append("- None for this report window.")
    else:
        for index, pattern in enumerate(patterns, start=1):
            notes = "; ".join(pattern.notes) if pattern.notes else "No extra notes recorded."
            lines.extend(
                [
                    f"### {index}. `{pattern.friction_type}` x{pattern.count}",
                    f"- Candidate improvement: {pattern.suggested_improvement}",
                    f"- Command attempted: `{pattern.command_attempted}`",
                    f"- Fallback used: `{pattern.fallback_used}`",
                    f"- Affected tasks: {', '.join(f'`{task_id}`' for task_id in pattern.task_ids)}",
                    f"- Observed notes: {notes}",
                ]
            )

    lines.extend(["", "## Candidate Improvements"])
    if not improvements:
        lines.append("- None. No follow-up candidates were generated for this report window.")
    else:
        for index, improvement in enumerate(improvements, start=1):
            friction_mix = ", ".join(
                f"`{friction_type}` x{count}"
                for friction_type, count in improvement.friction_type_counts.items()
            )
            commands = ", ".join(f"`{command}`" for command in improvement.command_attempts)
            lines.extend(
                [
                    f"{index}. {improvement.suggested_improvement}",
                    f"Seen in `{improvement.count}` entries across {', '.join(f'`{task_id}`' for task_id in improvement.task_ids)}.",
                    f"Friction mix: {friction_mix}",
                    f"Related commands: {commands}",
                ]
            )

    lines.extend(
        [
            "",
            "## Triage Guidance",
            "- Review this summary before proposing workflow follow-up work.",
            "- Do not auto-create backlog tasks from this report; backlog creation requires explicit human review.",
            "- Use the raw JSONL log only when deeper evidence is needed for a reviewed follow-up.",
            "",
            "## Proposed Follow-Up Seeds (Human Review Required)",
        ]
    )
    if not improvements:
        lines.append("- None for this report window.")
    else:
        for improvement in improvements:
            lines.append(
                "- Candidate task seed: "
                f"Investigate Horadus workflow friction around {improvement.suggested_improvement}."
            )

    return "\n".join(lines) + "\n"


def record_friction_data(
    *,
    task_input: str,
    command_attempted: str,
    fallback_used: str,
    friction_type: str,
    note: str,
    suggested_improvement: str,
    dry_run: bool,
) -> tuple[int, dict[str, Any], list[str]]:
    task_id = normalize_task_id(task_input)
    normalized_type = friction_type.strip().lower()
    if normalized_type not in VALID_FRICTION_TYPES:
        return (
            ExitCode.VALIDATION_ERROR,
            {"friction_type": friction_type, "valid_friction_types": list(VALID_FRICTION_TYPES)},
            [
                "Workflow friction logging failed.",
                (
                    "Unsupported friction type "
                    f"{friction_type!r}; expected one of: {', '.join(VALID_FRICTION_TYPES)}"
                ),
            ],
        )

    entry = WorkflowFrictionEntry(
        recorded_at=datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        task_id=task_id,
        command_attempted=command_attempted.strip(),
        fallback_used=fallback_used.strip(),
        friction_type=normalized_type,
        note=note.strip(),
        suggested_improvement=suggested_improvement.strip(),
    )
    log_path = _friction_log_path()
    relative_log_path = str(log_path.relative_to(repo_root()))
    lines = [
        f"Workflow friction log target: {relative_log_path}",
        "Record entries only for real Horadus workflow friction or forced fallback, not routine success cases.",
        "Friction entries remain in gitignored artifacts and are not source-of-truth task/spec/project records.",
        "Normal task execution should not require reading the friction log.",
    ]
    if dry_run:
        lines.append("Dry run: would append structured workflow friction entry.")
        return (
            ExitCode.OK,
            {"dry_run": True, "log_path": relative_log_path, "entry": entry},
            lines,
        )

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(entry), sort_keys=True) + "\n")
    except OSError as exc:
        lines.extend(
            [
                "Workflow friction logging failed while writing the gitignored artifact.",
                f"Filesystem error: {exc}",
            ]
        )
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {
                "dry_run": False,
                "log_path": relative_log_path,
                "entry": entry,
                "error": str(exc),
            },
            lines,
        )
    lines.append("Recorded structured workflow friction entry.")
    return (
        ExitCode.OK,
        {"dry_run": False, "log_path": relative_log_path, "entry": entry},
        lines,
    )


def summarize_friction_data(
    *,
    report_date_input: str | None,
    output_path_input: str | None,
    dry_run: bool,
) -> tuple[int, dict[str, Any], list[str]]:
    try:
        report_date = _parse_report_date(report_date_input)
    except ValueError as exc:
        return (ExitCode.VALIDATION_ERROR, {}, [str(exc)])

    log_path = _friction_log_path()
    missing_log = not log_path.exists()
    try:
        entries = _load_workflow_friction_entries(log_path)
    except ValueError as exc:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"log_path": _relative_display_path(log_path)},
            [f"Workflow friction summary failed: {exc}"],
        )
    except OSError as exc:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"log_path": _relative_display_path(log_path), "error": str(exc)},
            [
                "Workflow friction summary failed while reading the friction log artifact.",
                f"Filesystem error: {exc}",
            ],
        )

    filtered_entries = _entries_for_report_date(entries, report_date)
    patterns, improvements, friction_type_counts = _summarize_workflow_friction(filtered_entries)
    report_path = (
        Path(output_path_input).expanduser()
        if output_path_input is not None
        else _friction_summary_path(report_date)
    )
    if not report_path.is_absolute():
        report_path = repo_root() / report_path
    report_markdown = _render_workflow_friction_summary(
        report_date=report_date,
        log_path=log_path,
        report_path=report_path,
        entries=filtered_entries,
        patterns=patterns,
        improvements=improvements,
        friction_type_counts=friction_type_counts,
        missing_log=missing_log,
    )
    lines = [
        f"Workflow friction source: {_relative_display_path(log_path)}",
        f"Daily summary target: {_relative_display_path(report_path)}",
        "Human review remains required before creating backlog tasks from this summary.",
    ]
    data: dict[str, Any] = {
        "dry_run": dry_run,
        "report_date": report_date,
        "log_path": _relative_display_path(log_path),
        "report_path": _relative_display_path(report_path),
        "entry_count": len(filtered_entries),
        "pattern_count": len(patterns),
        "improvement_count": len(improvements),
        "missing_log": missing_log,
        "patterns": patterns,
        "improvements": improvements,
    }
    if dry_run:
        lines.append("Dry run: would write grouped workflow friction summary.")
        return (ExitCode.OK, data, lines)

    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_markdown, encoding="utf-8")
    except OSError as exc:
        lines.extend(
            [
                "Workflow friction summary failed while writing the report artifact.",
                f"Filesystem error: {exc}",
            ]
        )
        data["error"] = str(exc)
        return (ExitCode.ENVIRONMENT_ERROR, data, lines)

    lines.append("Wrote grouped workflow friction summary.")
    return (ExitCode.OK, data, lines)


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


def _ensure_command_available(command: str) -> str | None:
    return shutil.which(command)


def _resolve_finish_context(
    task_input: str | None, config: FinishConfig
) -> tuple[int, dict[str, Any], list[str]] | FinishContext:
    branch_result = _run_command([config.git_bin, "rev-parse", "--abbrev-ref", "HEAD"])
    if branch_result.returncode != 0:
        return _task_blocked(
            _result_message(branch_result, "Unable to determine current branch."),
            next_action="Resolve local git issues, then re-run `horadus tasks finish`.",
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    current_branch = branch_result.stdout.strip()
    if current_branch == "HEAD":
        return _task_blocked(
            "detached HEAD is not allowed.",
            next_action="Check out the task branch you want to finish, then re-run `horadus tasks finish`.",
            data={"current_branch": current_branch},
        )
    requested_task_id: str | None = None
    if task_input is not None:
        requested_task_id = normalize_task_id(task_input)
    if current_branch == "main":
        if requested_task_id is not None:
            lifecycle_result = resolve_task_lifecycle(requested_task_id, config=config)
            if isinstance(lifecycle_result, tuple):
                exit_code, data, lines = lifecycle_result
                return _task_blocked(
                    "unable to recover task context from 'main'.",
                    next_action=(
                        f"Restore the branch or PR state for {requested_task_id}, then re-run "
                        f"`horadus tasks finish {requested_task_id}`."
                    ),
                    data={"current_branch": current_branch, "task_id": requested_task_id, **data},
                    exit_code=exit_code,
                    extra_lines=lines,
                )
            if not lifecycle_result.working_tree_clean:
                return _task_blocked(
                    "working tree must be clean.",
                    next_action=(
                        "Commit or stash local changes, then re-run "
                        f"`horadus tasks finish {requested_task_id}`."
                    ),
                    data={"current_branch": current_branch, "task_id": requested_task_id},
                )
            if lifecycle_result.branch_name is None:
                return _task_blocked(
                    f"unable to resolve a task branch for {requested_task_id} from 'main'.",
                    next_action=(
                        f"Restore the task branch or open PR for {requested_task_id}, then re-run "
                        f"`horadus tasks finish {requested_task_id}`."
                    ),
                    data={"current_branch": current_branch, "task_id": requested_task_id},
                )
            return FinishContext(
                branch_name=lifecycle_result.branch_name,
                branch_task_id=requested_task_id,
                task_id=requested_task_id,
                current_branch=current_branch,
            )
        return _task_blocked(
            "refusing to run on 'main'.",
            next_action=(
                "Re-run `horadus tasks finish TASK-XXX` with an explicit task id, or switch to "
                "the task branch that owns the PR lifecycle you want to finish."
            ),
            data={"current_branch": current_branch},
        )

    match = TASK_BRANCH_PATTERN.match(current_branch)
    if match is None:
        return _task_blocked(
            (
                "branch does not match the required task pattern "
                f"`codex/task-XXX-short-name`: {current_branch}"
            ),
            next_action="Switch to a canonical task branch before running `horadus tasks finish`.",
            data={"current_branch": current_branch},
        )

    branch_task_id = f"TASK-{match.group('number')}"
    requested_task_id = branch_task_id
    if task_input is not None:
        requested_task_id = normalize_task_id(task_input)
        if requested_task_id != branch_task_id:
            return _task_blocked(
                (f"branch {current_branch} maps to {branch_task_id}, not {requested_task_id}."),
                next_action=(
                    f"Run `horadus tasks finish {branch_task_id}` on this branch, or switch to the "
                    f"branch for {requested_task_id}."
                ),
                data={
                    "current_branch": current_branch,
                    "branch_task_id": branch_task_id,
                    "task_id": requested_task_id,
                },
            )

    status_result = _run_command([config.git_bin, "status", "--porcelain"])
    if status_result.returncode != 0:
        return _task_blocked(
            _result_message(status_result, "Unable to determine working tree state."),
            next_action="Resolve local git issues, then re-run `horadus tasks finish`.",
            data={"branch_name": current_branch, "task_id": requested_task_id},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )
    if status_result.stdout.strip():
        return _task_blocked(
            "working tree must be clean.",
            next_action=(
                "Commit or stash local changes, then re-run "
                f"`horadus tasks finish {requested_task_id}`."
            ),
            data={"branch_name": current_branch, "task_id": requested_task_id},
        )

    return FinishContext(
        branch_name=current_branch,
        branch_task_id=branch_task_id,
        task_id=requested_task_id,
        current_branch=current_branch,
    )


def _run_pr_scope_guard(
    *, branch_name: str, pr_title: str, pr_body: str
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PR_BRANCH"] = branch_name
    env["PR_TITLE"] = pr_title
    env["PR_BODY"] = pr_body
    return subprocess.run(  # nosec B603
        ["./scripts/check_pr_task_scope.sh"],
        cwd=repo_root(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_review_gate(*, pr_url: str, config: FinishConfig) -> subprocess.CompletedProcess[str]:
    return _run_command_with_timeout(
        [
            config.python_bin,
            "./scripts/check_pr_review_gate.py",
            "--pr-url",
            pr_url,
            "--reviewer-login",
            config.review_bot_login,
            "--timeout-seconds",
            str(config.review_timeout_seconds),
            "--poll-seconds",
            str(config.review_poll_seconds),
            "--timeout-policy",
            config.review_timeout_policy,
        ],
        timeout_seconds=(
            config.review_timeout_seconds
            + max(config.review_poll_seconds, 1)
            + DEFAULT_FINISH_REVIEW_GATE_GRACE_SECONDS
        ),
    )


def _required_checks_state(*, pr_url: str, config: FinishConfig) -> tuple[str, list[str]]:
    result = _run_command(
        [
            config.gh_bin,
            "pr",
            "checks",
            pr_url,
            "--required",
            "--json",
            "bucket,name,link,workflow",
        ]
    )
    lines = _output_lines(result)
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        if result.returncode == 0:
            return ("pass", [])
        return ("pending", lines)

    if not isinstance(payload, list):
        if result.returncode == 0:
            return ("pass", [])
        return ("pending", lines)

    failed_checks: list[str] = []
    pending_checks: list[str] = []
    saw_checks = False
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        saw_checks = True
        bucket = str(entry.get("bucket") or "").strip().lower()
        name = str(entry.get("name") or "").strip() or "unnamed-check"
        workflow = str(entry.get("workflow") or "").strip()
        label = f"{workflow} / {name}" if workflow and workflow != name else name
        link = str(entry.get("link") or "").strip()
        detail = f"{label}: {bucket}"
        if link:
            detail = f"{detail} ({link})"
        if bucket in {"fail", "cancel"}:
            failed_checks.append(detail)
        elif bucket == "pending":
            pending_checks.append(detail)

    if failed_checks:
        return ("fail", failed_checks)
    if pending_checks:
        return ("pending", pending_checks)
    if result.returncode == 0:
        return ("pass", [])
    if saw_checks:
        return ("pending", lines)
    return ("pending", lines)


def _coerce_wait_for_required_checks_result(
    result: tuple[bool, list[str]] | tuple[bool, list[str], str],
) -> tuple[bool, list[str], str]:
    if len(result) == 2:
        checks_ok, check_lines = result
        return (checks_ok, check_lines, "pass" if checks_ok else "timeout")
    checks_ok, check_lines, reason = result
    return (checks_ok, check_lines, reason)


def _current_required_checks_blocker(
    *, pr_url: str, config: FinishConfig, block_pending: bool = True
) -> tuple[str, list[str]] | None:
    check_state, check_lines = _required_checks_state(pr_url=pr_url, config=config)
    if check_state == "fail":
        return (
            "required PR checks are failing on the current head.",
            check_lines,
        )
    if check_state == "pending" and block_pending:
        return (
            "required PR checks are still pending on the current head.",
            check_lines,
        )
    return None


def _unresolved_review_thread_lines(*, pr_url: str, config: FinishConfig) -> list[str]:
    repo_result = _run_command(
        [config.gh_bin, "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]
    )
    repo_name = repo_result.stdout.strip() if repo_result.returncode == 0 else ""
    if "/" not in repo_name:
        return []
    owner, repo = repo_name.split("/", 1)

    pr_number_result = _run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "number", "--jq", ".number"]
    )
    pr_number_raw = pr_number_result.stdout.strip() if pr_number_result.returncode == 0 else ""
    if not pr_number_raw.isdigit():
        return []

    query = (
        "query($owner:String!, $repo:String!, $number:Int!){"
        "repository(owner:$owner,name:$repo){"
        "pullRequest(number:$number){"
        "reviewThreads(first:100){"
        "nodes{"
        "isResolved "
        "comments(first:20){"
        "nodes{author{login} body path line originalLine url}"
        "}"
        "}"
        "}"
        "}"
        "}"
        "}"
    )
    threads_result = _run_command(
        [
            config.gh_bin,
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"repo={repo}",
            "-F",
            f"number={pr_number_raw}",
        ]
    )
    if threads_result.returncode != 0:
        return []
    try:
        payload = json.loads(threads_result.stdout or "{}")
    except json.JSONDecodeError:
        return []

    threads = (
        payload.get("data", {})
        .get("repository", {})
        .get("pullRequest", {})
        .get("reviewThreads", {})
        .get("nodes", [])
    )
    if not isinstance(threads, list):
        return []

    lines: list[str] = []
    for thread in threads:
        if not isinstance(thread, dict) or thread.get("isResolved") is True:
            continue
        comments = thread.get("comments", {}).get("nodes", [])
        if not isinstance(comments, list):
            continue
        comment = next((entry for entry in reversed(comments) if isinstance(entry, dict)), None)
        if comment is None:
            continue
        path = str(comment.get("path") or "<unknown>")
        line = comment.get("line") or comment.get("originalLine") or "?"
        url = str(comment.get("url") or "").strip()
        author = ""
        if isinstance(comment.get("author"), dict):
            author = str(comment["author"].get("login") or "").strip()
        header = f"- {path}:{line}"
        if url:
            header = f"{header} {url}"
        if author:
            header = f"{header} ({author})"
        lines.append(header)
        body = " ".join(str(comment.get("body") or "").strip().split())
        if body:
            lines.append(f"  {body}")
    return lines


def _maybe_request_fresh_review(*, pr_url: str, config: FinishConfig) -> list[str]:
    if config.review_bot_login != "chatgpt-codex-connector[bot]":
        return []
    request_comment = "@codex review"
    result = _run_command([config.gh_bin, "pr", "comment", pr_url, "--body", request_comment])
    if result.returncode != 0:
        return [
            f"Failed to request a fresh review from `{config.review_bot_login}` automatically.",
            *_output_lines(result),
        ]
    return [f"Requested a fresh review from `{config.review_bot_login}` with `{request_comment}`."]


def _wait_for_required_checks(*, pr_url: str, config: FinishConfig) -> tuple[bool, list[str], str]:
    deadline = time.time() + config.checks_timeout_seconds
    while True:
        check_state, check_lines = _required_checks_state(pr_url=pr_url, config=config)
        if check_state == "pass":
            return (True, [], "pass")
        if check_state == "fail":
            return (False, check_lines, "fail")
        if time.time() >= deadline:
            return (
                False,
                check_lines or ["`gh pr checks --required` did not report success before timeout."],
                "timeout",
            )
        if config.checks_poll_seconds:
            time.sleep(config.checks_poll_seconds)


def _wait_for_pr_state(
    *, pr_url: str, expected_state: str, config: FinishConfig
) -> tuple[bool, list[str]]:
    deadline = time.time() + config.checks_timeout_seconds
    while True:
        result = _run_command(
            [config.gh_bin, "pr", "view", pr_url, "--json", "state", "--jq", ".state"]
        )
        if result.returncode == 0 and result.stdout.strip() == expected_state:
            return (True, [])
        if time.time() >= deadline:
            return (
                False,
                _output_lines(result)
                or [f"PR did not reach state {expected_state!r} before timeout."],
            )
        if config.checks_poll_seconds:
            time.sleep(config.checks_poll_seconds)


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


def _check_rollup_state(entries: Any) -> str:
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
            lines=[
                f"Docker readiness failed: {exc}",
            ],
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
            lines=[
                *lines,
                "Docker auto-start command failed.",
                *_output_lines(start_result),
            ],
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


def _find_task_pull_request(
    *, task_id: str, config: FinishConfig
) -> tuple[int, dict[str, Any], list[str]] | TaskPullRequest | None:
    search_result = _run_command(
        [
            config.gh_bin,
            "pr",
            "list",
            "--state",
            "all",
            "--search",
            f"Primary-Task: {task_id} in:body",
            "--limit",
            "20",
            "--json",
            "number",
        ]
    )
    if search_result.returncode != 0:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"task_id": task_id},
            ["Task lifecycle failed.", "Unable to query GitHub pull requests."],
        )

    search_payload = json.loads(search_result.stdout or "[]")
    if not isinstance(search_payload, list) or not search_payload:
        return None

    pr_number = max(
        int(entry.get("number", 0))
        for entry in search_payload
        if isinstance(entry, dict) and entry.get("number") is not None
    )
    pr_result = _run_command(
        [
            config.gh_bin,
            "pr",
            "view",
            str(pr_number),
            "--json",
            "number,url,state,isDraft,headRefName,headRefOid,mergeCommit,statusCheckRollup",
        ]
    )
    if pr_result.returncode != 0:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"task_id": task_id, "pr_number": pr_number},
            ["Task lifecycle failed.", f"Unable to read GitHub PR #{pr_number}."],
        )

    payload = json.loads(pr_result.stdout or "{}")
    merge_commit = payload.get("mergeCommit")
    merge_commit_oid = None
    if isinstance(merge_commit, dict):
        raw_oid = merge_commit.get("oid")
        if raw_oid:
            merge_commit_oid = str(raw_oid)
    return TaskPullRequest(
        number=int(payload.get("number", pr_number)),
        url=str(payload.get("url") or ""),
        state=str(payload.get("state") or ""),
        is_draft=bool(payload.get("isDraft")),
        head_ref_name=str(payload.get("headRefName") or ""),
        head_ref_oid=str(payload.get("headRefOid") or "") or None,
        merge_commit_oid=merge_commit_oid,
        check_state=_check_rollup_state(payload.get("statusCheckRollup")),
    )


def task_lifecycle_state(snapshot: TaskLifecycleSnapshot) -> str:
    if snapshot.pr is not None:
        if snapshot.pr.state == "MERGED":
            if (
                snapshot.current_branch in {"main", "HEAD"}
                and snapshot.working_tree_clean
                and snapshot.local_main_synced
                and snapshot.merge_commit_on_main
            ):
                return "local-main-synced"
            return "merged"
        if snapshot.pr.state == "OPEN":
            if not snapshot.pr.is_draft and snapshot.pr.check_state == "pass":
                return "ci-green"
            return "pr-open"

    if snapshot.remote_branch_exists:
        return "pushed"
    return "local-only"


def resolve_task_lifecycle(
    task_input: str | None, *, config: FinishConfig
) -> tuple[int, dict[str, Any], list[str]] | TaskLifecycleSnapshot:
    branch_result = _run_command([config.git_bin, "rev-parse", "--abbrev-ref", "HEAD"])
    if branch_result.returncode != 0:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {},
            ["Task lifecycle failed.", "Unable to determine current branch."],
        )

    current_branch = branch_result.stdout.strip()
    if task_input is None:
        if current_branch == "HEAD":
            return (
                ExitCode.VALIDATION_ERROR,
                {"current_branch": current_branch},
                [
                    "Task lifecycle failed.",
                    "A task id is required when running from detached HEAD.",
                ],
            )
        inferred_task_id = _task_id_from_branch_name(current_branch)
        if inferred_task_id is None:
            return (
                ExitCode.VALIDATION_ERROR,
                {"current_branch": current_branch},
                [
                    "Task lifecycle failed.",
                    "A task id is required when the current branch is not a canonical task branch.",
                ],
            )
        task_id = inferred_task_id
    else:
        try:
            task_id = normalize_task_id(task_input)
        except ValueError as exc:
            return (ExitCode.VALIDATION_ERROR, {}, [str(exc)])

    branch_pattern = _task_branch_pattern(task_id)
    local_branch_result = _run_command([config.git_bin, "branch", "--list", branch_pattern])
    if local_branch_result.returncode != 0:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"task_id": task_id},
            ["Task lifecycle failed.", "Unable to inspect local task branches."],
        )
    local_branch_names = _parse_git_branch_lines(local_branch_result.stdout)

    remote_branch_result = _run_command(
        [config.git_bin, "ls-remote", "--heads", "origin", branch_pattern]
    )
    if remote_branch_result.returncode != 0:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"task_id": task_id},
            ["Task lifecycle failed.", "Unable to inspect remote task branches."],
        )
    remote_branch_names = _parse_remote_branch_lines(remote_branch_result.stdout)

    pr_result = _find_task_pull_request(task_id=task_id, config=config)
    if isinstance(pr_result, tuple):
        return pr_result
    pr = pr_result

    current_branch_task_id = _task_id_from_branch_name(current_branch)
    branch_name = None
    if current_branch_task_id == task_id:
        branch_name = current_branch
    elif pr is not None and pr.head_ref_name:
        branch_name = pr.head_ref_name
    elif local_branch_names:
        branch_name = local_branch_names[0]
    elif remote_branch_names:
        branch_name = remote_branch_names[0]

    if branch_name is None and pr is None:
        return (
            ExitCode.NOT_FOUND,
            {"task_id": task_id},
            [f"No local, remote, or PR lifecycle state found for {task_id}."],
        )

    status_result = _run_command([config.git_bin, "status", "--porcelain"])
    if status_result.returncode != 0:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"task_id": task_id},
            ["Task lifecycle failed.", "Unable to inspect working tree state."],
        )
    working_tree_clean = not status_result.stdout.strip()

    fetch_main_result = _run_command([config.git_bin, "fetch", "origin", "main", "--quiet"])
    if fetch_main_result.returncode != 0:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"task_id": task_id},
            ["Task lifecycle failed.", "Unable to refresh origin/main before verification."],
        )

    local_main_result = _run_command([config.git_bin, "rev-parse", "main"])
    remote_main_result = _run_command([config.git_bin, "rev-parse", "origin/main"])
    local_main_sha = local_main_result.stdout.strip() if local_main_result.returncode == 0 else None
    remote_main_sha = (
        remote_main_result.stdout.strip() if remote_main_result.returncode == 0 else None
    )
    local_main_synced = None
    if local_main_sha and remote_main_sha:
        local_main_synced = local_main_sha == remote_main_sha

    merge_commit_available_locally = None
    merge_commit_on_main = None
    if pr is not None and pr.merge_commit_oid:
        merge_commit_available_locally = (
            _run_command([config.git_bin, "cat-file", "-e", pr.merge_commit_oid]).returncode == 0
        )
        merge_commit_on_main = (
            merge_commit_available_locally
            and _run_command(
                [config.git_bin, "merge-base", "--is-ancestor", pr.merge_commit_oid, "main"]
            ).returncode
            == 0
        )

    remote_branch_exists = (
        branch_name in remote_branch_names if branch_name else bool(remote_branch_names)
    )
    snapshot = TaskLifecycleSnapshot(
        task_id=task_id,
        current_branch=current_branch,
        branch_name=branch_name,
        local_branch_names=local_branch_names,
        remote_branch_names=remote_branch_names,
        remote_branch_exists=remote_branch_exists,
        working_tree_clean=working_tree_clean,
        pr=pr,
        local_main_sha=local_main_sha,
        remote_main_sha=remote_main_sha,
        local_main_synced=local_main_synced,
        merge_commit_available_locally=merge_commit_available_locally,
        merge_commit_on_main=merge_commit_on_main,
        lifecycle_state="",
        strict_complete=False,
    )
    snapshot.lifecycle_state = task_lifecycle_state(snapshot)
    snapshot.strict_complete = snapshot.lifecycle_state == "local-main-synced"
    return snapshot


def full_local_gate_steps() -> list[LocalGateStep]:
    uv_bin = shlex.quote(getenv("UV_BIN") or "uv")
    return [
        LocalGateStep(
            name="check-tracked-artifacts",
            command="./scripts/check_no_tracked_artifacts.sh",
        ),
        LocalGateStep(
            name="docs-freshness",
            command=f"{uv_bin} run --no-sync python scripts/check_docs_freshness.py",
        ),
        LocalGateStep(
            name="ruff-format-check",
            command=f"{uv_bin} run --no-sync ruff format src/ tests/ --check",
        ),
        LocalGateStep(
            name="ruff-check",
            command=f"{uv_bin} run --no-sync ruff check src/ tests/",
        ),
        LocalGateStep(
            name="mypy",
            command=f"{uv_bin} run --no-sync mypy src/",
        ),
        LocalGateStep(
            name="validate-taxonomy",
            command=(
                f"{uv_bin} run --no-sync horadus eval validate-taxonomy "
                "--gold-set ai/eval/gold_set.jsonl "
                "--trend-config-dir config/trends "
                "--output-dir ai/eval/results "
                "--max-items 200 "
                "--tier1-trend-mode subset "
                "--signal-type-mode warn "
                "--unknown-trend-mode warn"
            ),
        ),
        LocalGateStep(
            name="pytest-unit-cov",
            command="./scripts/run_unit_coverage_gate.sh",
        ),
        LocalGateStep(
            name="bandit",
            command=f"{uv_bin} run --no-sync bandit -c pyproject.toml -r src/",
        ),
        LocalGateStep(
            name="lockfile-check",
            command=f"{uv_bin} lock --check",
        ),
        LocalGateStep(
            name="integration-docker",
            command="./scripts/test_integration_docker.sh",
        ),
        LocalGateStep(
            name="build-package",
            command=(
                "rm -rf dist build *.egg-info && "
                f"{uv_bin} run --no-sync --with build python -m build && "
                f"{uv_bin} run --no-sync --with twine twine check dist/*"
            ),
        ),
    ]


def local_gate_data(*, full: bool, dry_run: bool) -> tuple[int, dict[str, Any], list[str]]:
    if not full:
        return (
            ExitCode.VALIDATION_ERROR,
            {"full": False},
            [
                "Local gate selection failed.",
                "Use `horadus tasks local-gate --full` for the canonical post-task local gate.",
            ],
        )

    if _ensure_command_available(getenv("UV_BIN") or "uv") is None:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"missing_command": getenv("UV_BIN") or "uv"},
            ["Local gate failed: uv is required to run the canonical full local gate."],
        )

    steps = full_local_gate_steps()
    lines = [
        "Running canonical full local gate:",
        *[f"- {step.name}: {step.command}" for step in steps],
    ]
    if dry_run:
        lines.append("Dry run: validated the canonical step list without executing it.")
        return (
            ExitCode.OK,
            {
                "mode": "full",
                "dry_run": True,
                "steps": [asdict(step) for step in steps],
            },
            lines,
        )

    progress_lines = ["Running canonical full local gate:"]
    for index, step in enumerate(steps, start=1):
        progress_lines.append(f"[{index}/{len(steps)}] RUN {step.name}")
        if step.name == "integration-docker":
            docker_readiness = ensure_docker_ready(reason="the integration-docker local gate step")
            progress_lines.extend(docker_readiness.lines)
            if not docker_readiness.ready:
                return (
                    ExitCode.ENVIRONMENT_ERROR,
                    {
                        "mode": "full",
                        "failed_step": step.name,
                        "command": step.command,
                        "steps": [asdict(item) for item in steps],
                        "docker_ready": False,
                    },
                    [
                        *progress_lines,
                        "Local gate failed because Docker is not ready for the integration step.",
                    ],
                )
        result = _run_shell(step.command)
        if result.returncode != 0:
            output_lines = _summarize_output_lines(_output_lines(result))
            return (
                ExitCode.ENVIRONMENT_ERROR,
                {
                    "mode": "full",
                    "failed_step": step.name,
                    "command": step.command,
                    "steps": [asdict(item) for item in steps],
                },
                [
                    *progress_lines,
                    f"Local gate failed at step `{step.name}`.",
                    f"Command: {step.command}",
                    *output_lines,
                ],
            )
        progress_lines.append(f"[{index}/{len(steps)}] PASS {step.name}")

    progress_lines.append("Full local gate passed.")
    return (
        ExitCode.OK,
        {
            "mode": "full",
            "dry_run": False,
            "steps": [asdict(step) for step in steps],
        },
        progress_lines,
    )


def _ensure_required_hooks() -> tuple[bool, list[str]]:
    hooks_dir = repo_root() / ".git" / "hooks"
    required = ("pre-commit", "pre-push", "commit-msg")
    missing: list[str] = []
    for hook_name in required:
        hook_path = hooks_dir / hook_name
        if (
            not hook_path.exists()
            or not hook_path.is_file()
            or not hook_path.stat().st_mode & 0o111
        ):
            missing.append(hook_name)
    return (not missing, missing)


def _open_task_prs() -> tuple[bool, list[str] | str]:
    result = _run_command(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--base",
            "main",
            "--author",
            "@me",
            "--search",
            "head:codex/task-",
            "--limit",
            "100",
            "--json",
            "number,headRefName,url",
        ]
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "unknown gh error"
        return (False, message)
    payload = json.loads(result.stdout or "[]")
    open_prs = [
        f"#{entry['number']} {entry['headRefName']} {entry['url']}"
        for entry in payload
        if str(entry.get("headRefName", "")).startswith("codex/task-")
    ]
    return (True, open_prs)


def task_preflight_data() -> tuple[int, dict[str, Any], list[str]]:
    if getenv("SKIP_TASK_SEQUENCE_GUARD") == "1":
        data = {"skipped": True}
        return (ExitCode.OK, data, ["Task sequencing guard skipped (SKIP_TASK_SEQUENCE_GUARD=1)."])

    gh_path = shutil.which("gh")
    if gh_path is None:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"missing_command": "gh"},
            ["Task sequencing guard failed.", "GitHub CLI (gh) is required for open-PR checks."],
        )

    hooks_ok, missing_hooks = _ensure_required_hooks()
    if not hooks_ok:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"missing_hooks": missing_hooks},
            [
                "Task sequencing guard failed.",
                f"Required local git hooks are missing: {', '.join(missing_hooks)}.",
            ],
        )

    branch_result = _run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    current_branch = branch_result.stdout.strip()
    if current_branch != "main":
        return (
            ExitCode.VALIDATION_ERROR,
            {"current_branch": current_branch},
            [
                "Task sequencing guard failed.",
                f"You must start tasks from 'main'. Current branch: {current_branch}",
            ],
        )

    status_result = _run_command(["git", "status", "--porcelain"])
    if status_result.stdout.strip():
        return (
            ExitCode.VALIDATION_ERROR,
            {"working_tree_clean": False},
            [
                "Task sequencing guard failed.",
                "Working tree must be clean before starting a new task branch.",
            ],
        )

    fetch_result = _run_command(["git", "fetch", "origin", "main", "--quiet"])
    if fetch_result.returncode != 0:
        message = fetch_result.stderr.strip() or fetch_result.stdout.strip() or "git fetch failed"
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"fetch_error": message},
            ["Task sequencing guard failed.", message],
        )

    local_sha = _run_command(["git", "rev-parse", "HEAD"]).stdout.strip()
    remote_sha = _run_command(["git", "rev-parse", "origin/main"]).stdout.strip()
    if local_sha != remote_sha:
        return (
            ExitCode.VALIDATION_ERROR,
            {"local_main_sha": local_sha, "remote_main_sha": remote_sha},
            ["Task sequencing guard failed.", "Local main is not synced to origin/main."],
        )

    if getenv("ALLOW_OPEN_TASK_PRS") != "1":
        ok, pr_result = _open_task_prs()
        if not ok:
            return (
                ExitCode.ENVIRONMENT_ERROR,
                {"open_pr_query_error": pr_result},
                ["Task sequencing guard failed.", "Unable to query open PRs via GitHub CLI."],
            )
        if pr_result:
            return (
                ExitCode.VALIDATION_ERROR,
                {"open_task_prs": pr_result},
                [
                    "Task sequencing guard failed.",
                    "Open non-merged task PR(s) already exist for current user:",
                    *list(pr_result),
                ],
            )

    return (
        ExitCode.OK,
        {
            "gh_path": gh_path,
            "working_tree_clean": True,
            "local_main_sha": local_sha,
            "remote_main_sha": remote_sha,
        },
        ["Task sequencing guard passed: main is clean/synced and no open task PRs."],
    )


def getenv(name: str) -> str | None:
    import os

    return os.environ.get(name)


def _preflight_result() -> CommandResult:
    exit_code, data, lines = task_preflight_data()
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def eligibility_data(task_input: str) -> tuple[int, dict[str, Any], list[str]]:
    task_id = normalize_task_id(task_input)
    sprint_file = Path(getenv("TASK_ELIGIBILITY_SPRINT_FILE") or current_sprint_path())
    if not sprint_file.exists():
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"sprint_file": str(sprint_file)},
            [f"Missing sprint file: {sprint_file}"],
        )

    try:
        _ = active_section_text(sprint_file)
    except ValueError as exc:
        return (ExitCode.VALIDATION_ERROR, {"sprint_file": str(sprint_file)}, [str(exc)])

    matched_task = next(
        (task for task in parse_active_tasks(sprint_file) if task.task_id == task_id), None
    )
    if matched_task is None:
        return (
            ExitCode.VALIDATION_ERROR,
            {"task_id": task_id, "sprint_file": str(sprint_file)},
            [f"{task_id} is not listed in Active Tasks ({sprint_file})"],
        )
    if matched_task.requires_human:
        return (
            ExitCode.VALIDATION_ERROR,
            {"task_id": task_id, "requires_human": True},
            [f"{task_id} is marked [REQUIRES_HUMAN] and is not eligible for autonomous start"],
        )

    preflight_override = getenv("TASK_ELIGIBILITY_PREFLIGHT_CMD")
    if preflight_override and preflight_override != "./scripts/check_task_start_preflight.sh":
        preflight_result = _run_shell(preflight_override)
        if preflight_result.returncode != 0:
            return (
                ExitCode.VALIDATION_ERROR,
                {"task_id": task_id, "preflight_cmd": preflight_override},
                [f"Task sequencing preflight failed for {task_id}."],
            )
    else:
        preflight_exit, preflight_data, preflight_lines = task_preflight_data()
        if preflight_exit != ExitCode.OK:
            return (
                preflight_exit,
                {"task_id": task_id, "preflight": preflight_data},
                [*preflight_lines, f"Task sequencing preflight failed for {task_id}."],
            )

    return (
        ExitCode.OK,
        {"task_id": task_id, "sprint_file": str(sprint_file), "requires_human": False},
        [f"Agent task eligibility passed: {task_id}"],
    )


def start_task_data(
    task_input: str, raw_name: str, *, dry_run: bool
) -> tuple[int, dict[str, Any], list[str]]:
    task_id = normalize_task_id(task_input)
    slug = slugify_name(raw_name)
    branch_name = f"codex/task-{task_id[5:]}-{slug}"

    preflight_exit, preflight_data, preflight_lines = task_preflight_data()
    if preflight_exit != ExitCode.OK:
        return (
            preflight_exit,
            {"branch_name": branch_name, "preflight": preflight_data},
            preflight_lines,
        )

    local_exists = (
        _run_command(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"]
        ).returncode
        == 0
    )
    if local_exists:
        return (
            ExitCode.VALIDATION_ERROR,
            {"branch_name": branch_name},
            [f"Branch already exists locally: {branch_name}"],
        )

    remote_exists = (
        _run_command(
            ["git", "ls-remote", "--exit-code", "--heads", "origin", branch_name]
        ).returncode
        == 0
    )
    if remote_exists:
        return (
            ExitCode.VALIDATION_ERROR,
            {"branch_name": branch_name},
            [f"Branch already exists on origin: {branch_name}"],
        )

    lines = ["Task sequencing guard passed: main is clean/synced and no open task PRs."]
    if dry_run:
        lines.append(f"Dry run: would create task branch {branch_name}")
        return (
            ExitCode.OK,
            {"task_id": task_id, "branch_name": branch_name, "dry_run": True},
            lines,
        )

    switch_result = _run_command(["git", "switch", "-c", branch_name])
    if switch_result.returncode != 0:
        message = (
            switch_result.stderr.strip() or switch_result.stdout.strip() or "git switch failed"
        )
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"task_id": task_id, "branch_name": branch_name, "error": message},
            [message],
        )

    lines.extend(
        [
            f"Switched to a new branch '{branch_name}'",
            f"Created task branch: {branch_name}",
        ]
    )
    return (
        ExitCode.OK,
        {"task_id": task_id, "branch_name": branch_name, "dry_run": False},
        lines,
    )


def safe_start_task_data(
    task_input: str, raw_name: str, *, dry_run: bool
) -> tuple[int, dict[str, Any], list[str]]:
    task_id = normalize_task_id(task_input)

    eligibility_exit, eligibility_data_payload, eligibility_lines = eligibility_data(task_id)
    if eligibility_exit != ExitCode.OK:
        return (eligibility_exit, eligibility_data_payload, eligibility_lines)

    start_exit, start_data_payload, start_lines = start_task_data(
        task_id, raw_name, dry_run=dry_run
    )
    return (start_exit, start_data_payload, [*eligibility_lines, *start_lines])


def _replace_h2_section(content: str, heading: str, body: str) -> str:
    pattern = re.compile(
        rf"(^##\s+{re.escape(heading)}\s*\n)(?P<body>.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if match is None:
        raise ValueError(f"Unable to locate section '{heading}'")
    normalized_body = body.rstrip("\n")
    replacement = f"{match.group(1)}{normalized_body}\n\n"
    return f"{content[: match.start()]}{replacement}{content[match.end() :]}"


def _extract_h2_section_body(content: str, heading: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*\n(?P<body>.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if match is None:
        raise ValueError(f"Unable to locate section '{heading}'")
    return match.group("body")


def _extract_sprint_number(content: str) -> str:
    match = _SPRINT_NUMBER_PATTERN.search(content)
    if match is None:
        raise ValueError("Unable to determine sprint number from tasks/CURRENT_SPRINT.md")
    return match.group("number")


def _remove_task_lines(section_body: str, task_id: str) -> str:
    kept_lines = [line for line in section_body.splitlines() if task_id not in line]
    return "\n".join(kept_lines).strip("\n")


def _append_completed_sprint_line(section_body: str, task_id: str, title: str) -> str:
    target_line = f"- `{task_id}` {title} ✅"
    lines = [
        line
        for line in section_body.splitlines()
        if line.strip() and _CURRENT_SPRINT_PLACEHOLDER_PATTERN.match(line.strip()) is None
    ]
    if target_line not in lines:
        lines.append(target_line)
    return "\n".join(lines).strip("\n")


def _upsert_completed_ledger_entry(
    content: str,
    *,
    sprint_number: str,
    task_id: str,
    title: str,
) -> str:
    if not content.strip():
        content = f"{_COMPLETED_TASKS_HEADER}\n"
    if _COMPLETED_TASKS_HEADER not in content:
        content = f"{_COMPLETED_TASKS_HEADER}\n\n{content.lstrip()}"

    entry_line = f"- {task_id}: {title} ✅"
    section_heading = f"## Sprint {sprint_number}"
    pattern = re.compile(
        rf"(^##\s+Sprint\s+{re.escape(sprint_number)}\s*\n)(?P<body>.*?)(?=^##\s+Sprint\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if match is None:
        suffix = "" if content.endswith("\n") else "\n"
        return f"{content.rstrip()}{suffix}\n{section_heading}\n{entry_line}\n"

    lines = [line for line in match.group("body").splitlines() if line.strip()]
    if entry_line not in lines:
        lines.append(entry_line)
    replacement = f"{match.group(1)}" + "\n".join(lines) + "\n"
    return f"{content[: match.start()]}{replacement}{content[match.end() :]}"


def _closed_task_archive_preamble(archive_label: str) -> str:
    return "\n".join(
        [
            "# Closed Task Archive",
            "",
            _CLOSED_TASK_ARCHIVE_STATUS_LINE,
            f"**Quarter**: {archive_label}",
            "",
            CLOSED_TASK_ARCHIVE_GUIDANCE,
            "",
            "---",
            "",
        ]
    )


def _append_archived_task_block(
    archive_path: Path,
    *,
    archive_label: str,
    task_id: str,
    raw_block: str,
) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_exists = archive_path.exists()
    if archive_exists:
        archive_text = archive_path.read_text(encoding="utf-8")
    else:
        archive_text = _closed_task_archive_preamble(archive_label)

    if not archive_exists or task_block_match(task_id, archive_path) is None:
        suffix = "" if archive_text.endswith("\n") else "\n"
        archive_text = f"{archive_text}{suffix}{raw_block.strip()}\n\n---\n"
    archive_path.write_text(archive_text, encoding="utf-8")


def _remove_backlog_task_block(backlog_text: str, task_id: str) -> str:
    pattern = re.compile(
        rf"^###\s+{re.escape(task_id)}:\s+.*?(?:\n---\n|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    updated, count = pattern.subn("", backlog_text, count=1)
    if count != 1:
        raise ValueError(f"Unable to remove {task_id} from tasks/BACKLOG.md")
    return re.sub(r"\n{3,}", "\n\n", updated).rstrip() + "\n"


def close_ledgers_task_data(
    task_input: str,
    *,
    dry_run: bool,
) -> tuple[int, dict[str, Any], list[str]]:
    task_id = normalize_task_id(task_input)
    live_record = task_record(task_id)
    if live_record is None:
        if archived_task_record(task_id) is not None:
            return (
                ExitCode.VALIDATION_ERROR,
                {"task_id": task_id, "already_archived": True},
                [f"{task_id} is already closed and archived."],
            )
        return (
            ExitCode.NOT_FOUND,
            {"task_id": task_id},
            [f"{task_id} not found in tasks/BACKLOG.md"],
        )

    if task_block_match(task_id) is None:
        return (
            ExitCode.NOT_FOUND,
            {"task_id": task_id},
            [f"{task_id} not found in tasks/BACKLOG.md"],
        )

    backlog_text = backlog_path().read_text(encoding="utf-8")
    sprint_text = current_sprint_path().read_text(encoding="utf-8")
    completed_file = completed_path()
    completed_text = (
        completed_file.read_text(encoding="utf-8")
        if completed_file.exists()
        else f"{_COMPLETED_TASKS_HEADER}\n"
    )

    archive_date = current_date()
    archive_path = closed_tasks_archive_path(archive_date)
    archive_label = archive_path.stem
    updated_backlog = _remove_backlog_task_block(backlog_text, task_id)
    updated_sprint = _replace_h2_section(
        sprint_text,
        "Active Tasks",
        _remove_task_lines(_extract_h2_section_body(sprint_text, "Active Tasks"), task_id),
    )
    updated_sprint = _replace_h2_section(
        updated_sprint,
        "Completed This Sprint",
        _append_completed_sprint_line(
            _extract_h2_section_body(updated_sprint, "Completed This Sprint"),
            task_id,
            live_record.title,
        ),
    )
    updated_sprint = _replace_h2_section(
        updated_sprint,
        "Human Blocker Metadata",
        _remove_task_lines(
            _extract_h2_section_body(updated_sprint, "Human Blocker Metadata"), task_id
        ),
    )
    sprint_number = _extract_sprint_number(updated_sprint)
    updated_completed = _upsert_completed_ledger_entry(
        completed_text,
        sprint_number=sprint_number,
        task_id=task_id,
        title=live_record.title,
    )

    lines = [
        f"Task ledger close: {task_id}",
        f"- archive_shard={archive_path.relative_to(repo_root())}",
        f"- sprint={sprint_number}",
    ]
    if dry_run:
        lines.append("Dry run: would archive the full task block and update live ledgers.")
        return (
            ExitCode.OK,
            {
                "task_id": task_id,
                "archive_path": str(archive_path.relative_to(repo_root())),
                "sprint_number": sprint_number,
                "dry_run": True,
            },
            lines,
        )

    _append_archived_task_block(
        archive_path,
        archive_label=archive_label,
        task_id=task_id,
        raw_block=live_record.raw_block,
    )
    backlog_path().write_text(updated_backlog, encoding="utf-8")
    current_sprint_path().write_text(updated_sprint, encoding="utf-8")
    completed_file.write_text(updated_completed, encoding="utf-8")
    lines.append(
        "Archived task block and updated tasks/BACKLOG.md, tasks/CURRENT_SPRINT.md, and tasks/COMPLETED.md."
    )
    return (
        ExitCode.OK,
        {
            "task_id": task_id,
            "archive_path": str(archive_path.relative_to(repo_root())),
            "sprint_number": sprint_number,
            "dry_run": False,
        },
        lines,
    )


def finish_task_data(
    task_input: str | None, *, dry_run: bool
) -> tuple[int, dict[str, Any], list[str]]:
    try:
        config = _finish_config()
    except ValueError as exc:
        return _task_blocked(
            str(exc),
            next_action="Fix the invalid environment override and re-run `horadus tasks finish`.",
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    for command_name in (config.gh_bin, config.git_bin, config.python_bin):
        if _ensure_command_available(command_name) is None:
            return _task_blocked(
                f"missing required command '{command_name}'.",
                next_action=f"Install or expose `{command_name}` on PATH, then re-run `horadus tasks finish`.",
                data={"missing_command": command_name},
                exit_code=ExitCode.ENVIRONMENT_ERROR,
            )

    context = _resolve_finish_context(task_input, config)
    if not isinstance(context, FinishContext):
        return context

    remote_branch_result = _run_command(
        [config.git_bin, "ls-remote", "--exit-code", "--heads", "origin", context.branch_name]
    )
    remote_branch_exists = remote_branch_result.returncode == 0

    pr_url_result = _run_command(
        [config.gh_bin, "pr", "view", context.branch_name, "--json", "url", "--jq", ".url"]
    )
    pr_url = pr_url_result.stdout.strip()
    if pr_url_result.returncode != 0 or not pr_url:
        if not remote_branch_exists and not dry_run:
            docker_readiness = ensure_docker_ready(
                reason="the next required `git push` pre-push integration gate"
            )
            if not docker_readiness.ready:
                return _task_blocked(
                    "Docker is not ready for the next required push gate.",
                    next_action=(
                        f"Make Docker ready, then run `git push -u origin {context.branch_name}` "
                        f"and re-run `horadus tasks finish {context.task_id}`."
                    ),
                    data={
                        "task_id": context.task_id,
                        "branch_name": context.branch_name,
                        "docker_ready": False,
                    },
                    exit_code=ExitCode.ENVIRONMENT_ERROR,
                    extra_lines=docker_readiness.lines,
                )
        next_action = (
            f"Run `git push -u origin {context.branch_name}` and open a PR for {context.task_id}."
            if not remote_branch_exists
            else (
                f"Open a PR for `{context.branch_name}` titled `{context.task_id}: short summary` "
                f"with `Primary-Task: {context.task_id}` in the body, then re-run `horadus tasks finish`."
            )
        )
        return _task_blocked(
            f"unable to locate a PR for branch `{context.branch_name}`.",
            next_action=next_action,
            data={"task_id": context.task_id, "branch_name": context.branch_name},
        )

    pr_metadata_result = _run_command([config.gh_bin, "pr", "view", pr_url, "--json", "title,body"])
    if pr_metadata_result.returncode != 0:
        return _task_blocked(
            _result_message(pr_metadata_result, "Unable to read the PR title/body."),
            next_action="Resolve the GitHub CLI error, then re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )
    try:
        pr_metadata = json.loads(pr_metadata_result.stdout or "{}")
    except json.JSONDecodeError:
        return _task_blocked(
            "Unable to parse the PR title/body.",
            next_action="Resolve the GitHub CLI error, then re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
            extra_lines=_output_lines(pr_metadata_result),
        )
    pr_title = str(pr_metadata.get("title", "")) if isinstance(pr_metadata, dict) else ""
    pr_body = str(pr_metadata.get("body", "")) if isinstance(pr_metadata, dict) else ""

    scope_result = _run_pr_scope_guard(
        branch_name=context.branch_name,
        pr_title=pr_title,
        pr_body=pr_body,
    )
    if scope_result.returncode != 0:
        return _task_blocked(
            "PR scope validation failed.",
            next_action=(
                f"Fix the PR title to `{context.task_id}: short summary` and the PR body so it "
                f"contains exactly `Primary-Task: {context.task_id}`, then re-run `horadus tasks finish`."
            ),
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
            extra_lines=_output_lines(scope_result),
        )

    lines = []
    if context.current_branch is not None and context.current_branch != context.branch_name:
        lines.append(
            f"Resuming {context.task_id} from {context.current_branch} using task branch {context.branch_name}."
        )
    lines.extend([f"Finishing {context.task_id} from {context.branch_name}", f"PR: {pr_url}"])

    pr_state_result = _run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "state", "--jq", ".state"]
    )
    if pr_state_result.returncode != 0:
        return _task_blocked(
            _result_message(pr_state_result, "Unable to determine PR state."),
            next_action="Resolve the GitHub CLI error, then re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )
    pr_state = pr_state_result.stdout.strip()

    if pr_state != "MERGED" and not remote_branch_exists:
        return _task_blocked(
            f"branch `{context.branch_name}` is not pushed to origin.",
            next_action=f"Run `git push -u origin {context.branch_name}` and re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
        )

    draft_result = _run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "isDraft", "--jq", ".isDraft"]
    )
    if draft_result.returncode != 0:
        return _task_blocked(
            _result_message(draft_result, "Unable to determine PR draft status."),
            next_action="Resolve the GitHub CLI error, then re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )
    if draft_result.stdout.strip() == "true":
        return _task_blocked(
            "PR is draft; refusing to merge.",
            next_action="Mark the PR ready for review, then re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
        )

    if dry_run:
        lines.append(
            "Dry run: scope and PR preconditions passed; would wait for checks, merge, and sync main."
        )
        return (
            ExitCode.OK,
            {
                "task_id": context.task_id,
                "branch_name": context.branch_name,
                "pr_url": pr_url,
                "dry_run": True,
            },
            lines,
        )

    if pr_state == "MERGED":
        lines.append("PR already merged; skipping merge step.")
    else:
        lines.append(f"Waiting for PR checks to pass (timeout={config.checks_timeout_seconds}s)...")
        checks_ok, check_lines, check_reason = _coerce_wait_for_required_checks_result(
            _wait_for_required_checks(pr_url=pr_url, config=config)
        )
        if not checks_ok:
            return _task_blocked(
                (
                    "required PR checks are failing on the current head."
                    if check_reason == "fail"
                    else "required PR checks did not pass before timeout."
                ),
                next_action="Inspect the failing required checks, fix them, and re-run `horadus tasks finish`.",
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                },
                extra_lines=check_lines,
            )

        lines.append(
            "Waiting for review gate "
            f"(reviewer={config.review_bot_login}, timeout={config.review_timeout_seconds}s)..."
        )
        try:
            review_result = _run_review_gate(pr_url=pr_url, config=config)
        except CommandTimeoutError as exc:
            return _task_blocked(
                "review gate command did not exit after the configured wait window.",
                next_action=(
                    "Inspect GitHub/Codex review delivery and re-run `horadus tasks finish` "
                    "if the review gate keeps hanging."
                ),
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                },
                exit_code=ExitCode.ENVIRONMENT_ERROR,
                extra_lines=[str(exc), *exc.output_lines()],
            )
        if review_result.returncode != 0:
            review_lines = _output_lines(review_result)
            review_timed_out = any(line.startswith("review gate timeout:") for line in review_lines)
            return _task_blocked(
                (
                    "review gate timed out before the required current-head review arrived."
                    if review_timed_out
                    else "review gate did not pass."
                ),
                next_action=(
                    f"Wait for a current-head review from `{config.review_bot_login}`, then "
                    "re-run `horadus tasks finish`."
                    if review_timed_out
                    else "Address the current-head review feedback, then re-run "
                    "`horadus tasks finish`."
                ),
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                },
                exit_code=review_result.returncode,
                extra_lines=review_lines,
            )
        review_lines = _output_lines(review_result)
        review_timed_out = any(line.startswith("review gate timeout:") for line in review_lines)
        lines.extend(review_lines)

        unresolved_review_lines = _unresolved_review_thread_lines(pr_url=pr_url, config=config)
        if unresolved_review_lines:
            extra_lines = [*review_lines, *unresolved_review_lines]
            if review_timed_out:
                extra_lines.extend(_maybe_request_fresh_review(pr_url=pr_url, config=config))
            return _task_blocked(
                "PR is blocked by unresolved review comments.",
                next_action=(
                    "Resolve the unresolved review threads in GitHub and wait for a fresh "
                    "current-head review, then re-run `horadus tasks finish`."
                    if review_timed_out
                    else "Resolve the unresolved review threads in GitHub, then re-run "
                    "`horadus tasks finish`."
                ),
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                },
                extra_lines=extra_lines,
            )

        post_review_blocker = _current_required_checks_blocker(
            pr_url=pr_url, config=config, block_pending=False
        )
        if post_review_blocker is not None:
            blocker_message, blocker_lines = post_review_blocker
            return _task_blocked(
                blocker_message,
                next_action="Inspect the failing required checks, fix them, and re-run `horadus tasks finish`.",
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                },
                extra_lines=[*_output_lines(review_result), *blocker_lines],
            )

        lines.append("Merging PR (squash, delete branch)...")
        try:
            merge_result = _run_command_with_timeout(
                [config.gh_bin, "pr", "merge", pr_url, "--squash", "--delete-branch"],
                timeout_seconds=DEFAULT_FINISH_MERGE_COMMAND_TIMEOUT_SECONDS,
            )
        except CommandTimeoutError as exc:
            state_after_result = _run_command(
                [config.gh_bin, "pr", "view", pr_url, "--json", "state", "--jq", ".state"]
            )
            state_after = (
                state_after_result.stdout.strip() if state_after_result.returncode == 0 else ""
            )
            if state_after != "MERGED":
                return _task_blocked(
                    "merge command did not exit cleanly after the review gate passed.",
                    next_action="Inspect the PR merge state in GitHub, then re-run `horadus tasks finish`.",
                    data={
                        "task_id": context.task_id,
                        "branch_name": context.branch_name,
                        "pr_url": pr_url,
                    },
                    exit_code=ExitCode.ENVIRONMENT_ERROR,
                    extra_lines=[str(exc), *exc.output_lines()],
                )
            lines.append("Merge command timed out, but PR is already MERGED; continuing.")
            merge_result = subprocess.CompletedProcess(
                args=[config.gh_bin, "pr", "merge", pr_url, "--squash", "--delete-branch"],
                returncode=0,
                stdout="",
                stderr="",
            )
        if merge_result.returncode != 0:
            state_after_result = _run_command(
                [config.gh_bin, "pr", "view", pr_url, "--json", "state", "--jq", ".state"]
            )
            state_after = (
                state_after_result.stdout.strip() if state_after_result.returncode == 0 else ""
            )
            if state_after != "MERGED":
                merge_lines = _output_lines(merge_result)
                merge_message = "\n".join(merge_lines)
                if "--auto" in merge_message or "prohibits the merge" in merge_message:
                    lines.append(
                        "Base branch policy requires auto-merge; enabling auto-merge and waiting for merge completion."
                    )
                    try:
                        auto_merge_result = _run_command_with_timeout(
                            [
                                config.gh_bin,
                                "pr",
                                "merge",
                                pr_url,
                                "--auto",
                                "--squash",
                                "--delete-branch",
                            ],
                            timeout_seconds=DEFAULT_FINISH_MERGE_COMMAND_TIMEOUT_SECONDS,
                        )
                    except CommandTimeoutError as exc:
                        auto_state_after_result = _run_command(
                            [
                                config.gh_bin,
                                "pr",
                                "view",
                                pr_url,
                                "--json",
                                "state",
                                "--jq",
                                ".state",
                            ]
                        )
                        auto_state_after = (
                            auto_state_after_result.stdout.strip()
                            if auto_state_after_result.returncode == 0
                            else ""
                        )
                        if auto_state_after != "MERGED":
                            return _task_blocked(
                                "auto-merge command did not exit cleanly after the review gate passed.",
                                next_action=(
                                    "Inspect the PR auto-merge state in GitHub, then re-run "
                                    "`horadus tasks finish`."
                                ),
                                data={
                                    "task_id": context.task_id,
                                    "branch_name": context.branch_name,
                                    "pr_url": pr_url,
                                },
                                exit_code=ExitCode.ENVIRONMENT_ERROR,
                                extra_lines=[str(exc), *exc.output_lines()],
                            )
                        lines.append(
                            "Auto-merge command timed out, but PR is already MERGED; continuing."
                        )
                        auto_merge_result = subprocess.CompletedProcess(
                            args=[
                                config.gh_bin,
                                "pr",
                                "merge",
                                pr_url,
                                "--auto",
                                "--squash",
                                "--delete-branch",
                            ],
                            returncode=0,
                            stdout="",
                            stderr="",
                        )
                    if auto_merge_result.returncode != 0:
                        auto_state_after_result = _run_command(
                            [
                                config.gh_bin,
                                "pr",
                                "view",
                                pr_url,
                                "--json",
                                "state",
                                "--jq",
                                ".state",
                            ]
                        )
                        auto_state_after = (
                            auto_state_after_result.stdout.strip()
                            if auto_state_after_result.returncode == 0
                            else ""
                        )
                        if auto_state_after != "MERGED":
                            return _task_blocked(
                                "merge failed.",
                                next_action="Resolve the merge blocker in GitHub, then re-run `horadus tasks finish`.",
                                data={
                                    "task_id": context.task_id,
                                    "branch_name": context.branch_name,
                                    "pr_url": pr_url,
                                },
                                exit_code=ExitCode.ENVIRONMENT_ERROR,
                                extra_lines=_output_lines(auto_merge_result),
                            )
                    merged_ok, merged_lines = _wait_for_pr_state(
                        pr_url=pr_url, expected_state="MERGED", config=config
                    )
                    if not merged_ok:
                        return _task_blocked(
                            "auto-merge did not complete before timeout.",
                            next_action="Wait for the PR to merge in GitHub, then re-run `horadus tasks finish`.",
                            data={
                                "task_id": context.task_id,
                                "branch_name": context.branch_name,
                                "pr_url": pr_url,
                            },
                            exit_code=ExitCode.ENVIRONMENT_ERROR,
                            extra_lines=merged_lines,
                        )
                else:
                    return _task_blocked(
                        "merge failed.",
                        next_action="Resolve the merge blocker in GitHub, then re-run `horadus tasks finish`.",
                        data={
                            "task_id": context.task_id,
                            "branch_name": context.branch_name,
                            "pr_url": pr_url,
                        },
                        exit_code=ExitCode.ENVIRONMENT_ERROR,
                        extra_lines=merge_lines,
                    )
            lines.append("Merge step reported failure, but PR is already MERGED; continuing.")

    merge_commit_result = _run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "mergeCommit", "--jq", ".mergeCommit.oid"]
    )
    merge_commit = merge_commit_result.stdout.strip()
    if merge_commit_result.returncode != 0 or not merge_commit or merge_commit == "null":
        return _task_blocked(
            "could not determine merge commit.",
            next_action="Inspect the merged PR state in GitHub, then re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    lines.append("Syncing main...")
    switch_main_result = _run_command([config.git_bin, "switch", "main"])
    if switch_main_result.returncode != 0:
        return _task_blocked(
            _result_message(switch_main_result, "Failed to switch to main."),
            next_action="Resolve the local git state and switch to `main`, then re-run `horadus tasks finish`.",
            data={
                "task_id": context.task_id,
                "branch_name": context.branch_name,
                "pr_url": pr_url,
                "merge_commit": merge_commit,
            },
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    pull_result = _run_command([config.git_bin, "pull", "--ff-only"])
    if pull_result.returncode != 0:
        return _task_blocked(
            _result_message(pull_result, "Failed to fast-forward local main."),
            next_action="Resolve the local `main` sync issue and re-run `horadus tasks finish`.",
            data={
                "task_id": context.task_id,
                "branch_name": context.branch_name,
                "pr_url": pr_url,
                "merge_commit": merge_commit,
            },
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    cat_file_result = _run_command([config.git_bin, "cat-file", "-e", merge_commit])
    if cat_file_result.returncode != 0:
        return _task_blocked(
            f"merge commit {merge_commit} is not available locally after syncing main.",
            next_action="Fetch/pull `main` successfully, then re-run `horadus tasks finish`.",
            data={
                "task_id": context.task_id,
                "branch_name": context.branch_name,
                "pr_url": pr_url,
                "merge_commit": merge_commit,
            },
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    branch_exists_result = _run_command(
        [config.git_bin, "show-ref", "--verify", f"refs/heads/{context.branch_name}"]
    )
    if branch_exists_result.returncode == 0:
        delete_branch_result = _run_command([config.git_bin, "branch", "-d", context.branch_name])
        if delete_branch_result.returncode != 0:
            return _task_blocked(
                f"merged branch `{context.branch_name}` still exists locally and could not be deleted.",
                next_action=f"Delete `{context.branch_name}` locally after syncing main, then re-run `horadus tasks finish`.",
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                    "merge_commit": merge_commit,
                },
                exit_code=ExitCode.ENVIRONMENT_ERROR,
                extra_lines=_output_lines(delete_branch_result),
            )

    lifecycle_exit, lifecycle_data_result, lifecycle_lines = task_lifecycle_data(
        context.task_id,
        strict=True,
        dry_run=False,
    )
    if lifecycle_exit != ExitCode.OK:
        return _task_blocked(
            "completion verifier did not pass after merge.",
            next_action=(
                f"Run `horadus tasks lifecycle {context.task_id} --strict`, fix the remaining "
                "repo-state gap, then re-run `horadus tasks finish`."
            ),
            data={
                "task_id": context.task_id,
                "branch_name": context.branch_name,
                "pr_url": pr_url,
                "merge_commit": merge_commit,
                "lifecycle": lifecycle_data_result,
            },
            exit_code=lifecycle_exit,
            extra_lines=lifecycle_lines,
        )

    lines.append("Completion verifier passed: state local-main-synced.")
    lines.append(f"Task finish passed: merged {merge_commit} and synced main.")
    return (
        ExitCode.OK,
        {
            "task_id": context.task_id,
            "branch_name": context.branch_name,
            "pr_url": pr_url,
            "merge_commit": merge_commit,
            "lifecycle": lifecycle_data_result,
            "dry_run": False,
        },
        lines,
    )


def _task_record_payload(record: Any, *, include_raw: bool = True) -> dict[str, Any]:
    payload = asdict(record)
    if not include_raw:
        payload.pop("raw_block", None)
    payload["backlog_path"] = payload.get("source_path") or str(
        backlog_path().relative_to(repo_root())
    )
    payload["current_sprint_path"] = str(current_sprint_path().relative_to(repo_root()))
    return payload


def _archived_task_blocked_result(task_id: str) -> CommandResult:
    return CommandResult(
        exit_code=ExitCode.NOT_FOUND,
        error_lines=[
            f"{task_id} is archived; re-run with --include-archive to inspect its history"
        ],
        data={"task_id": task_id, "archived": True},
    )


def handle_list_active(_args: Any) -> CommandResult:
    tasks = parse_active_tasks()
    active_task_ids = {task.task_id for task in tasks}
    blockers = parse_human_blockers(task_ids=active_task_ids)
    blockers_by_task = {blocker.task_id: blocker for blocker in blockers}
    overdue_blockers = [
        blocker
        for blocker in blockers
        if blocker.urgency is not None and blocker.urgency.is_overdue
    ]
    lines = ["Active tasks:"]
    for task in tasks:
        suffix = " [REQUIRES_HUMAN]" if task.requires_human else ""
        note = f" — {task.note}" if task.note else ""
        urgency_note = ""
        blocker = blockers_by_task.get(task.task_id)
        if blocker is not None and blocker.urgency is not None:
            if blocker.urgency.is_overdue:
                overdue_days = abs(blocker.urgency.days_until_next_action or 0)
                urgency_note = f" [OVERDUE by {overdue_days}d]"
            elif blocker.urgency.is_due_today:
                urgency_note = " [DUE TODAY]"
        lines.append(f"- {task.task_id}: {task.title}{suffix}{urgency_note}{note}")
    if overdue_blockers:
        lines.append(
            "- overdue_human_blockers="
            f"{len(overdue_blockers)} ({', '.join(blocker.task_id for blocker in overdue_blockers)})"
        )
    return CommandResult(
        lines=lines,
        data={
            "tasks": [asdict(task) for task in tasks],
            "human_blockers": [asdict(item) for item in blockers],
            "overdue_human_blockers": [asdict(item) for item in overdue_blockers],
        },
    )


def handle_show(args: Any) -> CommandResult:
    try:
        task_id = normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])

    include_archive = bool(getattr(args, "include_archive", False))
    record = task_record(task_id, include_archive=include_archive)
    if record is None:
        if not include_archive and archived_task_record(task_id) is not None:
            return _archived_task_blocked_result(task_id)
        return CommandResult(
            exit_code=ExitCode.NOT_FOUND,
            error_lines=[f"{task_id} not found in tasks/BACKLOG.md"],
            data={"task_id": task_id},
        )

    lines = [
        f"# {record.task_id}: {record.title}",
        f"Status: {record.status}",
        f"Priority: {record.priority or 'unknown'}",
        f"Estimate: {record.estimate or 'unknown'}",
    ]
    if record.description:
        lines.append("Description:")
        lines.extend(f"- {item}" for item in record.description)
    if record.files:
        lines.append("Files:")
        lines.extend(f"- {item}" for item in record.files)
    if record.acceptance_criteria:
        lines.append("Acceptance Criteria:")
        lines.extend(record.acceptance_criteria)
    if record.spec_paths:
        lines.append("Specs:")
        lines.extend(f"- {item}" for item in record.spec_paths)
    return CommandResult(lines=lines, data=_task_record_payload(record))


def handle_search(args: Any) -> CommandResult:
    if args.limit is not None and args.limit < 1:
        return CommandResult(
            exit_code=ExitCode.VALIDATION_ERROR,
            error_lines=["--limit must be a positive integer"],
        )

    query = " ".join(args.query).strip()
    include_archive = bool(getattr(args, "include_archive", False))
    matches = search_task_records(
        query,
        status=args.status,
        limit=args.limit,
        include_archive=include_archive,
    )
    lines = [f"Task search: {query}"]
    lines.append(
        f"- status={args.status}, limit={args.limit if args.limit is not None else 'none'}, "
        f"include_archive={'yes' if include_archive else 'no'}, results={len(matches)}"
    )
    if not matches:
        lines.append("(no matches)")
    else:
        for record in matches:
            lines.append(
                f"- {record.task_id}: {record.title} [{record.status}] "
                f"(priority={record.priority or 'unknown'}, estimate={record.estimate or 'unknown'})"
            )
        if args.include_raw:
            for record in matches:
                lines.extend(["", f"## {record.task_id}", record.raw_block])
    return CommandResult(
        lines=lines,
        data={
            "query": query,
            "status_filter": args.status,
            "limit": args.limit,
            "include_archive": include_archive,
            "include_raw": bool(args.include_raw),
            "matches": [
                _task_record_payload(item, include_raw=bool(args.include_raw)) for item in matches
            ],
        },
    )


def _workflow_commands_for_context_pack(
    task_id: str,
    *,
    include_archive: bool,
    archived: bool,
) -> list[str]:
    commands = list(canonical_task_workflow_commands_for_task(task_id))
    if not (include_archive and archived):
        return commands

    default_context_pack = f"uv run --no-sync horadus tasks context-pack {task_id}"
    archived_context_pack = f"{default_context_pack} --include-archive"
    return [
        archived_context_pack if command == default_context_pack else command
        for command in commands
    ]


def handle_context_pack(args: Any) -> CommandResult:
    try:
        task_id = normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])

    include_archive = bool(getattr(args, "include_archive", False))
    record = task_record(task_id, include_archive=include_archive)
    if record is None:
        if not include_archive and archived_task_record(task_id) is not None:
            return _archived_task_blocked_result(task_id)
        return CommandResult(
            exit_code=ExitCode.NOT_FOUND,
            error_lines=[f"{task_id} not found in tasks/BACKLOG.md"],
            data={"task_id": task_id},
        )

    lines = [
        f"# Context Pack: {task_id}",
        "",
        "## Backlog Entry",
        record.raw_block,
        "",
        "## Sprint Status",
    ]
    lines.extend(record.sprint_lines or ["(not listed in current sprint)"])
    lines.extend(
        [
            "",
            "## Matching Spec",
        ]
    )
    lines.extend(record.spec_paths or ["(none)"])
    lines.extend(
        [
            "",
            "## Spec Contract Template",
            "tasks/specs/TEMPLATE.md",
        ]
    )
    lines.extend(
        [
            "",
            "## Likely Code Areas",
        ]
    )
    lines.extend(record.files or ["(not specified in backlog entry)"])
    lines.extend(
        [
            "",
            "## Suggested Workflow Commands",
        ]
    )
    workflow_commands = _workflow_commands_for_context_pack(
        task_id,
        include_archive=include_archive,
        archived=record.archived,
    )
    lines.extend(workflow_commands)
    lines.extend(
        [
            "",
            "## Suggested Validation Commands",
            "make agent-check",
            "uv run --no-sync horadus tasks local-gate --full",
        ]
    )
    return CommandResult(
        lines=lines,
        data={
            "task": _task_record_payload(record),
            "sprint_lines": record.sprint_lines,
            "spec_paths": record.spec_paths,
            "spec_template_path": "tasks/specs/TEMPLATE.md",
            "suggested_workflow_commands": workflow_commands,
            "suggested_validation_commands": [
                "make agent-check",
                "uv run --no-sync horadus tasks local-gate --full",
            ],
        },
    )


def handle_preflight(_args: Any) -> CommandResult:
    return _preflight_result()


def handle_eligibility(args: Any) -> CommandResult:
    try:
        task_id = normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = eligibility_data(task_id)
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_start(args: Any) -> CommandResult:
    try:
        task_id = normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = start_task_data(task_id, args.name, dry_run=bool(args.dry_run))
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_safe_start(args: Any) -> CommandResult:
    try:
        task_id = normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = safe_start_task_data(task_id, args.name, dry_run=bool(args.dry_run))
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_close_ledgers(args: Any) -> CommandResult:
    try:
        task_id = normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = close_ledgers_task_data(task_id, dry_run=bool(args.dry_run))
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_finish(args: Any) -> CommandResult:
    try:
        task_input = normalize_task_id(args.task_id) if args.task_id is not None else None
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = finish_task_data(task_input, dry_run=bool(args.dry_run))
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_record_friction(args: Any) -> CommandResult:
    try:
        task_id = normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = record_friction_data(
        task_input=task_id,
        command_attempted=args.command_attempted,
        fallback_used=args.fallback_used,
        friction_type=args.friction_type,
        note=args.note,
        suggested_improvement=args.suggested_improvement,
        dry_run=bool(args.dry_run),
    )
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_summarize_friction(args: Any) -> CommandResult:
    exit_code, data, lines = summarize_friction_data(
        report_date_input=args.date,
        output_path_input=args.output,
        dry_run=bool(args.dry_run),
    )
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def task_lifecycle_data(
    task_input: str | None, *, strict: bool, dry_run: bool
) -> tuple[int, dict[str, Any], list[str]]:
    try:
        config = _finish_config(enforce_review_timeout_override_policy=False)
    except ValueError as exc:
        return (ExitCode.ENVIRONMENT_ERROR, {}, [str(exc)])

    for command_name in (config.gh_bin, config.git_bin):
        if _ensure_command_available(command_name) is None:
            return (
                ExitCode.ENVIRONMENT_ERROR,
                {"missing_command": command_name},
                [f"Task lifecycle failed: missing required command '{command_name}'."],
            )

    snapshot = resolve_task_lifecycle(task_input, config=config)
    if not isinstance(snapshot, TaskLifecycleSnapshot):
        return snapshot
    snapshot.lifecycle_state = task_lifecycle_state(snapshot)
    snapshot.strict_complete = snapshot.lifecycle_state == "local-main-synced"

    lines = [
        f"Task lifecycle: {snapshot.task_id}",
        f"- state: {snapshot.lifecycle_state}",
        f"- current branch: {snapshot.current_branch}",
        f"- working tree clean: {'yes' if snapshot.working_tree_clean else 'no'}",
    ]
    if snapshot.branch_name:
        lines.append(f"- task branch: {snapshot.branch_name}")
    if snapshot.pr is None:
        lines.append("- PR: none")
    else:
        lines.append(
            f"- PR: {snapshot.pr.url} ({snapshot.pr.state}{' draft' if snapshot.pr.is_draft else ''})"
        )
        lines.append(f"- checks: {snapshot.pr.check_state}")
        if snapshot.pr.merge_commit_oid:
            lines.append(f"- merge commit: {snapshot.pr.merge_commit_oid}")
    if snapshot.local_main_synced is not None:
        lines.append(f"- local main synced: {'yes' if snapshot.local_main_synced else 'no'}")
    if snapshot.merge_commit_on_main is not None:
        lines.append(
            "- local main contains merge commit: "
            f"{'yes' if snapshot.merge_commit_on_main else 'no'}"
        )
    lines.append(f"- strict complete: {'yes' if snapshot.strict_complete else 'no'}")
    if dry_run:
        lines.append("Dry run: lifecycle inspection is read-only; returned live state.")

    exit_code = ExitCode.OK
    if strict and not snapshot.strict_complete:
        exit_code = ExitCode.VALIDATION_ERROR
        lines.append(
            "Strict verification failed: repo-policy completion requires state `local-main-synced`."
        )

    return (exit_code, asdict(snapshot), lines)


def handle_lifecycle(args: Any) -> CommandResult:
    try:
        task_input = normalize_task_id(args.task_id) if args.task_id is not None else None
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = task_lifecycle_data(
        task_input,
        strict=bool(getattr(args, "strict", False)),
        dry_run=bool(args.dry_run),
    )
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_local_gate(args: Any) -> CommandResult:
    exit_code, data, lines = local_gate_data(full=bool(args.full), dry_run=bool(args.dry_run))
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def add_leaf_cli_options(parser: Any) -> None:
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=["text", "json"],
        default=argparse.SUPPRESS,
        help="Output format.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Validate and describe the command without making changes.",
    )


def register_task_commands(subparsers: Any) -> None:
    tasks_parser = subparsers.add_parser("tasks", help="Repo task and sprint workflow helpers.")
    tasks_subparsers = tasks_parser.add_subparsers(dest="tasks_command")

    list_active_parser = tasks_subparsers.add_parser(
        "list-active",
        help="List active tasks from the current sprint.",
    )
    add_leaf_cli_options(list_active_parser)
    list_active_parser.set_defaults(handler=handle_list_active)

    show_parser = tasks_subparsers.add_parser("show", help="Show a live or archived task record.")
    add_leaf_cli_options(show_parser)
    show_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    show_parser.add_argument(
        "--include-archive",
        action="store_true",
        help="Allow lookup in archived backlog snapshots when the task is no longer live.",
    )
    show_parser.set_defaults(handler=handle_show)

    search_parser = tasks_subparsers.add_parser("search", help="Search live backlog tasks by text.")
    add_leaf_cli_options(search_parser)
    search_parser.add_argument("query", nargs="+", help="Query text.")
    search_parser.add_argument(
        "--status",
        choices=["active", "backlog", "completed", "all"],
        default="all",
        help="Filter search results by task status.",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of results to return.",
    )
    search_parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Include the raw backlog block for each matching task.",
    )
    search_parser.add_argument(
        "--include-archive",
        action="store_true",
        help="Include archived backlog snapshots in the search results.",
    )
    search_parser.set_defaults(handler=handle_search)

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
    context_pack_parser.set_defaults(handler=handle_context_pack)

    preflight_parser = tasks_subparsers.add_parser(
        "preflight",
        help="Validate task-start sequencing preflight on main.",
    )
    add_leaf_cli_options(preflight_parser)
    preflight_parser.set_defaults(handler=handle_preflight)

    eligibility_parser = tasks_subparsers.add_parser(
        "eligibility",
        help="Validate whether a task can be started autonomously.",
    )
    add_leaf_cli_options(eligibility_parser)
    eligibility_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    eligibility_parser.set_defaults(handler=handle_eligibility)

    start_parser = tasks_subparsers.add_parser(
        "start",
        help="Start a task branch with sequencing guards.",
    )
    add_leaf_cli_options(start_parser)
    start_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    start_parser.add_argument("--name", required=True, help="Short branch suffix.")
    start_parser.set_defaults(handler=handle_start)

    safe_start_parser = tasks_subparsers.add_parser(
        "safe-start",
        help="Run autonomous task-start eligibility plus guarded branch start.",
    )
    add_leaf_cli_options(safe_start_parser)
    safe_start_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    safe_start_parser.add_argument("--name", required=True, help="Short branch suffix.")
    safe_start_parser.set_defaults(handler=handle_safe_start)

    close_ledgers_parser = tasks_subparsers.add_parser(
        "close-ledgers",
        help="Archive the full task block and update the live task ledgers.",
    )
    add_leaf_cli_options(close_ledgers_parser)
    close_ledgers_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    close_ledgers_parser.set_defaults(handler=handle_close_ledgers)

    record_friction_parser = tasks_subparsers.add_parser(
        "record-friction",
        help="Append a structured Horadus workflow friction entry to local gitignored artifacts.",
    )
    add_leaf_cli_options(record_friction_parser)
    record_friction_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    record_friction_parser.add_argument(
        "--command-attempted",
        required=True,
        help="Canonical command or workflow step that triggered friction.",
    )
    record_friction_parser.add_argument(
        "--fallback-used",
        required=True,
        help="Fallback command or manual action used instead.",
    )
    record_friction_parser.add_argument(
        "--friction-type",
        required=True,
        choices=list(VALID_FRICTION_TYPES),
        help="Structured friction category.",
    )
    record_friction_parser.add_argument(
        "--note",
        required=True,
        help="Short note describing the friction.",
    )
    record_friction_parser.add_argument(
        "--suggested-improvement",
        required=True,
        help="Short suggestion for improving Horadus or its guidance.",
    )
    record_friction_parser.set_defaults(handler=handle_record_friction)

    summarize_friction_parser = tasks_subparsers.add_parser(
        "summarize-friction",
        help="Summarize daily Horadus workflow friction into a compact report artifact.",
    )
    add_leaf_cli_options(summarize_friction_parser)
    summarize_friction_parser.add_argument(
        "--date",
        default=None,
        help="UTC report date in YYYY-MM-DD format. Defaults to today in UTC.",
    )
    summarize_friction_parser.add_argument(
        "--output",
        default=None,
        help=(
            "Optional report path. Defaults to "
            "artifacts/agent/horadus-cli-feedback/daily/YYYY-MM-DD.md"
        ),
    )
    summarize_friction_parser.set_defaults(handler=handle_summarize_friction)

    finish_parser = tasks_subparsers.add_parser(
        "finish",
        help="Complete the current task PR lifecycle and sync local main.",
    )
    add_leaf_cli_options(finish_parser)
    finish_parser.add_argument(
        "task_id",
        nargs="?",
        help="Optional task id (TASK-XXX or XXX) to verify against the current task branch.",
    )
    finish_parser.set_defaults(handler=handle_finish)

    lifecycle_parser = tasks_subparsers.add_parser(
        "lifecycle",
        help="Report task lifecycle state and optionally verify repo-policy completion.",
    )
    add_leaf_cli_options(lifecycle_parser)
    lifecycle_parser.add_argument(
        "task_id",
        nargs="?",
        help="Optional task id (TASK-XXX or XXX). Required when not on the task branch.",
    )
    lifecycle_parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero unless the task is fully complete by repo policy.",
    )
    lifecycle_parser.set_defaults(handler=handle_lifecycle)

    local_gate_parser = tasks_subparsers.add_parser(
        "local-gate",
        help="Run the canonical post-task local validation gate.",
    )
    add_leaf_cli_options(local_gate_parser)
    local_gate_parser.add_argument(
        "--full",
        action="store_true",
        help="Run the full CI-parity local gate.",
    )
    local_gate_parser.set_defaults(handler=handle_local_gate)
