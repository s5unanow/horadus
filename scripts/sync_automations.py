#!/usr/bin/env python3
"""
Sync Codex automations between local $CODEX_HOME and repo-owned desired state.

This script intentionally avoids tracking volatile run-state fields (created_at,
updated_at) in git. The repo stores "specs" only; applying specs writes
timestamps only into $CODEX_HOME.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

DROP_KEYS = {"created_at", "updated_at"}


@dataclass(frozen=True)
class Paths:
    codex_home: Path
    repo_dir: Path
    ids_file: Path
    specs_dir: Path


def _now_ms() -> int:
    return int(time.time() * 1000)


def _read_ids(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"ids file not found: {path}")
    ids: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        ids.append(line)
    return ids


def _load_toml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"toml not found: {path}")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _toml_scalar(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    raise TypeError(f"unsupported TOML scalar type: {type(value).__name__}")


def _toml_value(value: object) -> str:
    if isinstance(value, str | bool | int):
        return _toml_scalar(value)
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if not isinstance(item, str | bool | int):
                raise TypeError(f"unsupported TOML list item type: {type(item).__name__}")
            parts.append(_toml_scalar(item))
        return "[" + ", ".join(parts) + "]"
    raise TypeError(f"unsupported TOML value type: {type(value).__name__}")


def _dump_toml(data: dict, *, created_at: int | None = None, updated_at: int | None = None) -> str:
    # Stable ordering for readability. Unknown keys (if any) are appended sorted.
    preferred = [
        "version",
        "id",
        "name",
        "prompt",
        "status",
        "rrule",
        "execution_environment",
        "cwds",
    ]
    keys = [k for k in preferred if k in data] + sorted([k for k in data if k not in preferred])

    lines: list[str] = []
    for k in keys:
        lines.append(f"{k} = {_toml_value(data[k])}")

    if created_at is not None:
        lines.append(f"created_at = {created_at}")
    if updated_at is not None:
        lines.append(f"updated_at = {updated_at}")

    return "\n".join(lines) + "\n"


def _automation_toml_path(codex_home: Path, automation_id: str) -> Path:
    return codex_home / "automations" / automation_id / "automation.toml"


def export_specs(paths: Paths) -> int:
    ids = _read_ids(paths.ids_file)
    paths.specs_dir.mkdir(parents=True, exist_ok=True)

    for automation_id in ids:
        src = _automation_toml_path(paths.codex_home, automation_id)
        data = _load_toml(src)
        if data.get("id") != automation_id:
            raise ValueError(f"id mismatch for {automation_id}: toml has id={data.get('id')!r}")
        sanitized = {k: v for k, v in data.items() if k not in DROP_KEYS}
        dest = paths.specs_dir / f"{automation_id}.toml"
        dest.write_text(_dump_toml(sanitized), encoding="utf-8")

    print(f"Exported {len(ids)} automation spec(s) to: {paths.specs_dir}")
    return 0


def apply_specs(paths: Paths) -> int:
    ids = _read_ids(paths.ids_file)

    for automation_id in ids:
        spec_path = paths.specs_dir / f"{automation_id}.toml"
        spec = _load_toml(spec_path)
        if spec.get("id") != automation_id:
            raise ValueError(f"id mismatch for {automation_id}: spec has id={spec.get('id')!r}")

        dest = _automation_toml_path(paths.codex_home, automation_id)
        dest.parent.mkdir(parents=True, exist_ok=True)

        created_at: int
        if dest.exists():
            existing = _load_toml(dest)
            created_at = int(existing.get("created_at") or _now_ms())
        else:
            created_at = _now_ms()

        updated_at = _now_ms()
        dest.write_text(
            _dump_toml(spec, created_at=created_at, updated_at=updated_at), encoding="utf-8"
        )

    print(f"Applied {len(ids)} automation spec(s) into: {paths.codex_home / 'automations'}")
    return 0


def _resolve_paths(*, codex_home: str | None, repo_dir: str | None) -> Paths:
    default_codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    ch = Path(codex_home).expanduser() if codex_home else default_codex_home
    rd = Path(repo_dir).expanduser() if repo_dir else Path("ops/automations")
    return Paths(
        codex_home=ch,
        repo_dir=rd,
        ids_file=rd / "ids.txt",
        specs_dir=rd / "specs",
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Export/apply repo-owned Codex automation desired state."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_export = sub.add_parser("export", help="Export local Codex automation TOMLs into repo specs.")
    p_export.add_argument("--codex-home", default=None)
    p_export.add_argument("--repo-dir", default=None)

    p_apply = sub.add_parser("apply", help="Apply repo specs into local Codex automation TOMLs.")
    p_apply.add_argument("--codex-home", default=None)
    p_apply.add_argument("--repo-dir", default=None)

    ns = parser.parse_args(argv)
    paths = _resolve_paths(codex_home=ns.codex_home, repo_dir=ns.repo_dir)

    try:
        if ns.cmd == "export":
            return export_specs(paths)
        if ns.cmd == "apply":
            return apply_specs(paths)
        raise AssertionError(f"unhandled cmd: {ns.cmd}")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
