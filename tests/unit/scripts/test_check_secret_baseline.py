from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "check_secret_baseline.py"
_SPEC = importlib.util.spec_from_file_location("check_secret_baseline", MODULE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
secret_scan_module = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = secret_scan_module
_SPEC.loader.exec_module(secret_scan_module)

pytestmark = pytest.mark.unit


def test_actionable_findings_ignore_line_number_only_changes() -> None:
    baseline_results = {
        "tests/conftest.py": [
            {
                "type": "Hex High Entropy String",
                "hashed_secret": "abc123",  # pragma: allowlist secret
                "is_verified": False,
                "line_number": 10,
            }
        ]
    }
    current_results = {
        "tests/conftest.py": [
            {
                "type": "Hex High Entropy String",
                "hashed_secret": "abc123",  # pragma: allowlist secret
                "is_verified": False,
                "line_number": 30,
            }
        ]
    }

    findings = secret_scan_module.actionable_findings(
        current_results=current_results,
        baseline_results=baseline_results,
    )

    assert findings == []


def test_actionable_findings_report_new_fingerprint() -> None:
    baseline_results = {
        "tests/conftest.py": [
            {
                "type": "Hex High Entropy String",
                "hashed_secret": "abc123",  # pragma: allowlist secret
                "is_verified": False,
                "line_number": 10,
            }
        ]
    }
    current_results = {
        "scripts/example.py": [
            {
                "type": "Basic Auth Credentials",
                "hashed_secret": "new-fingerprint",  # pragma: allowlist secret
                "is_verified": False,
                "line_number": 7,
            }
        ]
    }

    findings = secret_scan_module.actionable_findings(
        current_results=current_results,
        baseline_results=baseline_results,
    )

    assert findings == [
        {
            "filename": "scripts/example.py",
            "line_number": 7,
            "type": "Basic Auth Credentials",
        }
    ]


def test_actionable_findings_report_duplicate_occurrence_beyond_baseline_count() -> None:
    baseline_results = {
        "tests/conftest.py": [
            {
                "type": "Hex High Entropy String",
                "hashed_secret": "abc123",  # pragma: allowlist secret
                "is_verified": False,
                "line_number": 10,
            }
        ]
    }
    current_results = {
        "tests/conftest.py": [
            {
                "type": "Hex High Entropy String",
                "hashed_secret": "abc123",  # pragma: allowlist secret
                "is_verified": False,
                "line_number": 10,
            },
            {
                "type": "Hex High Entropy String",
                "hashed_secret": "abc123",  # pragma: allowlist secret
                "is_verified": False,
                "line_number": 11,
            },
        ]
    }

    findings = secret_scan_module.actionable_findings(
        current_results=current_results,
        baseline_results=baseline_results,
    )

    assert findings == [
        {
            "filename": "tests/conftest.py",
            "line_number": 11,
            "type": "Hex High Entropy String",
        }
    ]


def test_actionable_findings_ignore_verification_state_changes() -> None:
    baseline_results = {
        "src/example.py": [
            {
                "type": "AWS Access Key",
                "hashed_secret": "verified-secret",  # pragma: allowlist secret
                "is_verified": False,
                "line_number": 12,
            }
        ]
    }
    current_results = {
        "src/example.py": [
            {
                "type": "AWS Access Key",
                "hashed_secret": "verified-secret",  # pragma: allowlist secret
                "is_verified": True,
                "line_number": 12,
            }
        ]
    }

    findings = secret_scan_module.actionable_findings(
        current_results=current_results,
        baseline_results=baseline_results,
    )

    assert findings == []


def test_load_secret_scan_policy_matches_repo_owned_excludes() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    policy = secret_scan_module.load_secret_scan_policy(repo_root)

    assert policy.baseline_path == ".secrets.baseline"
    assert secret_scan_module.is_excluded_path("docs/runbook.md", policy) is True
    assert secret_scan_module.is_excluded_path("tasks/CURRENT_SPRINT.md", policy) is True
    assert secret_scan_module.is_excluded_path("ai/eval/baselines/example.json", policy) is True
    assert secret_scan_module.is_excluded_path(".env.example", policy) is True
    assert secret_scan_module.is_excluded_path("src/core/config.py", policy) is False
