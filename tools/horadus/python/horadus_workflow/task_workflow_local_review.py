from __future__ import annotations

import json
import subprocess  # nosec B404
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import CommandResult, ExitCode

from ._task_workflow_local_review_config import (
    _harness_value as _harness_value_impl,
)
from ._task_workflow_local_review_config import (
    _local_review_log_path as _local_review_log_path_impl,
)
from ._task_workflow_local_review_config import (
    _local_review_runs_dir as _local_review_runs_dir_impl,
)
from ._task_workflow_local_review_config import (
    _provider_attempt_order,
)
from ._task_workflow_local_review_constants import (
    DEFAULT_LOCAL_REVIEW_BASE_BRANCH,
    DEFAULT_LOCAL_REVIEW_PROVIDER,
    LOCAL_REVIEW_DIRECTORY,
    LOCAL_REVIEW_HARNESS_PATH,
    LOCAL_REVIEW_LOG_FILENAME,
    LOCAL_REVIEW_PROVIDER_ENV,
    LOCAL_REVIEW_RUNS_DIRECTORY,
    LOCAL_REVIEW_STATUS_PATTERN,
    SUPPORTED_LOCAL_REVIEW_PROVIDERS,
    VALID_LOCAL_REVIEW_USEFULNESS,
)
from ._task_workflow_local_review_constants import (
    PROVIDER_BINARIES as _PROVIDER_BINARIES,
)
from ._task_workflow_local_review_context import _run_git as _run_git_impl
from ._task_workflow_local_review_models import (
    LocalReviewContext,
    LocalReviewParsedOutput,
    LocalReviewProviderRun,
)
from ._task_workflow_local_review_provider import (
    _execute_provider,
    _parse_provider_output,
    _provider_command,
    _render_codex_review_prompt,
    _render_prompt_contract,
    _render_prompt_only_provider_prompt,
)


def _local_review_log_path() -> Path:
    return _local_review_log_path_impl()


def _local_review_runs_dir() -> Path:
    return _local_review_runs_dir_impl()


def _harness_value(name: str) -> str | None:
    return _harness_value_impl(name)


def _resolve_provider_selection(
    explicit_provider: str | None,
) -> tuple[str, str] | tuple[int, dict[str, object], list[str]]:
    if explicit_provider is not None:
        return explicit_provider, "cli"

    configured_provider = _harness_value(LOCAL_REVIEW_PROVIDER_ENV)
    if configured_provider is None:
        return DEFAULT_LOCAL_REVIEW_PROVIDER, "default"

    provider = configured_provider.strip().lower()
    if provider not in SUPPORTED_LOCAL_REVIEW_PROVIDERS:
        return (
            ExitCode.VALIDATION_ERROR,
            {
                "configured_provider": configured_provider,
                "supported_providers": list(SUPPORTED_LOCAL_REVIEW_PROVIDERS),
            },
            [
                "Local review configuration failed.",
                f"{LOCAL_REVIEW_PROVIDER_ENV}={configured_provider!r} is unsupported.",
                "Supported providers: "
                + ", ".join(
                    f"`{provider_name}`" for provider_name in SUPPORTED_LOCAL_REVIEW_PROVIDERS
                ),
            ],
        )
    return provider, "env"


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return _run_git_impl(args)


def _review_context(
    *,
    base_branch: str,
) -> LocalReviewContext | tuple[int, dict[str, object], list[str]]:
    branch_result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    if branch_result.returncode != 0:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {},
            ["Local review failed: unable to determine the current branch."],
        )

    current_branch = branch_result.stdout.strip()
    if current_branch == "HEAD":
        return (
            ExitCode.VALIDATION_ERROR,
            {"current_branch": current_branch},
            [
                "Local review selection failed.",
                "A local review target requires a checked-out branch; detached HEAD is unsupported.",
            ],
        )

    base_result = _run_git(["rev-parse", "--verify", base_branch])
    if base_result.returncode != 0:
        return (
            ExitCode.VALIDATION_ERROR,
            {"base_branch": base_branch},
            [
                "Local review selection failed.",
                f"Base branch `{base_branch}` is not available locally.",
            ],
        )

    diff_result = _run_git(["diff", "--no-ext-diff", "--find-renames", f"{base_branch}...HEAD"])
    if diff_result.returncode != 0:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"base_branch": base_branch, "current_branch": current_branch},
            ["Local review failed: unable to compute the branch diff."],
        )

    diff_text = diff_result.stdout.strip()
    if not diff_text:
        return (
            ExitCode.VALIDATION_ERROR,
            {
                "base_branch": base_branch,
                "current_branch": current_branch,
                "review_target_kind": "branch_diff",
                "review_target_value": f"{base_branch}...{current_branch}",
            },
            [
                "Local review selection failed.",
                f"No branch diff exists for `{base_branch}...{current_branch}`.",
            ],
        )

    diff_stat_result = _run_git(["diff", "--stat", "--no-ext-diff", f"{base_branch}...HEAD"])
    name_only_result = _run_git(["diff", "--name-only", "--no-ext-diff", f"{base_branch}...HEAD"])
    status_result = _run_git(["status", "--short"])
    changed_files = [line.strip() for line in name_only_result.stdout.splitlines() if line.strip()]
    task_id = shared._task_id_from_branch_name(current_branch)
    return LocalReviewContext(
        current_branch=current_branch,
        task_id=task_id,
        base_branch=base_branch,
        review_target_kind="branch_diff",
        review_target_value=f"{base_branch}...{current_branch}",
        diff_text=diff_text,
        diff_stat=diff_stat_result.stdout.strip(),
        changed_files=changed_files,
        working_tree_dirty=bool(status_result.stdout.strip()),
    )


def _write_raw_output(
    *,
    provider: str,
    stdout: str,
    stderr: str,
) -> Path:
    runs_dir = _local_review_runs_dir()
    runs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    path = runs_dir / f"{timestamp}-{provider}-{uuid4().hex}.txt"
    path.write_text(
        "\n".join(
            [
                f"provider={provider}",
                "",
                "stdout:",
                stdout.rstrip(),
                "",
                "stderr:",
                stderr.rstrip(),
            ]
        ).rstrip()
        + "\n",
        encoding="utf-8",
    )
    return path


def _append_local_review_entry(payload: dict[str, object]) -> None:
    log_path = _local_review_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")


def _entry_payload(
    *,
    context: LocalReviewContext,
    selection_source: str,
    attempted_provider: str,
    executed_provider: str | None,
    fallback_provider: str | None,
    instructions: str | None,
    outcome: str,
    duration_seconds: float,
    findings_reported: bool | None,
    usefulness: str,
    raw_output_path: Path | None,
) -> dict[str, object]:
    return {
        "timestamp": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "task_id": context.task_id,
        "executed_provider": executed_provider,
        "provider_selection_source": selection_source,
        "review_target_kind": context.review_target_kind,
        "review_target_value": context.review_target_value,
        "custom_instructions_supplied": bool(instructions and instructions.strip()),
        "run_outcome": outcome,
        "duration_seconds": round(duration_seconds, 3),
        "attempted_provider": attempted_provider,
        "fallback_provider": fallback_provider,
        "findings_reported": findings_reported,
        "follow_up_changes": usefulness == "follow-up-changes",
        "judged_not_useful": usefulness == "not-useful",
        "raw_output_path": (
            str(raw_output_path.relative_to(task_repo.repo_root()))
            if raw_output_path is not None
            else None
        ),
    }


def _configuration_lines(
    *,
    context: LocalReviewContext,
    selected_provider: str,
    selection_source: str,
    provider_order: list[str],
    instructions: str | None,
    save_raw_output: bool,
    usefulness: str,
) -> list[str]:
    return [
        "Local review configuration:",
        f"- provider: {selected_provider} (source={selection_source})",
        f"- provider order: {', '.join(provider_order)}",
        f"- base branch: {context.base_branch}",
        f"- target: {context.review_target_value}",
        f"- instructions supplied: {'yes' if instructions and instructions.strip() else 'no'}",
        f"- usefulness: {usefulness}",
        f"- raw output: {'keep' if save_raw_output else 'discard on success'}",
    ]


def _dry_run_result(
    *,
    context: LocalReviewContext,
    selected_provider: str,
    selection_source: str,
    provider_order: list[str],
    instructions: str | None,
    lines: list[str],
) -> tuple[int, dict[str, object], list[str]]:
    preview_commands = []
    for provider_name in provider_order:
        command, _prompt = _provider_command(
            provider_name,
            context=context,
            instructions=instructions,
        )
        preview_commands.append({"provider": provider_name, "command": command})
    return (
        ExitCode.OK,
        {
            "provider": selected_provider,
            "provider_selection_source": selection_source,
            "provider_order": provider_order,
            "base_branch": context.base_branch,
            "current_branch": context.current_branch,
            "task_id": context.task_id,
            "review_target_kind": context.review_target_kind,
            "review_target_value": context.review_target_value,
            "working_tree_dirty": context.working_tree_dirty,
            "commands": preview_commands,
        },
        [*lines, "Dry run: validated the review target and provider command plan."],
    )


def _blocked_result(
    *,
    context: LocalReviewContext,
    selected_provider: str,
    selection_source: str,
    provider_order: list[str],
    attempted_provider: str,
    instructions: str | None,
    usefulness: str,
    lines: list[str],
    missing_provider: str | None = None,
    duration_seconds: float = 0.0,
) -> tuple[int, dict[str, object], list[str]]:
    payload = _entry_payload(
        context=context,
        selection_source=selection_source,
        attempted_provider=attempted_provider,
        executed_provider=None,
        fallback_provider=None,
        instructions=instructions,
        outcome="blocked",
        duration_seconds=duration_seconds,
        findings_reported=None,
        usefulness=usefulness,
        raw_output_path=None,
    )
    _append_local_review_entry(payload)
    data = {
        **payload,
        "provider": selected_provider,
        "provider_order": provider_order,
    }
    if missing_provider is not None:
        data["missing_provider"] = missing_provider
    message = "Local review blocked: no supported provider CLI was available."
    if missing_provider is not None:
        message = f"Local review blocked: `{missing_provider}` is not installed or not on PATH."
    return (ExitCode.ENVIRONMENT_ERROR, data, [*lines, message])


def _success_result(
    *,
    context: LocalReviewContext,
    selected_provider: str,
    selection_source: str,
    provider_order: list[str],
    attempted_provider: str,
    executed_provider: str,
    instructions: str | None,
    usefulness: str,
    save_raw_output: bool,
    started: float,
    parsed_output: LocalReviewParsedOutput,
    provider_run: LocalReviewProviderRun,
    lines: list[str],
) -> tuple[int, dict[str, object], list[str]]:
    raw_output_path = None
    if save_raw_output:
        raw_output_path = _write_raw_output(
            provider=executed_provider,
            stdout=provider_run.stdout,
            stderr=provider_run.stderr,
        )
    payload = _entry_payload(
        context=context,
        selection_source=selection_source,
        attempted_provider=attempted_provider,
        executed_provider=executed_provider,
        fallback_provider=(executed_provider if executed_provider != attempted_provider else None),
        instructions=instructions,
        outcome="ok",
        duration_seconds=time.monotonic() - started,
        findings_reported=parsed_output.findings_reported,
        usefulness=usefulness,
        raw_output_path=raw_output_path,
    )
    _append_local_review_entry(payload)
    summary_lines = [
        *lines,
        f"Local review completed via `{executed_provider}`.",
        f"Findings reported: {'yes' if parsed_output.findings_reported else 'no'}",
    ]
    if raw_output_path is not None:
        summary_lines.append(
            "Raw output: " + str(raw_output_path.relative_to(task_repo.repo_root()))
        )
    if parsed_output.review_body:
        summary_lines.extend(parsed_output.review_body.splitlines())
    return (
        ExitCode.OK,
        {
            **payload,
            "provider": selected_provider,
            "provider_order": provider_order,
            "base_branch": context.base_branch,
            "current_branch": context.current_branch,
            "review_body": parsed_output.review_body,
        },
        summary_lines,
    )


def _failed_result(
    *,
    context: LocalReviewContext,
    selected_provider: str,
    selection_source: str,
    provider_order: list[str],
    attempted_provider: str,
    executed_provider: str,
    instructions: str | None,
    usefulness: str,
    started: float,
    provider_run: LocalReviewProviderRun,
    lines: list[str],
) -> tuple[int, dict[str, object], list[str]]:
    raw_output_path = _write_raw_output(
        provider=executed_provider,
        stdout=provider_run.stdout,
        stderr=provider_run.stderr,
    )
    payload = _entry_payload(
        context=context,
        selection_source=selection_source,
        attempted_provider=attempted_provider,
        executed_provider=executed_provider,
        fallback_provider=(executed_provider if executed_provider != attempted_provider else None),
        instructions=instructions,
        outcome="failed",
        duration_seconds=time.monotonic() - started,
        findings_reported=None,
        usefulness=usefulness,
        raw_output_path=raw_output_path,
    )
    _append_local_review_entry(payload)
    output_lines = shared._summarize_output_lines(
        [*provider_run.stdout.splitlines(), *provider_run.stderr.splitlines()]
    )
    return (
        ExitCode.ENVIRONMENT_ERROR,
        {
            **payload,
            "provider": selected_provider,
            "provider_order": provider_order,
            "command": provider_run.command,
        },
        [
            *lines,
            "Local review failed: the provider command did not produce a usable result.",
            f"Raw output: {raw_output_path.relative_to(task_repo.repo_root())}",
            *output_lines,
        ],
    )


def local_review_data(
    *,
    provider: str | None,
    base_branch: str,
    instructions: str | None,
    allow_provider_fallback: bool,
    save_raw_output: bool,
    usefulness: str,
    dry_run: bool,
) -> tuple[int, dict[str, object], list[str]]:
    selection = _resolve_provider_selection(provider)
    if not isinstance(selection[0], str):
        return selection
    selected_provider, selection_source = selection
    context = _review_context(base_branch=base_branch)
    if not isinstance(context, LocalReviewContext):
        exit_code, data, lines = context
        return (
            exit_code,
            {
                **data,
                "attempted_provider": selected_provider,
                "provider_selection_source": selection_source,
            },
            lines,
        )
    provider_order = _provider_attempt_order(
        selected_provider,
        selection_source=selection_source,
        allow_provider_fallback=allow_provider_fallback,
    )
    lines = _configuration_lines(
        context=context,
        selected_provider=selected_provider,
        selection_source=selection_source,
        provider_order=provider_order,
        instructions=instructions,
        save_raw_output=save_raw_output,
        usefulness=usefulness,
    )
    if dry_run:
        return _dry_run_result(
            context=context,
            selected_provider=selected_provider,
            selection_source=selection_source,
            provider_order=provider_order,
            instructions=instructions,
            lines=lines,
        )
    if not provider_order:
        return _blocked_result(
            context=context,
            selected_provider=selected_provider,
            selection_source=selection_source,
            provider_order=provider_order,
            attempted_provider=selected_provider,
            instructions=instructions,
            usefulness=usefulness,
            lines=lines,
        )
    return _run_provider_review(
        context=context,
        selected_provider=selected_provider,
        selection_source=selection_source,
        provider_order=provider_order,
        instructions=instructions,
        allow_provider_fallback=allow_provider_fallback,
        save_raw_output=save_raw_output,
        usefulness=usefulness,
        lines=lines,
    )


def _run_provider_review(
    *,
    context: LocalReviewContext,
    selected_provider: str,
    selection_source: str,
    provider_order: list[str],
    instructions: str | None,
    allow_provider_fallback: bool,
    save_raw_output: bool,
    usefulness: str,
    lines: list[str],
) -> tuple[int, dict[str, object], list[str]]:
    attempted_provider = provider_order[0]
    started = time.monotonic()
    for index, provider_name in enumerate(provider_order):
        if shared._ensure_command_available(_PROVIDER_BINARIES[provider_name]) is None:
            lines.append(f"Provider `{provider_name}` is unavailable on PATH.")
            if index + 1 < len(provider_order):
                lines.append(f"Falling back to `{provider_order[index + 1]}`.")
                continue
            return _blocked_result(
                context=context,
                selected_provider=selected_provider,
                selection_source=selection_source,
                provider_order=provider_order,
                attempted_provider=attempted_provider,
                instructions=instructions,
                usefulness=usefulness,
                lines=lines,
                missing_provider=provider_name,
                duration_seconds=time.monotonic() - started,
            )
        provider_run = _execute_provider(
            provider_name,
            context=context,
            instructions=instructions,
        )
        lines.append(
            f"Ran `{provider_name}` local review ({provider_run.interface_kind} adapter, "
            f"{provider_run.duration_seconds:.2f}s)."
        )
        parsed_output = _parse_provider_output(provider_name, provider_run.stdout)
        if provider_run.returncode == 0 and parsed_output is not None:
            return _success_result(
                context=context,
                selected_provider=selected_provider,
                selection_source=selection_source,
                provider_order=provider_order,
                attempted_provider=attempted_provider,
                executed_provider=provider_name,
                instructions=instructions,
                usefulness=usefulness,
                save_raw_output=save_raw_output,
                started=started,
                parsed_output=parsed_output,
                provider_run=provider_run,
                lines=lines,
            )
        if provider_run.returncode != 0:
            lines.append(f"`{provider_name}` exited with status {provider_run.returncode}.")
        else:
            lines.append(
                f"`{provider_name}` returned unreadable output for the repo-owned contract."
            )
        if allow_provider_fallback and index + 1 < len(provider_order):
            lines.append(f"Falling back to `{provider_order[index + 1]}`.")
            continue
        return _failed_result(
            context=context,
            selected_provider=selected_provider,
            selection_source=selection_source,
            provider_order=provider_order,
            attempted_provider=attempted_provider,
            executed_provider=provider_name,
            instructions=instructions,
            usefulness=usefulness,
            started=started,
            provider_run=provider_run,
            lines=lines,
        )
    raise AssertionError("provider review loop exited without returning")  # pragma: no cover


def handle_local_review(args: Any) -> CommandResult:
    exit_code, data, lines = local_review_data(
        provider=getattr(args, "provider", None),
        base_branch=getattr(args, "base", DEFAULT_LOCAL_REVIEW_BASE_BRANCH),
        instructions=getattr(args, "instructions", None),
        allow_provider_fallback=bool(getattr(args, "allow_provider_fallback", False)),
        save_raw_output=bool(getattr(args, "save_raw_output", False)),
        usefulness=getattr(args, "usefulness", "pending"),
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


__all__ = [
    "DEFAULT_LOCAL_REVIEW_BASE_BRANCH",
    "DEFAULT_LOCAL_REVIEW_PROVIDER",
    "LOCAL_REVIEW_DIRECTORY",
    "LOCAL_REVIEW_HARNESS_PATH",
    "LOCAL_REVIEW_LOG_FILENAME",
    "LOCAL_REVIEW_PROVIDER_ENV",
    "LOCAL_REVIEW_RUNS_DIRECTORY",
    "LOCAL_REVIEW_STATUS_PATTERN",
    "SUPPORTED_LOCAL_REVIEW_PROVIDERS",
    "VALID_LOCAL_REVIEW_USEFULNESS",
    "LocalReviewContext",
    "LocalReviewParsedOutput",
    "LocalReviewProviderRun",
    "_append_local_review_entry",
    "_entry_payload",
    "_execute_provider",
    "_harness_value",
    "_local_review_log_path",
    "_local_review_runs_dir",
    "_parse_provider_output",
    "_provider_attempt_order",
    "_provider_command",
    "_render_codex_review_prompt",
    "_render_prompt_contract",
    "_render_prompt_only_provider_prompt",
    "_resolve_provider_selection",
    "_review_context",
    "_run_git",
    "_write_raw_output",
    "handle_local_review",
    "local_review_data",
]
