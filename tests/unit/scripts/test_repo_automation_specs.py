from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
AUTOMATION_IDS = REPO_ROOT / "ops" / "automations" / "ids.txt"
AUTOMATION_SPECS = REPO_ROOT / "ops" / "automations" / "specs"
AUTOMATION_INSTRUCTIONS = REPO_ROOT / "agents" / "automation"
AUTOPILOT_INSTRUCTIONS = AUTOMATION_INSTRUCTIONS / "horadus-sprint-autopilot.md"


def _read_ids() -> list[str]:
    ids: list[str] = []
    for raw in AUTOMATION_IDS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        ids.append(line)
    return ids


def test_repo_owned_automation_specs_have_expected_instruction_targets() -> None:
    ids = _read_ids()
    expected_instruction_dir = AUTOMATION_INSTRUCTIONS.relative_to(REPO_ROOT)

    for automation_id in ids:
        spec_path = AUTOMATION_SPECS / f"{automation_id}.toml"
        assert spec_path.exists(), f"missing automation spec: {spec_path}"

        spec = tomllib.loads(spec_path.read_text(encoding="utf-8"))
        assert spec["id"] == automation_id

        prompt = spec["prompt"]
        assert isinstance(prompt, str)
        if not prompt.startswith("Open and follow: "):
            pytest.fail(f"{automation_id} should keep the spec prompt minimal")

        instruction_path_raw = prompt.splitlines()[0].removeprefix("Open and follow: ").strip()
        instruction_path = Path(instruction_path_raw)
        if not instruction_path.is_absolute():
            pytest.fail(f"instruction path should be absolute: {instruction_path}")

        repo_relative_instruction = Path(
            *instruction_path.parts[-len(expected_instruction_dir.parts) - 1 :]
        )
        assert repo_relative_instruction.parent == expected_instruction_dir
        if not (REPO_ROOT / repo_relative_instruction).exists():
            pytest.fail(f"missing automation instructions: {repo_relative_instruction}")


def test_horadus_sprint_autopilot_instructions_cover_resume_and_main_sync() -> None:
    instructions = AUTOPILOT_INSTRUCTIONS.read_text(encoding="utf-8")

    assert "codex/rules/default.rules" in instructions
    assert "automations/horadus-sprint-autopilot/lock" in instructions
    assert "horadus tasks automation-lock lock --path" in instructions
    assert "horadus tasks automation-lock unlock --path" in instructions
    assert "git pull --ff-only" in instructions
    assert "open non-merged task PR" in instructions
    assert "uv run --no-sync horadus tasks finish TASK-XXX" in instructions
    assert "stop this automation run" in instructions
