from __future__ import annotations

import json
import re
import shutil
import subprocess  # nosec B404 - fixed git argv only, no shell execution
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from detect_secrets.core.secrets_collection import SecretsCollection
from detect_secrets.settings import configure_settings_from_baseline

REPO_EXCLUDE_PATTERN = re.compile(r"(^docs/|^tasks/|^ai/eval/baselines/|\.env\.example$)")


@dataclass(frozen=True, order=True)
class SecretFingerprint:
    filename: str
    secret_type: str
    hashed_secret: str
    is_verified: bool


def fingerprint_counts(results: dict[str, list[dict[str, object]]]) -> Counter[SecretFingerprint]:
    fingerprints: Counter[SecretFingerprint] = Counter()
    for filename, findings in results.items():
        for finding in findings:
            fingerprints[
                SecretFingerprint(
                    filename=filename,
                    secret_type=str(finding["type"]),
                    hashed_secret=str(finding["hashed_secret"]),
                    is_verified=bool(finding.get("is_verified", False)),
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
                is_verified=bool(entry.get("is_verified", False)),
            )
            seen_counts[fingerprint] += 1
            if seen_counts[fingerprint] > baseline_counts[fingerprint]:
                findings.append(
                    {
                        "filename": filename,
                        "line_number": int(entry.get("line_number", 0)),
                        "type": str(entry["type"]),
                    }
                )
    return findings


def is_excluded_path(path: str) -> bool:
    return bool(REPO_EXCLUDE_PATTERN.search(path))


def tracked_files(repo_root: Path) -> list[str]:
    git_bin = shutil.which("git")
    if git_bin is None:
        raise RuntimeError("git is required for the secret scan.")

    result = subprocess.run(  # nosec B603 - fixed git argv against repo-owned paths
        [git_bin, "ls-files", "-z", "--", ".", ":(exclude).secrets.baseline"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    output = result.stdout.decode("utf-8")
    return [path for path in output.split("\0") if path and not is_excluded_path(path)]


def scan_results(
    *, repo_root: Path, baseline: dict[str, object], files: list[str]
) -> dict[str, list[dict[str, object]]]:
    configure_settings_from_baseline(baseline, filename=".secrets.baseline")
    collection = SecretsCollection()
    collection.scan_files(*files)
    return collection.json()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    baseline_path = repo_root / ".secrets.baseline"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    files = tracked_files(repo_root)
    if not files:
        print("secret-scan: no tracked files to scan.")
        return 0

    print("secret-scan: scanning tracked files against .secrets.baseline")
    findings = actionable_findings(
        current_results=scan_results(repo_root=repo_root, baseline=baseline, files=files),
        baseline_results=baseline["results"],
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
