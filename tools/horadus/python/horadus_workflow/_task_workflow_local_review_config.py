from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

from tools.horadus.python.horadus_workflow import task_repo

from ._task_workflow_local_review_constants import (
    LOCAL_REVIEW_DIRECTORY,
    LOCAL_REVIEW_HARNESS_PATH,
    LOCAL_REVIEW_LOG_FILENAME,
    LOCAL_REVIEW_RUNS_DIRECTORY,
    SUPPORTED_LOCAL_REVIEW_PROVIDERS,
)


def _local_review_log_path() -> Path:
    return task_repo.repo_root() / LOCAL_REVIEW_DIRECTORY / LOCAL_REVIEW_LOG_FILENAME


def _local_review_runs_dir() -> Path:
    return task_repo.repo_root() / LOCAL_REVIEW_RUNS_DIRECTORY


def _harness_value(name: str) -> str | None:
    raw = os.getenv(name)
    if raw is not None and raw.strip():
        return raw.strip()
    env_path = task_repo.repo_root() / LOCAL_REVIEW_HARNESS_PATH
    if not env_path.exists():
        return None
    value = dotenv_values(env_path).get(name)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _provider_attempt_order(
    primary_provider: str,
    *,
    selection_source: str,
    allow_provider_fallback: bool,
) -> list[str]:
    if selection_source == "cli" and not allow_provider_fallback:
        return [primary_provider]
    return [
        primary_provider,
        *[
            provider
            for provider in SUPPORTED_LOCAL_REVIEW_PROVIDERS
            if provider != primary_provider
        ],
    ]
