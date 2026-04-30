from __future__ import annotations

from pathlib import Path

from ._docs_freshness_models import DocsFreshnessIssue
from ._docs_freshness_parsing import _normalize_whitespace

_REFERENCE_PATHS: tuple[str, ...] = (
    "ops/skills/horadus-cli/SKILL.md",
    "ops/skills/horadus-cli/references/commands.md",
)
_REQUIRED_TOKENS: tuple[str, ...] = (
    "uv run --no-sync horadus trends status",
    "uv run --no-sync horadus dashboard export",
    "uv run --no-sync horadus eval benchmark",
    "--tier-scope tier2",
    "uv run --no-sync horadus pipeline dry-run",
    "uv run --no-sync horadus agent smoke",
    "uv run --no-sync horadus doctor",
    "uv run --no-sync horadus tasks close-ledgers TASK-XXX",
    "uv run --no-sync horadus tasks intake add",
    "uv run --no-sync horadus tasks automation-lock check",
    "uv run --no-sync horadus eval behavior",
    "uv run --no-sync horadus eval validate-taxonomy",
    "uv run --no-sync horadus eval regression-intake",
    "uv run --no-sync horadus eval code-health",
    "uv run --no-sync horadus eval vector-benchmark",
    "uv run --no-sync horadus eval embedding-lineage",
    "uv run --no-sync horadus eval source-freshness",
)


def check_horadus_cli_skill_references(
    *,
    repo_root: Path,
    errors: list[DocsFreshnessIssue],
) -> None:
    missing_paths: list[str] = []
    content_parts: list[str] = []
    for reference_path in _REFERENCE_PATHS:
        file_path = repo_root / reference_path
        if file_path.exists():
            content_parts.append(file_path.read_text(encoding="utf-8"))
        else:
            missing_paths.append(reference_path)

    _record_missing_reference_errors(errors=errors, missing_paths=missing_paths)
    normalized_content = _normalize_whitespace("\n".join(content_parts))
    errors.extend(
        DocsFreshnessIssue(
            level="error",
            rule_id="horadus_cli_skill_command_reference_missing",
            message=f"Horadus CLI skill must document command or option reference: {token}",
            path=_REFERENCE_PATHS[0],
        )
        for token in _REQUIRED_TOKENS
        if _normalize_whitespace(token) not in normalized_content
    )


def _record_missing_reference_errors(
    *,
    errors: list[DocsFreshnessIssue],
    missing_paths: list[str],
) -> None:
    errors.extend(
        DocsFreshnessIssue(
            level="error",
            rule_id="horadus_cli_skill_reference_file_missing",
            message=f"Missing Horadus CLI skill reference file: {path}",
            path=path,
        )
        for path in missing_paths
    )
