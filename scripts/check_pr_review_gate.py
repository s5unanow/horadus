#!/usr/bin/env python3
"""Wait through the PR review window and fail on actionable current-head bot comments."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.horadus.python.horadus_workflow.pr_review_gate import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
