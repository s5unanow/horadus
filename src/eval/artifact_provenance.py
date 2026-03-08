"""
Shared provenance helpers for evaluation artifacts.
"""

from __future__ import annotations

import hashlib
import json
import subprocess  # nosec
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

_REPO_ROOT = Path(__file__).resolve().parents[2]


def build_source_control_provenance(*, repo_root: Path | None = None) -> dict[str, Any]:
    resolved_root = (repo_root or _REPO_ROOT).resolve()
    commit_sha = _run_git_command(("rev-parse", "HEAD"), repo_root=resolved_root)
    if commit_sha is None:
        return {
            "git": {
                "available": False,
                "repo_root": str(resolved_root),
                "commit_sha": None,
                "worktree_dirty": None,
                "branch": None,
            }
        }

    branch = _run_git_command(("rev-parse", "--abbrev-ref", "HEAD"), repo_root=resolved_root)
    status_output = _run_git_command(("status", "--porcelain"), repo_root=resolved_root)
    return {
        "git": {
            "available": True,
            "repo_root": str(resolved_root),
            "commit_sha": commit_sha,
            "worktree_dirty": bool(status_output),
            "branch": branch,
        }
    }


def build_file_manifest_provenance(
    paths: Mapping[str, str | Path],
) -> dict[str, dict[str, str]]:
    payload: dict[str, dict[str, str]] = {}
    for label, raw_path in sorted(paths.items()):
        path = Path(raw_path)
        raw_text = path.read_text(encoding="utf-8")
        payload[label] = {
            "path": str(path),
            "sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        }
    return payload


def build_directory_provenance(
    *,
    directory: str | Path,
    patterns: tuple[str, ...] = ("*.yaml", "*.yml"),
    files: Sequence[str | Path] | None = None,
    recursive: bool = False,
) -> dict[str, Any]:
    resolved_directory = Path(directory).resolve()
    if files is None:
        discovered_files: list[Path] = []
        for pattern in patterns:
            matcher = resolved_directory.rglob if recursive else resolved_directory.glob
            discovered_files.extend(matcher(pattern))
    else:
        discovered_files = [Path(path) for path in files]
    unique_files = sorted({path.resolve() for path in discovered_files})

    file_payloads: list[dict[str, str]] = []
    digest_inputs: list[str] = []
    for path in unique_files:
        raw_text = path.read_text(encoding="utf-8")
        content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        try:
            display_path = path.relative_to(resolved_directory).as_posix()
        except ValueError:
            display_path = str(path)
        file_payloads.append({"path": display_path, "sha256": content_hash})
        digest_inputs.append(f"{display_path}:{content_hash}")

    fingerprint_source = "\n".join(digest_inputs)
    fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
    return {
        "path": str(resolved_directory),
        "file_count": len(file_payloads),
        "files": file_payloads,
        "fingerprint_sha256": fingerprint,
    }


def normalize_request_overrides(request_overrides: dict[str, Any] | None) -> dict[str, Any] | None:
    if request_overrides is None:
        return None
    canonical = json.dumps(request_overrides, sort_keys=True, separators=(",", ":"))
    return cast("dict[str, Any]", json.loads(canonical))


def gold_set_fingerprint(items: list[Any]) -> str:
    canonical_rows: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda row: str(row.item_id)):
        row: dict[str, Any] = {
            "item_id": item.item_id,
            "title": item.title,
            "content": item.content,
            "label_verification": item.label_verification,
            "tier1": {
                "trend_scores": item.tier1.trend_scores,
                "max_relevance": item.tier1.max_relevance,
            },
            "tier2": None,
        }
        if item.tier2 is not None:
            row["tier2"] = {
                "trend_id": item.tier2.trend_id,
                "signal_type": item.tier2.signal_type,
                "direction": item.tier2.direction,
                "severity": item.tier2.severity,
                "confidence": item.tier2.confidence,
            }
        canonical_rows.append(row)

    payload = json.dumps(canonical_rows, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def gold_set_item_ids_fingerprint(items: list[Any]) -> str:
    normalized_ids = "\n".join(sorted(str(item.item_id) for item in items))
    return hashlib.sha256(normalized_ids.encode("utf-8")).hexdigest()


def _run_git_command(
    args: tuple[str, ...],
    *,
    repo_root: Path,
) -> str | None:
    try:
        completed = subprocess.run(  # nosec
            ["git", *args],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    output = completed.stdout.strip()
    return output or None
