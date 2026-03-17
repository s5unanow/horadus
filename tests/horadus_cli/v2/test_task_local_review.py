from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
import tools.horadus.python.horadus_workflow.task_repo as task_repo_module
from tests.horadus_cli.v2.helpers import _completed

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_repo_root_override() -> None:
    task_repo_module.clear_repo_root_override()
    yield
    task_repo_module.clear_repo_root_override()


def _seed_repo_root(tmp_path: Path) -> None:
    task_repo_module.set_repo_root_override(tmp_path)
    (tmp_path / "tasks").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='horadus'\n", encoding="utf-8")


def _fake_review_git(args: list[str], *, branch: str = "codex/task-286-local-review") -> object:
    mapping = {
        ("rev-parse", "--abbrev-ref", "HEAD"): _completed(["git", *args], stdout=f"{branch}\n"),
        ("rev-parse", "--verify", "main"): _completed(["git", *args], stdout="base-sha\n"),
        (
            "diff",
            "--no-ext-diff",
            "--find-renames",
            "main...HEAD",
        ): _completed(
            ["git", *args],
            stdout="diff --git a/docs/AGENT_RUNBOOK.md b/docs/AGENT_RUNBOOK.md\n+new line\n",
        ),
        ("diff", "--stat", "--no-ext-diff", "main...HEAD"): _completed(
            ["git", *args],
            stdout=" docs/AGENT_RUNBOOK.md | 1 +\n 1 file changed, 1 insertion(+)\n",
        ),
        ("diff", "--name-only", "--no-ext-diff", "main...HEAD"): _completed(
            ["git", *args], stdout="docs/AGENT_RUNBOOK.md\n"
        ),
        ("status", "--short"): _completed(["git", *args], stdout=""),
    }
    try:
        return mapping[tuple(args)]
    except KeyError as exc:  # pragma: no cover - guard for future command drift
        raise AssertionError(f"unexpected git args: {args}") from exc


def test_local_review_data_uses_env_provider_and_writes_success_telemetry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_repo_root(tmp_path)
    (tmp_path / ".env.harness").write_text(
        "HORADUS_LOCAL_REVIEW_PROVIDER=gemini\n", encoding="utf-8"
    )
    monkeypatch.setattr(task_commands_module, "_run_git", _fake_review_git)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_execute_provider",
        lambda provider, **_kwargs: task_commands_module.LocalReviewProviderRun(
            provider=provider,
            interface_kind="prompt",
            command=["gemini", "--prompt", "..."],
            prompt="prompt",
            returncode=0,
            stdout="HORADUS-LOCAL-REVIEW: no-findings\nNo findings.\n",
            stderr="",
            duration_seconds=0.75,
        ),
    )

    exit_code, data, lines = task_commands_module.local_review_data(
        provider=None,
        base_branch="main",
        instructions="Focus on CLI contract drift.",
        allow_provider_fallback=False,
        save_raw_output=False,
        usefulness="pending",
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["provider"] == "gemini"
    assert data["provider_selection_source"] == "env"
    assert data["executed_provider"] == "gemini"
    assert data["findings_reported"] is False
    assert data["task_id"] == "TASK-286"
    assert any(line == "Local review completed via `gemini`." for line in lines)

    log_path = tmp_path / "artifacts" / "agent" / "local-review" / "entries.jsonl"
    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert payload["provider_selection_source"] == "env"
    assert payload["attempted_provider"] == "gemini"
    assert payload["executed_provider"] == "gemini"
    assert payload["review_target_value"] == "main...codex/task-286-local-review"
    assert payload["run_outcome"] == "ok"
    assert payload["raw_output_path"] is None


def test_local_review_data_auto_falls_back_when_default_provider_cli_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_repo_root(tmp_path)
    monkeypatch.setattr(task_commands_module, "_run_git", _fake_review_git)

    def fake_which(name: str) -> str | None:
        if name == "claude":
            return None
        return f"/bin/{name}"

    monkeypatch.setattr(task_commands_module, "_ensure_command_available", fake_which)
    monkeypatch.setattr(
        task_commands_module,
        "_execute_provider",
        lambda provider, **_kwargs: task_commands_module.LocalReviewProviderRun(
            provider=provider,
            interface_kind="review" if provider == "codex" else "prompt",
            command=[provider],
            prompt="prompt",
            returncode=0,
            stdout="HORADUS-LOCAL-REVIEW: findings\n- docs/AGENT_RUNBOOK.md: update wording\n",
            stderr="",
            duration_seconds=0.5,
        ),
    )

    exit_code, data, lines = task_commands_module.local_review_data(
        provider=None,
        base_branch="main",
        instructions=None,
        allow_provider_fallback=False,
        save_raw_output=False,
        usefulness="follow-up-changes",
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["provider"] == "claude"
    assert data["executed_provider"] == "codex"
    assert data["fallback_provider"] == "codex"
    assert data["findings_reported"] is True
    assert "Provider `claude` is unavailable on PATH." in lines
    assert "Falling back to `codex`." in lines


def test_local_review_data_accepts_codex_native_review_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_repo_root(tmp_path)
    monkeypatch.setattr(task_commands_module, "_run_git", _fake_review_git)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_execute_provider",
        lambda provider, **_kwargs: task_commands_module.LocalReviewProviderRun(
            provider=provider,
            interface_kind="review",
            command=["codex", "exec", "review", "--base", "main"],
            prompt="prompt",
            returncode=0,
            stdout="No blocking issues found in the reviewed changes.\n",
            stderr="",
            duration_seconds=0.3,
        ),
    )

    exit_code, data, lines = task_commands_module.local_review_data(
        provider="codex",
        base_branch="main",
        instructions=None,
        allow_provider_fallback=False,
        save_raw_output=False,
        usefulness="pending",
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["provider"] == "codex"
    assert data["executed_provider"] == "codex"
    assert data["findings_reported"] is False
    assert any(line == "Local review completed via `codex`." for line in lines)


def test_local_review_data_does_not_fallback_on_runtime_failure_without_opt_in(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_repo_root(tmp_path)
    monkeypatch.setattr(task_commands_module, "_run_git", _fake_review_git)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_execute_provider",
        lambda provider, **_kwargs: task_commands_module.LocalReviewProviderRun(
            provider=provider,
            interface_kind="prompt",
            command=[provider],
            prompt="prompt",
            returncode=1,
            stdout="",
            stderr="authentication failed\n",
            duration_seconds=0.2,
        ),
    )

    exit_code, data, lines = task_commands_module.local_review_data(
        provider=None,
        base_branch="main",
        instructions=None,
        allow_provider_fallback=False,
        save_raw_output=False,
        usefulness="pending",
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["provider"] == "claude"
    assert data["executed_provider"] == "claude"
    assert data["run_outcome"] == "failed"
    assert any(line == "`claude` exited with status 1." for line in lines)
    assert any(
        line == "Local review failed: the provider command did not produce a usable result."
        for line in lines
    )
    assert any(
        str(line).startswith("Raw output: artifacts/agent/local-review/runs/") for line in lines
    )


def test_local_review_data_returns_bounded_timeout_failure_with_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_repo_root(tmp_path)
    monkeypatch.setattr(task_commands_module, "_run_git", _fake_review_git)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_execute_provider",
        lambda provider, **_kwargs: task_commands_module.LocalReviewProviderRun(
            provider=provider,
            interface_kind="prompt",
            command=[provider],
            prompt="prompt",
            returncode=124,
            stdout="partial stdout\n",
            stderr="provider command timed out after 180s\n",
            duration_seconds=180.0,
            timed_out=True,
            timeout_seconds=180.0,
        ),
    )

    exit_code, data, lines = task_commands_module.local_review_data(
        provider="claude",
        base_branch="main",
        instructions=None,
        allow_provider_fallback=False,
        save_raw_output=False,
        usefulness="pending",
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["provider"] == "claude"
    assert data["executed_provider"] == "claude"
    assert data["timed_out"] is True
    assert data["timeout_seconds"] == 180.0
    assert any(line == "`claude` timed out after 180s." for line in lines)
    assert any(line == "Local review failed: `claude` did not exit within 180s." for line in lines)
    assert any(
        str(line).startswith("Raw output: artifacts/agent/local-review/runs/") for line in lines
    )


def test_local_review_data_reports_missing_explicit_provider_without_implicit_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_repo_root(tmp_path)
    monkeypatch.setattr(task_commands_module, "_run_git", _fake_review_git)
    monkeypatch.setattr(task_commands_module, "_ensure_command_available", lambda _name: None)

    exit_code, data, lines = task_commands_module.local_review_data(
        provider="claude",
        base_branch="main",
        instructions=None,
        allow_provider_fallback=False,
        save_raw_output=False,
        usefulness="not-useful",
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["provider"] == "claude"
    assert data["missing_provider"] == "claude"
    assert data["run_outcome"] == "blocked"
    assert lines[-1] == "Local review blocked: `claude` is not installed or not on PATH."


def test_local_review_helper_functions_cover_provider_config_and_prompt_shapes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_repo_root(tmp_path)
    assert task_commands_module._harness_value("HORADUS_LOCAL_REVIEW_PROVIDER") is None

    monkeypatch.setenv("HORADUS_LOCAL_REVIEW_PROVIDER", " codex ")
    assert task_commands_module._harness_value("HORADUS_LOCAL_REVIEW_PROVIDER") == "codex"
    monkeypatch.delenv("HORADUS_LOCAL_REVIEW_PROVIDER", raising=False)

    (tmp_path / ".env.harness").write_text(
        "HORADUS_LOCAL_REVIEW_PROVIDER= gemini \n", encoding="utf-8"
    )
    assert task_commands_module._harness_value("HORADUS_LOCAL_REVIEW_PROVIDER") == "gemini"
    (tmp_path / ".env.harness").write_text("OTHER=value\n", encoding="utf-8")
    assert task_commands_module._harness_value("HORADUS_LOCAL_REVIEW_PROVIDER") is None
    (tmp_path / ".env.harness").write_text(
        "HORADUS_LOCAL_REVIEW_PROVIDER= gemini \n", encoding="utf-8"
    )
    assert task_commands_module._resolve_provider_selection("claude") == ("claude", "cli")
    assert task_commands_module._resolve_provider_selection(None) == ("gemini", "env")

    (tmp_path / ".env.harness").write_text(
        "HORADUS_LOCAL_REVIEW_PROVIDER=bogus\n", encoding="utf-8"
    )
    invalid = task_commands_module._resolve_provider_selection(None)
    assert invalid[0] == task_commands_module.ExitCode.VALIDATION_ERROR
    assert task_commands_module._provider_attempt_order(
        "claude", selection_source="cli", allow_provider_fallback=False
    ) == ["claude"]
    assert task_commands_module._provider_attempt_order(
        "codex", selection_source="default", allow_provider_fallback=False
    ) == ["codex", "claude", "gemini"]

    context = task_commands_module.LocalReviewContext(
        current_branch="feature/local-review",
        task_id=None,
        base_branch="main",
        review_target_kind="branch_diff",
        review_target_value="main...feature/local-review",
        diff_text="diff --git a/foo b/foo\n",
        diff_stat="1 file changed\n",
        changed_files=[],
        working_tree_dirty=True,
    )
    contract = task_commands_module._render_prompt_contract(
        instructions="Focus on docs regressions."
    )
    assert "Additional review instructions:" in contract
    prompt = task_commands_module._render_prompt_only_provider_prompt(
        context=context,
        instructions="Focus on docs regressions.",
    )
    assert "Task id: unknown" in prompt
    assert "Changed files:\n- (none)" in prompt
    codex_prompt = task_commands_module._render_codex_review_prompt(
        context=context,
        instructions=None,
    )
    assert "Review the current repository changes against the provided base branch." in codex_prompt

    claude_command, _ = task_commands_module._provider_command(
        "claude", context=context, instructions=None
    )
    gemini_command, _ = task_commands_module._provider_command(
        "gemini", context=context, instructions=None
    )
    codex_command, _ = task_commands_module._provider_command(
        "codex", context=context, instructions=None
    )
    assert claude_command[:3] == ["claude", "--print", "--output-format"]
    assert gemini_command[:2] == ["gemini", "--prompt"]
    assert codex_command == ["codex", "exec", "review", "--base", "main"]


def test_local_review_helper_functions_cover_git_run_output_parsing_and_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_repo_root(tmp_path)
    captured_commands: list[list[str]] = []
    monkeypatch.setattr(
        task_commands_module, "getenv", lambda name: "custom-git" if name == "GIT_BIN" else None
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: captured_commands.append(args) or _completed(args, stdout="ok\n"),
    )
    assert task_commands_module._run_git(["status"]).stdout == "ok\n"
    assert captured_commands == [["custom-git", "status"]]
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError("missing git")),
    )
    missing_git = task_commands_module._run_git(["status"])
    assert missing_git.returncode == 1
    assert "missing git" in missing_git.stderr

    parsed = task_commands_module._parse_provider_output(
        "claude", "\nHORADUS-LOCAL-REVIEW: findings\n- file.py: issue\n"
    )
    assert parsed is not None
    assert parsed.findings_reported is True
    assert task_commands_module._parse_provider_output("claude", "") is None
    assert task_commands_module._parse_provider_output("claude", "not the marker") is None
    assert task_commands_module._parse_provider_output("codex", "   \n") is None
    codex_no_findings = task_commands_module._parse_provider_output(
        "codex",
        "No blocking issues found in the reviewed changes.",
    )
    assert codex_no_findings is not None
    assert codex_no_findings.findings_reported is False
    codex_mixed_response = task_commands_module._parse_provider_output(
        "codex",
        "Looks good to me.\n- foo.py: found a real bug after the summary line.",
    )
    assert codex_mixed_response is not None
    assert codex_mixed_response.findings_reported is True
    codex_colon_finding = task_commands_module._parse_provider_output(
        "codex",
        "No blocking issues found: foo.py still raises on empty config.",
    )
    assert codex_colon_finding is not None
    assert codex_colon_finding.findings_reported is True
    codex_findings = task_commands_module._parse_provider_output(
        "codex",
        "- tools/horadus/python/horadus_workflow/_task_workflow_local_review_provider.py: "
        "drops the compatibility branch for older prompt adapters.",
    )
    assert codex_findings is not None
    assert codex_findings.findings_reported is True

    monkeypatch.setattr(task_commands_module, "_local_review_runs_dir", lambda: tmp_path / "runs")
    raw_output_path = task_commands_module._write_raw_output(
        provider="codex",
        stdout="hello\n",
        stderr="warn\n",
    )
    second_raw_output_path = task_commands_module._write_raw_output(
        provider="codex",
        stdout="hello again\n",
        stderr="warn again\n",
    )
    assert raw_output_path.read_text(encoding="utf-8").startswith("provider=codex\n")
    assert second_raw_output_path != raw_output_path

    context = task_commands_module.LocalReviewContext(
        current_branch="codex/task-286-local-review",
        task_id="TASK-286",
        base_branch="main",
        review_target_kind="branch_diff",
        review_target_value="main...codex/task-286-local-review",
        diff_text="diff\n",
        diff_stat="1 file changed\n",
        changed_files=["foo.py"],
        working_tree_dirty=False,
    )
    payload = task_commands_module._entry_payload(
        context=context,
        selection_source="default",
        attempted_provider="claude",
        executed_provider="codex",
        fallback_provider="codex",
        instructions="extra",
        outcome="ok",
        duration_seconds=1.2345,
        findings_reported=True,
        usefulness="follow-up-changes",
        raw_output_path=raw_output_path,
    )
    assert payload["raw_output_path"] == str(raw_output_path.relative_to(tmp_path))
    monkeypatch.setattr(
        task_commands_module, "_local_review_log_path", lambda: tmp_path / "entries.jsonl"
    )
    task_commands_module._append_local_review_entry(payload)
    assert (
        json.loads((tmp_path / "entries.jsonl").read_text(encoding="utf-8"))["executed_provider"]
        == "codex"
    )


@pytest.mark.parametrize(
    ("responses", "expected_line"),
    [
        (
            {
                ("rev-parse", "--abbrev-ref", "HEAD"): _completed(["git"], returncode=1),
            },
            "Local review failed: unable to determine the current branch.",
        ),
        (
            {
                ("rev-parse", "--abbrev-ref", "HEAD"): _completed(["git"], stdout="HEAD\n"),
            },
            "A local review target requires a checked-out branch; detached HEAD is unsupported.",
        ),
        (
            {
                ("rev-parse", "--abbrev-ref", "HEAD"): _completed(["git"], stdout="feature\n"),
                ("rev-parse", "--verify", "main"): _completed(["git"], returncode=1),
            },
            "Base branch `main` is not available locally.",
        ),
        (
            {
                ("rev-parse", "--abbrev-ref", "HEAD"): _completed(["git"], stdout="feature\n"),
                ("rev-parse", "--verify", "main"): _completed(["git"], stdout="sha\n"),
                (
                    "diff",
                    "--no-ext-diff",
                    "--find-renames",
                    "main...HEAD",
                ): _completed(["git"], returncode=1),
            },
            "Local review failed: unable to compute the branch diff.",
        ),
        (
            {
                ("rev-parse", "--abbrev-ref", "HEAD"): _completed(["git"], stdout="feature\n"),
                ("rev-parse", "--verify", "main"): _completed(["git"], stdout="sha\n"),
                (
                    "diff",
                    "--no-ext-diff",
                    "--find-renames",
                    "main...HEAD",
                ): _completed(["git"], stdout=""),
            },
            "No branch diff exists for `main...feature`.",
        ),
    ],
)
def test_review_context_reports_expected_blockers(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[tuple[str, ...], object],
    expected_line: str,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_run_git",
        lambda args: responses[tuple(args)],
    )

    exit_code, _data, lines = task_commands_module._review_context(base_branch="main")

    assert exit_code in {
        task_commands_module.ExitCode.ENVIRONMENT_ERROR,
        task_commands_module.ExitCode.VALIDATION_ERROR,
    }
    assert expected_line in lines


def test_execute_provider_and_local_review_dry_run_cover_remaining_success_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_repo_root(tmp_path)
    monkeypatch.setattr(task_commands_module, "_run_git", _fake_review_git)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )

    monotonic_values = iter(
        [10.0, 12.5, 20.0, 21.0, 30.0, 31.5, 40.0, 40.25, 50.0, 50.5, 60.0, 60.25]
    )
    monkeypatch.setattr(task_commands_module.time, "monotonic", lambda: next(monotonic_values))
    captured_runs: list[tuple[list[str], str | None]] = []

    monkeypatch.setattr(
        task_commands_module.subprocess,
        "run",
        lambda command, **kwargs: (
            captured_runs.append((command, kwargs.get("input")))
            or _completed(command, stdout="HORADUS-LOCAL-REVIEW: no-findings\n")
        ),
    )
    context = task_commands_module.LocalReviewContext(
        current_branch="codex/task-286-local-review",
        task_id="TASK-286",
        base_branch="main",
        review_target_kind="branch_diff",
        review_target_value="main...codex/task-286-local-review",
        diff_text="diff\n",
        diff_stat="1 file changed\n",
        changed_files=["foo.py"],
        working_tree_dirty=False,
    )
    run = task_commands_module._execute_provider("codex", context=context, instructions=None)
    assert run.duration_seconds == 2.5
    assert run.command == ["codex", "exec", "review", "--base", "main"]
    claude_run = task_commands_module._execute_provider(
        "claude", context=context, instructions=None
    )
    gemini_run = task_commands_module._execute_provider(
        "gemini", context=context, instructions=None
    )
    assert claude_run.duration_seconds == 1.0
    assert gemini_run.duration_seconds == 1.5
    assert captured_runs[0][0] == ["codex", "exec", "review", "--base", "main"]
    assert captured_runs[1][0] == [
        "claude",
        "--print",
        "--output-format",
        "text",
        "--permission-mode",
        "plan",
    ]
    assert captured_runs[2][0] == [
        "gemini",
        "--prompt",
        "Review the full stdin payload and follow its contract exactly.",
        "--approval-mode",
        "plan",
        "--output-format",
        "text",
    ]
    assert captured_runs[0][1] is None
    assert captured_runs[1][1] == claude_run.prompt
    assert captured_runs[2][1] == gemini_run.prompt

    monkeypatch.setattr(
        task_commands_module.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("argument list too long")),
    )
    failed_run = task_commands_module._execute_provider(
        "claude", context=context, instructions=None
    )
    assert failed_run.returncode == 1
    assert "argument list too long" in failed_run.stderr

    def raise_timeout(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(["claude"], 180, output=b"partial", stderr=b"still waiting")

    monkeypatch.setattr(task_commands_module.subprocess, "run", raise_timeout)
    timed_out_run = task_commands_module._execute_provider(
        "claude", context=context, instructions=None
    )
    assert timed_out_run.returncode == 124
    assert timed_out_run.timed_out is True
    assert timed_out_run.timeout_seconds == 180.0
    assert timed_out_run.stdout == "partial"
    assert "still waiting" in timed_out_run.stderr
    assert "provider command timed out after 180s" in timed_out_run.stderr

    def raise_timeout_with_text(
        *_args: object, **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(["claude"], 180, output="partial-text", stderr=None)

    monkeypatch.setattr(task_commands_module.subprocess, "run", raise_timeout_with_text)
    timed_out_text_run = task_commands_module._execute_provider(
        "claude", context=context, instructions=None
    )
    assert timed_out_text_run.stdout == "partial-text"
    assert timed_out_text_run.stderr == "provider command timed out after 180s"

    exit_code, data, lines = task_commands_module.local_review_data(
        provider="codex",
        base_branch="main",
        instructions=None,
        allow_provider_fallback=True,
        save_raw_output=False,
        usefulness="pending",
        dry_run=True,
    )
    assert exit_code == task_commands_module.ExitCode.OK
    assert data["provider_order"] == ["codex", "claude", "gemini"]
    assert lines[-1] == "Dry run: validated the review target and provider command plan."


def test_local_review_data_covers_context_blocker_saved_raw_success_fallback_and_all_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_repo_root(tmp_path)

    monkeypatch.setattr(
        task_commands_module,
        "_review_context",
        lambda **_kwargs: (
            task_commands_module.ExitCode.VALIDATION_ERROR,
            {"base_branch": "main"},
            ["Local review selection failed."],
        ),
    )
    exit_code, data, lines = task_commands_module.local_review_data(
        provider="claude",
        base_branch="main",
        instructions=None,
        allow_provider_fallback=False,
        save_raw_output=False,
        usefulness="pending",
        dry_run=False,
    )
    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["attempted_provider"] == "claude"
    assert data["provider_selection_source"] == "cli"
    assert lines == ["Local review selection failed."]

    (tmp_path / ".env.harness").write_text(
        "HORADUS_LOCAL_REVIEW_PROVIDER=bogus\n", encoding="utf-8"
    )
    exit_code, data, lines = task_commands_module.local_review_data(
        provider=None,
        base_branch="main",
        instructions=None,
        allow_provider_fallback=False,
        save_raw_output=False,
        usefulness="pending",
        dry_run=False,
    )
    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["configured_provider"] == "bogus"
    assert lines[0] == "Local review configuration failed."

    monkeypatch.setattr(
        task_commands_module, "_review_context", lambda **_kwargs: _fake_review_context()
    )
    monkeypatch.setattr(task_commands_module, "_run_git", _fake_review_git)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(task_commands_module, "_harness_value", lambda _name: None)
    monkeypatch.setattr(
        task_commands_module,
        "_execute_provider",
        lambda provider, **_kwargs: task_commands_module.LocalReviewProviderRun(
            provider=provider,
            interface_kind="prompt",
            command=[provider],
            prompt="prompt",
            returncode=0,
            stdout="HORADUS-LOCAL-REVIEW: no-findings\n",
            stderr="",
            duration_seconds=0.1,
        ),
    )
    exit_code, data, lines = task_commands_module.local_review_data(
        provider="claude",
        base_branch="main",
        instructions=None,
        allow_provider_fallback=False,
        save_raw_output=True,
        usefulness="pending",
        dry_run=False,
    )
    assert exit_code == task_commands_module.ExitCode.OK
    assert data["raw_output_path"] is not None
    assert any(
        str(line).startswith("Raw output: artifacts/agent/local-review/runs/") for line in lines
    )

    executions = iter(
        [
            task_commands_module.LocalReviewProviderRun(
                provider="claude",
                interface_kind="prompt",
                command=["claude"],
                prompt="prompt",
                returncode=0,
                stdout="unreadable",
                stderr="",
                duration_seconds=0.1,
            ),
            task_commands_module.LocalReviewProviderRun(
                provider="codex",
                interface_kind="review",
                command=["codex"],
                prompt="prompt",
                returncode=0,
                stdout="HORADUS-LOCAL-REVIEW: findings\n- foo.py: bug\n",
                stderr="",
                duration_seconds=0.1,
            ),
        ]
    )
    monkeypatch.setattr(
        task_commands_module,
        "_execute_provider",
        lambda _provider, **_kwargs: next(executions),
    )
    exit_code, data, lines = task_commands_module.local_review_data(
        provider="claude",
        base_branch="main",
        instructions=None,
        allow_provider_fallback=True,
        save_raw_output=False,
        usefulness="pending",
        dry_run=False,
    )
    assert exit_code == task_commands_module.ExitCode.OK
    assert data["executed_provider"] == "codex"
    assert "Falling back to `codex`." in lines
    assert any(
        line == "`claude` returned unreadable output for the repo-owned contract." for line in lines
    )

    monkeypatch.setattr(
        task_commands_module,
        "_provider_attempt_order",
        lambda *_args, **_kwargs: [],
    )
    exit_code, data, lines = task_commands_module.local_review_data(
        provider=None,
        base_branch="main",
        instructions=None,
        allow_provider_fallback=False,
        save_raw_output=False,
        usefulness="pending",
        dry_run=False,
    )
    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["run_outcome"] == "blocked"
    assert lines[-1] == "Local review blocked: no supported provider CLI was available."


def _fake_review_context() -> task_commands_module.LocalReviewContext:
    return task_commands_module.LocalReviewContext(
        current_branch="codex/task-286-local-review",
        task_id="TASK-286",
        base_branch="main",
        review_target_kind="branch_diff",
        review_target_value="main...codex/task-286-local-review",
        diff_text="diff --git a/foo.py b/foo.py\n",
        diff_stat=" foo.py | 1 +\n",
        changed_files=["foo.py"],
        working_tree_dirty=False,
    )
