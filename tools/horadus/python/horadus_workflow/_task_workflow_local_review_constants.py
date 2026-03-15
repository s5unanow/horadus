from __future__ import annotations

import re
from pathlib import Path

SUPPORTED_LOCAL_REVIEW_PROVIDERS: tuple[str, ...] = ("claude", "codex", "gemini")
VALID_LOCAL_REVIEW_USEFULNESS: tuple[str, ...] = (
    "pending",
    "follow-up-changes",
    "not-useful",
)
DEFAULT_LOCAL_REVIEW_PROVIDER = "claude"
DEFAULT_LOCAL_REVIEW_BASE_BRANCH = "main"
LOCAL_REVIEW_PROVIDER_ENV = "HORADUS_LOCAL_REVIEW_PROVIDER"
LOCAL_REVIEW_HARNESS_PATH = Path(".env.harness")
LOCAL_REVIEW_DIRECTORY = Path("artifacts/agent/local-review")
LOCAL_REVIEW_LOG_FILENAME = "entries.jsonl"
LOCAL_REVIEW_RUNS_DIRECTORY = LOCAL_REVIEW_DIRECTORY / "runs"
LOCAL_REVIEW_STATUS_PATTERN = re.compile(
    r"^HORADUS-LOCAL-REVIEW:\s*(?P<status>findings|no-findings)\s*$",
    re.IGNORECASE,
)
PROVIDER_INTERFACE_KIND = {
    "claude": "prompt",
    "codex": "review",
    "gemini": "prompt",
}
PROVIDER_BINARIES = {
    "claude": "claude",
    "codex": "codex",
    "gemini": "gemini",
}
