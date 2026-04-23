from __future__ import annotations

from pathlib import Path

import pytest

from tools.horadus.python.horadus_workflow.docstring_policy import (
    load_docstring_policy,
    render_docstring_policy_issues,
    run_docstring_policy_check,
)

pytestmark = pytest.mark.unit

_STANDARD_POLICY = """
[policy]
require_module_docstrings = true
require_public_class_docstrings = true
require_public_function_docstrings = true
require_public_method_docstrings = true
complex_member_min_lines = {min_lines}

[[targets]]
path = "src/app.py"
reason = "Application surface"
"""

_LOAD_POLICY = _STANDARD_POLICY.format(min_lines=12).replace(
    "require_public_function_docstrings = true",
    "require_public_function_docstrings = false",
)

_STANDARD_POLICY_5 = _STANDARD_POLICY.format(min_lines=5)
_STANDARD_POLICY_10 = _STANDARD_POLICY.format(min_lines=10)


def _write_file(repo_root: Path, relative_path: str, text: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_policy(repo_root: Path, body: str) -> Path:
    policy_path = repo_root / "config" / "quality" / "docstring_policy.toml"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(body.strip(), encoding="utf-8")
    return policy_path


def test_load_docstring_policy_reads_targets_and_thresholds(tmp_path: Path) -> None:
    policy_path = _write_policy(
        tmp_path,
        _LOAD_POLICY,
    )

    policy = load_docstring_policy(policy_path)

    assert policy.require_module_docstrings is True
    assert policy.require_public_class_docstrings is True
    assert policy.require_public_function_docstrings is False
    assert policy.require_public_method_docstrings is True
    assert policy.complex_member_min_lines == 12
    assert policy.targets[0].path == "src/app.py"
    assert policy.targets[0].reason == "Application surface"


def test_run_docstring_policy_check_reports_missing_required_docstrings(tmp_path: Path) -> None:
    policy_path = _write_policy(
        tmp_path,
        _STANDARD_POLICY_5,
    )
    _write_file(
        tmp_path,
        "src/app.py",
        "\n".join(
            [
                "class Service:",
                "    def run(self) -> None:",
                "        return None",
                "",
                "def public_api() -> None:",
                "    if True:",
                "        def _nested_helper(flag: bool, other: bool) -> int:",
                "            value = 0",
                "            if flag:",
                "                value += 1",
                "            if other:",
                "                value += 1",
                "            return value",
                "",
                "        _nested_helper(False, False)",
                "    return None",
                "",
                "def _complex_helper(flag: bool, other: bool) -> int:",
                "    value = 0",
                "    if flag:",
                "        value += 1",
                "    if other:",
                "        value += 1",
                "    return value",
            ]
        )
        + "\n",
    )

    result = run_docstring_policy_check(repo_root=tmp_path, policy_path=policy_path)
    rendered = render_docstring_policy_issues(result)

    assert result.errors == result.issues
    assert rendered == [
        "ERROR [class-docstring] src/app.py: Service is missing a docstring (public class)",
        "ERROR [member-docstring] src/app.py: Service.run is missing a docstring (public method on selected high-value path)",
        "ERROR [member-docstring] src/app.py: _complex_helper is missing a docstring (complex member >= 5 lines)",
        "ERROR [member-docstring] src/app.py: public_api is missing a docstring (public function on selected high-value path, complex member >= 5 lines)",
        "ERROR [member-docstring] src/app.py: public_api._nested_helper is missing a docstring (complex member >= 5 lines)",
        "ERROR [module-docstring] src/app.py: module docstring required for selected high-value path (Application surface)",
    ]


def test_run_docstring_policy_check_ignores_trivial_private_helpers(tmp_path: Path) -> None:
    policy_path = _write_policy(
        tmp_path,
        _STANDARD_POLICY_5,
    )
    _write_file(
        tmp_path,
        "src/app.py",
        "\n".join(
            [
                '"""Application surface."""',
                "",
                "class Service:",
                '    """Perform work."""',
                "",
                "    def run(self) -> None:",
                '        """Run the service."""',
                "        if True:",
                "            def _nested_helper() -> int:",
                '                """Compute an internal status."""',
                "                value = 0",
                "                value += 1",
                "                return value",
                "",
                "            _nested_helper()",
                "        return None",
                "",
                "    def _helper(self) -> None:",
                "        return None",
                "",
                "def public_api() -> None:",
                '    """Expose the public API."""',
                "    return None",
            ]
        )
        + "\n",
    )

    result = run_docstring_policy_check(repo_root=tmp_path, policy_path=policy_path)

    assert result.issues == ()
    assert render_docstring_policy_issues(result) == []


def test_run_docstring_policy_check_reports_missing_targets_and_parse_errors(
    tmp_path: Path,
) -> None:
    policy_path = _write_policy(
        tmp_path,
        """
[policy]
require_module_docstrings = true
require_public_class_docstrings = true
require_public_function_docstrings = true
require_public_method_docstrings = true
complex_member_min_lines = 10

[[targets]]
path = "src/missing.py"
reason = "Missing target"

[[targets]]
path = "src/broken.py"
reason = "Broken syntax"
""",
    )
    _write_file(tmp_path, "src/broken.py", "def broken(:\n    pass\n")

    result = run_docstring_policy_check(repo_root=tmp_path, policy_path=policy_path)

    assert render_docstring_policy_issues(result) == [
        "ERROR [parse-error] src/broken.py: unable to parse Python source: invalid syntax",
        "ERROR [target-missing] src/missing.py: configured docstring-policy target does not exist",
    ]


def test_run_docstring_policy_check_handles_nested_public_classes(tmp_path: Path) -> None:
    policy_path = _write_policy(
        tmp_path,
        _STANDARD_POLICY_10,
    )
    _write_file(
        tmp_path,
        "src/app.py",
        "\n".join(
            [
                '"""Application surface."""',
                "",
                "class Outer:",
                '    """Own the nested API surface."""',
                "",
                "    class Inner:",
                '        """Expose a nested helper type."""',
                "",
                "        def run(self) -> None:",
                '            """Run the nested helper."""',
                "            return None",
            ]
        )
        + "\n",
    )

    result = run_docstring_policy_check(repo_root=tmp_path, policy_path=policy_path)

    assert result.issues == ()


def test_run_docstring_policy_check_ignores_private_class_members(tmp_path: Path) -> None:
    policy_path = _write_policy(
        tmp_path,
        _STANDARD_POLICY_10,
    )
    _write_file(
        tmp_path,
        "src/app.py",
        "\n".join(
            [
                '"""Application surface."""',
                "",
                "class _Internal:",
                "    def run(self) -> None:",
                "        return None",
                "",
                "    class Nested:",
                "        def call(self) -> None:",
                "            return None",
            ]
        )
        + "\n",
    )

    result = run_docstring_policy_check(repo_root=tmp_path, policy_path=policy_path)

    assert result.issues == ()
