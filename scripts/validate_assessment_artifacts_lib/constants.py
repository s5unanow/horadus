"""Shared constants and patterns for assessment artifact validation."""

from __future__ import annotations

import re

ALLOWED_AREAS = {
    "api",
    "core",
    "storage",
    "ingestion",
    "processing",
    "workers",
    "repo",
    "docs",
    "security",
    "ops",
}

ALLOWED_GATES = {"AUTO_OK", "HUMAN_REVIEW", "REQUIRES_HUMAN"}

RE_PROPOSAL_HEADING = re.compile(r"^###\s+((?:PROPOSAL|FINDING)-[A-Za-z0-9._:-]+)\s*$")
RE_FORBIDDEN_TASK_HEADING = re.compile(r"^###\s+TASK-\d{3}\b")
RE_FIELD_LINE = re.compile(r"^\s*([A-Za-z_ ]+)\s*:\s*(.*?)\s*$")
RE_DAILY_FILENAME_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})\.md$")
RE_TITLE_DATE = re.compile(r"^#\s+.+?(\d{4}-\d{2}-\d{2})\s*$")
RE_PROPOSAL_DATE = re.compile(r"^(?:PROPOSAL|FINDING)-(\d{4}-\d{2}-\d{2})-")
RE_TASK_REFERENCE = re.compile(r"\bTASK-\d{3}\b")
RE_SPRINT_DATES = re.compile(
    r"^\*\*Sprint Dates\*\*:\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})\s*$"
)
RE_ACTIVE_SPRINT_TASK = re.compile(r"^-\s+`(TASK-\d{3})`")
RE_PRIORITY = re.compile(r"^P[0-3]$")
RE_ALL_CLEAR = re.compile(r"\ball clear\b", re.IGNORECASE)
RE_TASK_TITLE = re.compile(r"^###\s+(TASK-\d+):\s+(.+?)\s*$")
RE_COMPLETED_TASK = re.compile(r"^-\s+(TASK-\d+):\s+(.+?)\s+✅\s*$")

REQUIRED_FIELDS = {
    "area",
    "priority",
    "confidence",
    "estimate",
    "verification",
    "blast_radius",
    "recommended_gate",
}

FIELD_ALIASES = {
    "proposal_id": "proposal_id",
    "area": "area",
    "priority": "priority",
    "confidence": "confidence",
    "estimate": "estimate",
    "recommended_gate": "recommended_gate",
    "verification": "verification",
    "blast_radius": "blast_radius",
    "blast radius": "blast_radius",
}

NON_FIELD_SECTION_ALIASES = {
    "problem",
    "proposed_change",
    "proposed change",
    "summary",
    "delta",
    "delta since prior report",
    "delta_since_prior_report",
    "new evidence",
    "new_evidence",
    "change since last report",
    "change_since_last_report",
    "updated scope",
    "updated_scope",
    "scope reviewed",
    "scope_reviewed",
}

TOKEN_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}

DELTA_HINT_PATTERN = re.compile(
    r"\b(delta since prior report|new evidence|change since last report|updated scope)\b",
    re.IGNORECASE,
)
CURRENT_TASK_ASSERTION_PATTERN = re.compile(
    r"\b(active|current|remaining|open|overdue|blocker|blockers|human-gated|"
    r"launch blocker|still|today|next_action|decision required)\b",
    re.IGNORECASE,
)
HISTORICAL_TASK_MARKER_PATTERN = re.compile(
    r"(?:\[(?:historical|completed|closed)\]|"
    r"\b(?:historical|completed|closed|prior|previous|earlier|former|formerly|"
    r"past|reference(?:d)?|carryover|already implemented)\b)",
    re.IGNORECASE,
)

ROLE_PREFIXES = {"po", "ba", "sa", "security", "agents"}
SLUG_SIMILARITY_THRESHOLD = 0.6
BODY_SIMILARITY_THRESHOLD = 0.72
