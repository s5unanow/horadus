#!/usr/bin/env python3
"""
Validate assessment artifacts under artifacts/assessments/ against a minimal schema.

This is intentionally lightweight: it enforces a stable "proposal block" format
that can be produced by role agents and consumed by triage automation.
"""

from __future__ import annotations

from validate_assessment_artifacts_lib.models import Finding
from validate_assessment_artifacts_lib.runner import main
from validate_assessment_artifacts_lib.schema_validation import validate_file

__all__ = ["Finding", "main", "validate_file"]


if __name__ == "__main__":
    raise SystemExit(main())
