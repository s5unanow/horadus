"""Cross-role overlap validation for assessment artifacts."""

from __future__ import annotations

from pathlib import Path

from .artifacts import parse_artifact, role_from_path
from .history import history_artifacts_for_file
from .models import Finding
from .novelty import proposal_has_explicit_delta, similar_history_match


def cross_role_overlap_findings_for_file(
    path: Path,
    *,
    lookback_days: int,
    all_files: list[Path],
    repo_root: Path,
) -> list[Finding]:
    artifact = parse_artifact(path)
    if artifact.is_all_clear or not artifact.proposals or artifact.role is None:
        return []

    history = history_artifacts_for_file(
        artifact,
        lookback_days=lookback_days,
        all_files=all_files,
        repo_root=repo_root,
        include_same_role=False,
    )
    if not history:
        return []

    findings: list[Finding] = []
    novel_count = 0
    for proposal in artifact.proposals:
        if proposal_has_explicit_delta(proposal):
            novel_count += 1
            continue

        prior_match = similar_history_match(proposal, history=history)
        if prior_match is None:
            novel_count += 1
            continue

        prior_role = role_from_path(prior_match[1]) or "unknown"
        findings.append(
            Finding(
                path=path,
                line_no=proposal.line_no,
                message=(
                    f"{proposal.proposal_id}: overlaps with recent {prior_role} proposal "
                    f"{prior_match[0].proposal_id} in {prior_match[1].as_posix()} "
                    f"(similarity {prior_match[2]:.2f}). Suppress the duplicate, record the "
                    "suppression in automation memory/log output, add an explicit delta, or "
                    "emit 'All clear'."
                ),
            )
        )

    if novel_count == 0:
        findings.append(
            Finding(
                path=path,
                line_no=1,
                message=(
                    f"no materially new cross-role proposals remain after {lookback_days}-day "
                    "overlap check; emit an explicit 'All clear' report instead."
                ),
            )
        )

    return findings
