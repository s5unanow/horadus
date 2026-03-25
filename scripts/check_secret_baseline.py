from __future__ import annotations

import json
import re
import shutil
import subprocess  # nosec B404 - fixed git argv only, no shell execution
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from detect_secrets.core.secrets_collection import SecretsCollection
from detect_secrets.settings import configure_settings_from_baseline


@dataclass(frozen=True, order=True)
class SecretFingerprint:
    filename: str
    secret_type: str
    hashed_secret: str


@dataclass(frozen=True)
class SecretScanPolicy:
    baseline_path: str
    exclude_pattern: str

    def compiled_exclude_pattern(self) -> re.Pattern[str]:
        return re.compile(self.exclude_pattern)


def fingerprint_counts(results: dict[str, list[dict[str, object]]]) -> Counter[SecretFingerprint]:
    fingerprints: Counter[SecretFingerprint] = Counter()
    for filename, findings in results.items():
        for finding in findings:
            fingerprints[
                SecretFingerprint(
                    filename=filename,
                    secret_type=str(finding["type"]),
                    hashed_secret=str(finding["hashed_secret"]),
                )
            ] += 1
    return fingerprints


def actionable_findings(
    *,
    current_results: dict[str, list[dict[str, object]]],
    baseline_results: dict[str, list[dict[str, object]]],
) -> list[dict[str, object]]:
    baseline_counts = fingerprint_counts(baseline_results)
    seen_counts: Counter[SecretFingerprint] = Counter()
    findings: list[dict[str, object]] = []
    for filename, entries in sorted(current_results.items()):
        for entry in entries:
            fingerprint = SecretFingerprint(
                filename=filename,
                secret_type=str(entry["type"]),
                hashed_secret=str(entry["hashed_secret"]),
            )
            seen_counts[fingerprint] += 1
            if seen_counts[fingerprint] > baseline_counts[fingerprint]:
                findings.append(
                    {
                        "filename": filename,
                        "line_number": parse_line_number(entry.get("line_number")),
                        "type": str(entry["type"]),
                    }
                )
    return findings


def repo_root_from_script(script_file: str | None = None) -> Path:
    script_path = Path(script_file or __file__).resolve()
    return script_path.parents[1]


def load_secret_scan_policy(repo_root: Path) -> SecretScanPolicy:
    policy_path = repo_root / "config" / "security" / "secret_scan_policy.json"
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    baseline_path = payload.get("baseline_path")
    exclude_pattern = payload.get("exclude_pattern")
    if not isinstance(baseline_path, str) or not baseline_path:
        raise ValueError("secret scan policy is missing a valid 'baseline_path' value")
    if not isinstance(exclude_pattern, str) or not exclude_pattern:
        raise ValueError("secret scan policy is missing a valid 'exclude_pattern' value")
    return SecretScanPolicy(
        baseline_path=baseline_path,
        exclude_pattern=exclude_pattern,
    )


def is_excluded_path(path: str, policy: SecretScanPolicy) -> bool:
    return bool(policy.compiled_exclude_pattern().search(path))


def parse_line_number(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    return 0


def tracked_files(repo_root: Path, policy: SecretScanPolicy) -> list[str]:
    git_bin = shutil.which("git")
    if git_bin is None:
        raise RuntimeError("git is required for the secret scan.")

    result = subprocess.run(  # nosec B603 - fixed git argv against repo-owned paths
        [git_bin, "ls-files", "-z", "--", ".", f":(exclude){policy.baseline_path}"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    output = result.stdout.decode("utf-8")
    return [path for path in output.split("\0") if path and not is_excluded_path(path, policy)]


def scan_results(
    *, baseline: dict[str, object], files: list[str], policy: SecretScanPolicy
) -> dict[str, list[dict[str, object]]]:
    configure_settings_from_baseline(baseline, filename=policy.baseline_path)
    collection = SecretsCollection()
    collection.scan_files(*files)
    return collection.json()


def baseline_results(baseline: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    results = baseline.get("results")
    if not isinstance(results, dict):
        raise ValueError(".secrets.baseline is missing a valid 'results' mapping")
    return cast("dict[str, list[dict[str, object]]]", results)


def main() -> int:
    repo_root = repo_root_from_script()
    policy = load_secret_scan_policy(repo_root)
    baseline_path = repo_root / policy.baseline_path
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    files = tracked_files(repo_root, policy)
    if not files:
        print("secret-scan: no tracked files to scan.")
        return 0

    print("secret-scan: scanning tracked files against .secrets.baseline")
    findings = actionable_findings(
        current_results=scan_results(baseline=baseline, files=files, policy=policy),
        baseline_results=baseline_results(baseline),
    )
    if findings:
        print("Secret scan failed: findings outside .secrets.baseline were detected.")
        for finding in findings:
            print(f"- {finding['filename']}:{finding['line_number']} {finding['type']}")
        return 1

    print("Secret scan passed: no actionable findings outside .secrets.baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
