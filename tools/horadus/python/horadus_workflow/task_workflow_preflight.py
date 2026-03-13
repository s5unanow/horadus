from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import CommandResult, ExitCode

_TASK_LEDGER_INTAKE_PATHS = (
    "tasks/BACKLOG.md",
    "tasks/CURRENT_SPRINT.md",
)


@dataclass(slots=True)
class TaskLedgerIntakeState:
    task_id: str | None
    dirty_paths: list[str]
    eligible_paths: list[str]
    blocking_paths: list[str]
    consistency_errors: list[str]

    @property
    def ready(self) -> bool:
        return bool(self.eligible_paths) and not self.blocking_paths and not self.consistency_errors


def _git_status_dirty_paths(status_output: str) -> list[str]:
    paths: list[str] = []
    for raw_line in status_output.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        candidate = line[3:].strip() if len(line) >= 4 else ""
        if " -> " in candidate:
            candidate = candidate.split(" -> ", 1)[1].strip()
        if candidate.startswith('"') and candidate.endswith('"'):
            candidate = candidate[1:-1]
        if candidate:
            paths.append(candidate)
    return paths


def _head_text_for_path(path: str) -> str:
    result = shared._run_command(["git", "show", f"HEAD:{path}"])
    if result.returncode != 0:
        return ""
    return result.stdout


def _working_tree_text_for_path(path: str) -> str:
    try:
        repo_root = cast("Callable[[], Path]", shared._compat_attr("repo_root", task_repo))
        return (repo_root() / path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _index_text_for_path(path: str) -> str:
    result = shared._run_command(["git", "show", f":{path}"])
    if result.returncode != 0:
        return ""
    return result.stdout


def _diff_texts_for_path(path: str) -> list[tuple[str, str]]:
    texts: list[tuple[str, str]] = []
    for diff_kind, args in (
        ("unstaged", ["git", "diff", "--unified=20", "--", path]),
        ("staged", ["git", "diff", "--cached", "--unified=20", "--", path]),
    ):
        result = shared._run_command(args)
        if result.returncode == 0 and result.stdout.strip():
            texts.append((diff_kind, result.stdout))
    return texts


def _changed_line_numbers(diff_text: str) -> tuple[list[int], list[int]]:
    old_lines: list[int] = []
    new_lines: list[int] = []
    old_line = 0
    new_line = 0
    in_hunk = False
    hunk_pattern = re.compile(
        r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
    )
    for raw_line in diff_text.splitlines():
        match = hunk_pattern.match(raw_line)
        if match is not None:
            old_line = int(match.group("old_start"))
            new_line = int(match.group("new_start"))
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if raw_line.startswith("-") and not raw_line.startswith("---"):
            old_lines.append(old_line)
            old_line += 1
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            new_lines.append(new_line)
            new_line += 1
            continue
        if raw_line.startswith(" "):
            old_line += 1
            new_line += 1
    return (old_lines, new_lines)


def _backlog_task_id_for_line(text: str, line_number: int) -> str | None:
    lines = text.splitlines()
    if not lines:
        return None
    bounded_line = min(line_number, len(lines))
    if bounded_line <= 0:
        return None
    current_match = re.match(r"^###\s+(TASK-\d{3}):", lines[bounded_line - 1])
    if current_match is not None:
        return current_match.group(1)
    for index in range(bounded_line - 1, -1, -1):
        if re.match(r"^\s*---\s*$", lines[index]):
            break
        match = re.match(r"^###\s+(TASK-\d{3}):", lines[index])
        if match is not None:
            return match.group(1)
    return None


def _dirty_task_refs_for_path(path: str) -> set[str]:
    diff_texts = _diff_texts_for_path(path)
    if not diff_texts:
        return set()
    if path == "tasks/BACKLOG.md":
        head_text = _head_text_for_path(path)
        index_text = _index_text_for_path(path)
        working_text = _working_tree_text_for_path(path)
        refs: set[str] = set()
        for diff_kind, diff_text in diff_texts:
            old_text = index_text if diff_kind == "unstaged" else head_text
            new_text = working_text if diff_kind == "unstaged" else index_text
            old_lines, new_lines = _changed_line_numbers(diff_text)
            refs.update(
                task_id
                for line_number in old_lines
                if (task_id := _backlog_task_id_for_line(old_text, line_number)) is not None
            )
            refs.update(
                task_id
                for line_number in new_lines
                if (task_id := _backlog_task_id_for_line(new_text, line_number)) is not None
            )
        return refs
    diff_refs: set[str] = set()
    for _diff_kind, diff_text in diff_texts:
        for raw_line in diff_text.splitlines():
            if (raw_line.startswith("+") and not raw_line.startswith("+++")) or (
                raw_line.startswith("-") and not raw_line.startswith("---")
            ):
                diff_refs.update(re.findall(r"TASK-\d{3}", raw_line))
    return diff_refs


def _path_owned_task_start_intake_ref(path: str) -> str | None:
    if path in _TASK_LEDGER_INTAKE_PATHS:
        return None
    if path.startswith("tasks/exec_plans/"):
        return task_repo.task_id_from_exec_plan_path(path)
    if path.startswith("tasks/specs/"):
        return task_repo.task_id_from_spec_path(path)
    return None


def _is_task_start_intake_path(path: str) -> bool:
    return path in _TASK_LEDGER_INTAKE_PATHS or _path_owned_task_start_intake_ref(path) is not None


def _path_owned_task_start_intake_refs_from_diff(path: str) -> set[str]:
    refs: set[str] = set()
    if (owned_task_id := _path_owned_task_start_intake_ref(path)) is not None:
        refs.add(owned_task_id)
    for _diff_kind, diff_text in _diff_texts_for_path(path):
        for raw_line in diff_text.splitlines():
            candidate_path: str | None = None
            if raw_line.startswith("rename from "):
                candidate_path = raw_line.removeprefix("rename from ").strip()
            elif raw_line.startswith("rename to "):
                candidate_path = raw_line.removeprefix("rename to ").strip()
            elif raw_line.startswith("--- "):
                candidate_path = raw_line.removeprefix("--- ").strip()
            elif raw_line.startswith("+++ "):
                candidate_path = raw_line.removeprefix("+++ ").strip()
            if candidate_path is None or candidate_path == "/dev/null":
                continue
            if candidate_path.startswith(("a/", "b/")):
                candidate_path = candidate_path[2:]
            if (task_id := _path_owned_task_start_intake_ref(candidate_path)) is not None:
                refs.add(task_id)
    return refs


def _task_start_intake_refs_for_path(path: str) -> set[str]:
    if _path_owned_task_start_intake_ref(path) is not None:
        return _path_owned_task_start_intake_refs_from_diff(path)
    return _dirty_task_refs_for_path(path)


def _task_ledger_intake_state(
    *,
    task_id: str | None,
    dirty_paths: list[str],
) -> TaskLedgerIntakeState:
    eligible_paths = [path for path in dirty_paths if _is_task_start_intake_path(path)]
    blocking_paths = [path for path in dirty_paths if not _is_task_start_intake_path(path)]
    consistency_errors: list[str] = []
    if task_id is not None:
        task_block_match = shared._compat_attr("task_block_match", task_repo)
        try:
            backlog_match = task_block_match(task_id)
        except FileNotFoundError:
            backlog_match = None
            consistency_errors.append("tasks/BACKLOG.md is missing in the working tree.")
        if backlog_match is None:
            consistency_errors.append(
                f"{task_id} is not present in tasks/BACKLOG.md in the working tree."
            )
        for path in eligible_paths:
            task_refs = _task_start_intake_refs_for_path(path)
            if task_id not in task_refs:
                if _path_owned_task_start_intake_ref(path) is not None:
                    consistency_errors.append(f"{path} does not belong to {task_id}.")
                else:
                    consistency_errors.append(
                        f"{path} does not include {task_id} in its dirty diff."
                    )
            other_refs = sorted(ref for ref in task_refs if ref != task_id)
            if other_refs:
                consistency_errors.append(
                    f"{path} contains edits for other tasks: {', '.join(other_refs)}"
                )
        if "tasks/CURRENT_SPRINT.md" in eligible_paths:
            parse_active_tasks = shared._compat_attr("parse_active_tasks", task_repo)
            try:
                active_tasks = parse_active_tasks()
            except (FileNotFoundError, ValueError) as exc:
                consistency_errors.append(str(exc))
            else:
                if not any(task.task_id == task_id for task in active_tasks):
                    current_sprint_path = shared._compat_attr("current_sprint_path", task_repo)
                    consistency_errors.append(
                        f"{task_id} is not listed in Active Tasks ({current_sprint_path()})"
                    )
    return TaskLedgerIntakeState(
        task_id=task_id,
        dirty_paths=list(dirty_paths),
        eligible_paths=eligible_paths,
        blocking_paths=blocking_paths,
        consistency_errors=consistency_errors,
    )


def _ensure_required_hooks() -> tuple[bool, list[str]]:
    repo_root = shared._compat_attr("repo_root", task_repo)
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
    result = shared._run_command(
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


def task_preflight_data(
    *,
    task_id: str | None = None,
    allow_task_ledger_intake: bool = False,
) -> tuple[int, dict[str, object], list[str]]:
    if shared.getenv("SKIP_TASK_SEQUENCE_GUARD") == "1":
        data: dict[str, object] = {"skipped": True}
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

    branch_result = shared._run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
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

    status_result = shared._run_command(["git", "status", "--porcelain"])
    dirty_paths = _git_status_dirty_paths(status_result.stdout)
    intake_state = _task_ledger_intake_state(
        task_id=task_id if allow_task_ledger_intake else None,
        dirty_paths=dirty_paths,
    )
    if dirty_paths and not (allow_task_ledger_intake and intake_state.ready):
        dirty_data: dict[str, object] = {
            "working_tree_clean": False,
            "dirty_paths": dirty_paths,
            "eligible_dirty_paths": intake_state.eligible_paths,
            "blocking_dirty_paths": intake_state.blocking_paths,
            "intake_consistency_errors": intake_state.consistency_errors,
        }
        lines = [
            "Task sequencing guard failed.",
            "Working tree must be clean before starting a new task branch.",
        ]
        if allow_task_ledger_intake and intake_state.eligible_paths:
            lines.append(
                f"Eligible planning intake files for {task_id}: "
                f"{', '.join(intake_state.eligible_paths)}"
            )
        elif intake_state.eligible_paths and not intake_state.blocking_paths:
            lines.append(
                "Detected planning-intake-only dirty files: "
                f"{', '.join(intake_state.eligible_paths)}"
            )
            lines.append(
                "Run `uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name` "
                "to check whether they can be carried onto a new task branch."
            )
        if intake_state.blocking_paths:
            lines.append(f"Blocking dirty files: {', '.join(intake_state.blocking_paths)}")
        lines.extend(intake_state.consistency_errors)
        return (ExitCode.VALIDATION_ERROR, dirty_data, lines)

    fetch_result = shared._run_command(["git", "fetch", "origin", "main", "--quiet"])
    if fetch_result.returncode != 0:
        message = fetch_result.stderr.strip() or fetch_result.stdout.strip() or "git fetch failed"
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"fetch_error": message},
            ["Task sequencing guard failed.", message],
        )

    local_sha = shared._run_command(["git", "rev-parse", "HEAD"]).stdout.strip()
    remote_sha = shared._run_command(["git", "rev-parse", "origin/main"]).stdout.strip()
    if local_sha != remote_sha:
        return (
            ExitCode.VALIDATION_ERROR,
            {"local_main_sha": local_sha, "remote_main_sha": remote_sha},
            ["Task sequencing guard failed.", "Local main is not synced to origin/main."],
        )

    if shared.getenv("ALLOW_OPEN_TASK_PRS") != "1":
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

    result_data: dict[str, object] = {
        "gh_path": gh_path,
        "working_tree_clean": not dirty_paths,
        "local_main_sha": local_sha,
        "remote_main_sha": remote_sha,
        "dirty_paths": dirty_paths,
        "eligible_dirty_paths": intake_state.eligible_paths,
        "blocking_dirty_paths": intake_state.blocking_paths,
    }
    return (
        ExitCode.OK,
        result_data,
        [
            "Task sequencing guard passed: main is synced and no open task PRs.",
            *(
                [
                    f"Eligible planning intake files will carry onto the new branch for {task_id}: "
                    f"{', '.join(intake_state.eligible_paths)}"
                ]
                if intake_state.eligible_paths
                else []
            ),
        ],
    )


def _preflight_result() -> CommandResult:
    exit_code, data, lines = task_preflight_data()
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def eligibility_data(task_input: str) -> tuple[int, dict[str, object], list[str]]:
    task_id = task_repo.normalize_task_id(task_input)
    sprint_file = Path(
        shared.getenv("TASK_ELIGIBILITY_SPRINT_FILE") or task_repo.current_sprint_path()
    )
    if not sprint_file.exists():
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"sprint_file": str(sprint_file)},
            [f"Missing sprint file: {sprint_file}"],
        )

    try:
        _ = task_repo.active_section_text(sprint_file)
    except ValueError as exc:
        return (ExitCode.VALIDATION_ERROR, {"sprint_file": str(sprint_file)}, [str(exc)])

    matched_task = next(
        (task for task in task_repo.parse_active_tasks(sprint_file) if task.task_id == task_id),
        None,
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

    preflight_override = shared.getenv("TASK_ELIGIBILITY_PREFLIGHT_CMD")
    if preflight_override and preflight_override != "./scripts/check_task_start_preflight.sh":
        preflight_result = shared._run_shell(preflight_override)
        if preflight_result.returncode != 0:
            return (
                ExitCode.VALIDATION_ERROR,
                {"task_id": task_id, "preflight_cmd": preflight_override},
                [f"Task sequencing preflight failed for {task_id}."],
            )
    else:
        preflight_exit, preflight_data, preflight_lines = task_preflight_data(
            task_id=task_id,
            allow_task_ledger_intake=True,
        )
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
) -> tuple[int, dict[str, object], list[str]]:
    task_id = task_repo.normalize_task_id(task_input)
    slug = task_repo.slugify_name(raw_name)
    branch_name = f"codex/task-{task_id[5:]}-{slug}"

    preflight_exit, preflight_data, preflight_lines = task_preflight_data(
        task_id=task_id,
        allow_task_ledger_intake=True,
    )
    if preflight_exit != ExitCode.OK:
        return (
            preflight_exit,
            {"branch_name": branch_name, "preflight": preflight_data},
            preflight_lines,
        )

    local_exists = (
        shared._run_command(
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
        shared._run_command(
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

    lines = list(preflight_lines)
    if dry_run:
        lines.append(f"Dry run: would create task branch {branch_name}")
        return (
            ExitCode.OK,
            {"task_id": task_id, "branch_name": branch_name, "dry_run": True},
            lines,
        )

    switch_result = shared._run_command(["git", "switch", "-c", branch_name])
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
) -> tuple[int, dict[str, object], list[str]]:
    task_id = task_repo.normalize_task_id(task_input)

    eligibility_exit, eligibility_data_payload, eligibility_lines = eligibility_data(task_id)
    if eligibility_exit != ExitCode.OK:
        return (eligibility_exit, eligibility_data_payload, eligibility_lines)

    start_exit, start_data_payload, start_lines = start_task_data(
        task_id, raw_name, dry_run=dry_run
    )
    return (start_exit, start_data_payload, [*eligibility_lines, *start_lines])


def handle_preflight(_args: Any) -> CommandResult:
    return _preflight_result()


def handle_eligibility(args: Any) -> CommandResult:
    try:
        task_id = task_repo.normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = eligibility_data(task_id)
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_start(args: Any) -> CommandResult:
    try:
        task_id = task_repo.normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = start_task_data(task_id, args.name, dry_run=bool(args.dry_run))
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_safe_start(args: Any) -> CommandResult:
    try:
        task_id = task_repo.normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = safe_start_task_data(task_id, args.name, dry_run=bool(args.dry_run))
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


__all__ = [
    "TaskLedgerIntakeState",
    "_backlog_task_id_for_line",
    "_changed_line_numbers",
    "_diff_texts_for_path",
    "_dirty_task_refs_for_path",
    "_ensure_required_hooks",
    "_git_status_dirty_paths",
    "_head_text_for_path",
    "_index_text_for_path",
    "_open_task_prs",
    "_path_owned_task_start_intake_ref",
    "_path_owned_task_start_intake_refs_from_diff",
    "_preflight_result",
    "_task_ledger_intake_state",
    "_working_tree_text_for_path",
    "eligibility_data",
    "handle_eligibility",
    "handle_preflight",
    "handle_safe_start",
    "handle_start",
    "safe_start_task_data",
    "start_task_data",
    "task_preflight_data",
]
