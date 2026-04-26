from __future__ import annotations

import json


def runtime_json_stdout_line(stdout: str) -> str:
    """Return the last stdout line that is a JSON object payload."""
    fallback = ""
    for line in reversed(stdout.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        if not fallback:
            fallback = candidate
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return candidate
    return fallback
