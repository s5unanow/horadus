#!/usr/bin/env python3
"""
Run the repo-owned dependency audit with narrow allowlist filtering.
"""

from __future__ import annotations

import json
import subprocess  # nosec B404 - fixed argv only, no shell execution
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ALLOWLIST_PATH = REPO_ROOT / "config" / "security" / "dependency_audit_allowlist.json"


@dataclass(frozen=True)
class AllowlistEntry:
    vuln_id: str
    package: str
    version: str
    reason: str
    review_after: str


@dataclass(frozen=True)
class AuditFinding:
    package: str
    version: str
    vuln_id: str
    aliases: tuple[str, ...]
    fix_versions: tuple[str, ...]
    description: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.package.lower(), self.version, self.vuln_id)


def load_allowlist(path: Path | None = None) -> tuple[AllowlistEntry, ...]:
    policy_path = ALLOWLIST_PATH if path is None else path
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    allowlist = payload.get("allowlist")
    if not isinstance(allowlist, list):
        raise ValueError("dependency audit allowlist must contain an 'allowlist' array")

    entries: list[AllowlistEntry] = []
    for index, raw_entry in enumerate(allowlist):
        if not isinstance(raw_entry, dict):
            raise ValueError(f"dependency audit allowlist entry {index} must be an object")
        try:
            vuln_id = str(raw_entry["id"]).strip()
            package = str(raw_entry["package"]).strip()
            version = str(raw_entry["version"]).strip()
            reason = str(raw_entry["reason"]).strip()
            review_after = str(raw_entry["review_after"]).strip()
        except KeyError as exc:
            raise ValueError(
                f"dependency audit allowlist entry {index} is missing {exc.args[0]!r}"
            ) from exc
        if not all((vuln_id, package, version, reason, review_after)):
            raise ValueError(
                f"dependency audit allowlist entry {index} must not contain blank fields"
            )
        entries.append(
            AllowlistEntry(
                vuln_id=vuln_id,
                package=package,
                version=version,
                reason=reason,
                review_after=review_after,
            )
        )
    return tuple(entries)


def parse_audit_report(payload: dict[str, Any]) -> tuple[AuditFinding, ...]:
    dependencies = payload.get("dependencies")
    if not isinstance(dependencies, list):
        raise ValueError("dependency audit report is missing a valid 'dependencies' array")

    findings: list[AuditFinding] = []
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            raise ValueError("dependency audit dependency entries must be objects")
        package = str(dependency.get("name", "")).strip()
        version = str(dependency.get("version", "")).strip()
        skip_reason = str(dependency.get("skip_reason", "")).strip()
        vulns = dependency.get("vulns", [])
        if not package:
            raise ValueError("dependency audit dependency entries must include name and version")
        if skip_reason:
            raise ValueError(f"dependency audit skipped {package}: {skip_reason}")
        if not version:
            raise ValueError("dependency audit dependency entries must include name and version")
        if not isinstance(vulns, list):
            raise ValueError("dependency audit dependency 'vulns' must be a list")
        for vuln in vulns:
            if not isinstance(vuln, dict):
                raise ValueError("dependency audit vulnerability entries must be objects")
            vuln_id = str(vuln.get("id", "")).strip()
            if not vuln_id:
                raise ValueError("dependency audit vulnerability entries must include an id")
            aliases = vuln.get("aliases", [])
            fix_versions = vuln.get("fix_versions", [])
            if not isinstance(aliases, list) or not isinstance(fix_versions, list):
                raise ValueError(
                    "dependency audit vulnerability aliases and fix_versions must be lists"
                )
            findings.append(
                AuditFinding(
                    package=package,
                    version=version,
                    vuln_id=vuln_id,
                    aliases=tuple(str(alias) for alias in aliases),
                    fix_versions=tuple(str(fix_version) for fix_version in fix_versions),
                    description=str(vuln.get("description", "")).strip(),
                )
            )
    return tuple(findings)


def split_findings(
    findings: tuple[AuditFinding, ...],
    allowlist: tuple[AllowlistEntry, ...],
) -> tuple[tuple[AuditFinding, ...], tuple[AuditFinding, ...], tuple[AllowlistEntry, ...]]:
    allowlist_by_key = {
        (entry.package.lower(), entry.version, entry.vuln_id): entry for entry in allowlist
    }
    allowed: list[AuditFinding] = []
    blocked: list[AuditFinding] = []
    used_keys: set[tuple[str, str, str]] = set()
    for finding in findings:
        if finding.key in allowlist_by_key and not finding.fix_versions:
            allowed.append(finding)
            used_keys.add(finding.key)
        else:
            blocked.append(finding)
    stale = tuple(
        entry
        for entry in allowlist
        if (entry.package.lower(), entry.version, entry.vuln_id) not in used_keys
    )
    return (tuple(allowed), tuple(blocked), stale)


def _run_command(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 - fixed repo-owned argv only, no shell execution
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def export_frozen_requirements(*, repo_root: Path, uv_bin: str, output_path: Path) -> None:
    result = _run_command(
        [
            uv_bin,
            "export",
            "--frozen",
            "--extra",
            "dev",
            "--format",
            "requirements-txt",
            "--no-hashes",
            "--no-emit-project",
            "-o",
            str(output_path),
        ],
        cwd=repo_root,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "uv export failed")


def run_pip_audit(
    *,
    repo_root: Path,
    uv_bin: str,
    requirements_path: Path,
    report_path: Path,
) -> tuple[int, str]:
    result = _run_command(
        [
            uv_bin,
            "run",
            "--no-sync",
            "python",
            "-m",
            "pip_audit",
            "-r",
            str(requirements_path),
            "--format",
            "json",
            "--progress-spinner",
            "off",
            "--strict",
            "-o",
            str(report_path),
        ],
        cwd=repo_root,
    )
    combined_output = "\n".join(
        line for line in (result.stdout.strip(), result.stderr.strip()) if line
    ).strip()
    return (result.returncode, combined_output)


def _format_finding(finding: AuditFinding) -> str:
    detail = f"{finding.package} {finding.version} {finding.vuln_id}"
    if finding.fix_versions:
        detail += f" fix_versions={','.join(finding.fix_versions)}"
    return detail


def main() -> int:
    repo_root = REPO_ROOT
    uv_bin = str(Path(sys.argv[1] if len(sys.argv) > 1 else "uv"))

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        requirements_path = temp_path / "requirements.txt"
        report_path = temp_path / "pip-audit.json"

        print(
            "dependency-audit: auditing the exported frozen dependency set for known vulnerabilities"
        )
        export_frozen_requirements(
            repo_root=repo_root, uv_bin=uv_bin, output_path=requirements_path
        )
        exit_code, audit_output = run_pip_audit(
            repo_root=repo_root,
            uv_bin=uv_bin,
            requirements_path=requirements_path,
            report_path=report_path,
        )

        if exit_code not in {0, 1}:
            if audit_output:
                print(audit_output)
            print("dependency-audit: pip-audit failed before findings could be evaluated.")
            return 2

        report = json.loads(report_path.read_text(encoding="utf-8"))
        try:
            findings = parse_audit_report(report)
            allowlist = load_allowlist()
        except ValueError as exc:
            print(f"dependency-audit failed: {exc}")
            return 2
        allowed, blocked, stale = split_findings(findings, allowlist)

        if blocked:
            print(
                "dependency-audit failed: actionable vulnerabilities remain after allowlist filtering."
            )
            for finding in blocked:
                print(f"- {_format_finding(finding)}")
            if stale:
                print(
                    "dependency-audit failed: stale allowlist entries no longer match current findings."
                )
                for entry in stale:
                    print(
                        "- stale allowlist entry: "
                        f"{entry.package} {entry.version} {entry.vuln_id} "
                        f"(review_after={entry.review_after})"
                    )
            return 1

        if stale:
            print(
                "dependency-audit failed: stale allowlist entries no longer match current findings."
            )
            for entry in stale:
                print(
                    "- stale allowlist entry: "
                    f"{entry.package} {entry.version} {entry.vuln_id} "
                    f"(review_after={entry.review_after})"
                )
            return 1

        if allowed:
            print(
                "dependency-audit: applying repo-owned allowlist entries from "
                "config/security/dependency_audit_allowlist.json"
            )
            for finding in allowed:
                entry = next(
                    item
                    for item in allowlist
                    if (item.package.lower(), item.version, item.vuln_id) == finding.key
                )
                print(
                    "- allowed: "
                    f"{_format_finding(finding)} "
                    f"(review_after={entry.review_after}; reason={entry.reason})"
                )

        print("dependency-audit passed: no actionable vulnerabilities remain.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
