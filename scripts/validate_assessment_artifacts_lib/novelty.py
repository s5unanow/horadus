"""Novelty and proposal-similarity helpers for assessment artifacts."""

from __future__ import annotations

import re
from pathlib import Path

from .artifacts import parse_artifact, proposal_body_text
from .constants import (
    BODY_SIMILARITY_THRESHOLD,
    DELTA_HINT_PATTERN,
    RE_PROPOSAL_DATE,
    ROLE_PREFIXES,
    SLUG_SIMILARITY_THRESHOLD,
    TOKEN_STOPWORDS,
)
from .history import history_artifacts_for_file, load_task_titles
from .models import Finding, ParsedArtifact, ProposalBlock


def normalize_slug(proposal_id: str) -> str:
    match = RE_PROPOSAL_DATE.match(proposal_id)
    slug = proposal_id
    if match:
        slug = proposal_id.split("-", 4)[4]
    parts = [part for part in slug.split("-") if part]
    if parts and parts[0] in ROLE_PREFIXES:
        parts = parts[1:]
    return "-".join(parts)


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in TOKEN_STOPWORDS and len(token) > 1
    }


def token_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    intersection = left & right
    union = left | right
    return len(intersection) / len(union)


def proposal_has_explicit_delta(proposal: ProposalBlock) -> bool:
    for key in (
        "delta",
        "delta_since_prior_report",
        "new_evidence",
        "change_since_last_report",
        "updated_scope",
    ):
        if proposal.sections.get(key, "").strip():
            return True
    return bool(DELTA_HINT_PATTERN.search(proposal_body_text(proposal)))


def similar_history_match(
    proposal: ProposalBlock,
    *,
    history: list[ParsedArtifact],
) -> tuple[ProposalBlock, Path, float] | None:
    slug_tokens = tokenize(normalize_slug(proposal.proposal_id))
    body_tokens = tokenize(proposal_body_text(proposal))

    prior_match: tuple[ProposalBlock, Path, float] | None = None
    for previous in history:
        for previous_proposal in previous.proposals:
            prev_slug_tokens = tokenize(normalize_slug(previous_proposal.proposal_id))
            prev_body_tokens = tokenize(proposal_body_text(previous_proposal))
            slug_similarity = token_similarity(slug_tokens, prev_slug_tokens)
            body_similarity = token_similarity(body_tokens, prev_body_tokens)
            if (
                slug_similarity >= SLUG_SIMILARITY_THRESHOLD
                or body_similarity >= BODY_SIMILARITY_THRESHOLD
            ):
                score = max(slug_similarity, body_similarity)
                if prior_match is None or score > prior_match[2]:
                    prior_match = (previous_proposal, previous.path, score)

    return prior_match


def novelty_findings_for_file(
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
        include_same_role=True,
    )

    task_titles = load_task_titles(repo_root)
    findings: list[Finding] = []
    novel_count = 0

    for proposal in artifact.proposals:
        if proposal_has_explicit_delta(proposal):
            novel_count += 1
            continue

        slug_tokens = tokenize(normalize_slug(proposal.proposal_id))
        prior_match = similar_history_match(proposal, history=history)

        if prior_match is not None:
            findings.append(
                Finding(
                    path=path,
                    line_no=proposal.line_no,
                    message=(
                        f"{proposal.proposal_id}: non-novel within {lookback_days} days; "
                        f"matches prior same-role proposal {prior_match[0].proposal_id} in "
                        f"{prior_match[1].as_posix()} (similarity {prior_match[2]:.2f}). "
                        "Add an explicit delta section or emit 'All clear'."
                    ),
                )
            )
            continue

        task_match: tuple[str, str, float] | None = None
        for task_id, task_title in task_titles:
            task_tokens = tokenize(task_title)
            score = token_similarity(slug_tokens, task_tokens)
            if (
                score >= SLUG_SIMILARITY_THRESHOLD
                or (len(slug_tokens & task_tokens) >= 2 and score >= 0.5)
            ) and (task_match is None or score > task_match[2]):
                task_match = (task_id, task_title, score)

        if task_match is not None:
            findings.append(
                Finding(
                    path=path,
                    line_no=proposal.line_no,
                    message=(
                        f"{proposal.proposal_id}: already captured in task ledger by "
                        f"{task_match[0]} ({task_match[1]}) (similarity {task_match[2]:.2f}); "
                        "adjust the proposal with an explicit delta or emit 'All clear'."
                    ),
                )
            )
            continue

        novel_count += 1

    if novel_count == 0:
        findings.append(
            Finding(
                path=path,
                line_no=1,
                message=(
                    f"no materially new proposals remain after {lookback_days}-day novelty "
                    "check; emit an explicit 'All clear' report instead."
                ),
            )
        )

    return findings
