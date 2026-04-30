from __future__ import annotations

REQUIRED_TOKENS: tuple[str, ...] = (
    "uv run --no-sync horadus trends status",
    "uv run --no-sync horadus dashboard export",
    "uv run --no-sync horadus eval benchmark",
    "--tier-scope tier1",
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
