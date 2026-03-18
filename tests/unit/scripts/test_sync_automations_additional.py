from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "sync_automations.py"


def _load_module() -> ModuleType:
    module_name = f"sync_automations_additional_{len(sys.modules)}"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_sync_automations_helper_branches(tmp_path: Path) -> None:
    module = _load_module()
    ids_file = tmp_path / "ids.txt"
    with pytest.raises(FileNotFoundError, match="ids file not found"):
        module._read_ids(ids_file)

    ids_file.write_text("# comment\n\nalpha\n", encoding="utf-8")
    assert module._read_ids(ids_file) == ["alpha"]

    with pytest.raises(FileNotFoundError, match="toml not found"):
        module._load_toml(tmp_path / "missing.toml")

    assert module._toml_int({}, "created_at", default=5) == 5
    assert module._toml_int({"created_at": "6"}, "created_at", default=5) == 6
    assert module._toml_scalar(True) == "true"
    assert module._toml_scalar(7) == "7"
    with pytest.raises(TypeError, match="unsupported TOML scalar type"):
        module._toml_scalar(1.5)
    with pytest.raises(TypeError, match="unsupported TOML list item type"):
        module._toml_value([object()])
    with pytest.raises(TypeError, match="unsupported TOML value type"):
        module._toml_value(object())


def test_sync_automations_export_apply_and_main_error_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_module()
    repo_dir = tmp_path / "repo"
    codex_home = tmp_path / "codex"
    repo_dir.mkdir()
    (repo_dir / "specs").mkdir()
    (repo_dir / "ids.txt").write_text("daily\n", encoding="utf-8")
    paths = module.Paths(
        codex_home=codex_home,
        repo_dir=repo_dir,
        ids_file=repo_dir / "ids.txt",
        specs_dir=repo_dir / "specs",
    )

    bad_src = codex_home / "automations" / "daily" / "automation.toml"
    bad_src.parent.mkdir(parents=True, exist_ok=True)
    bad_src.write_text('id = "other"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="id mismatch for daily"):
        module.export_specs(paths)

    good_src = codex_home / "automations" / "daily" / "automation.toml"
    good_src.write_text(
        'id = "daily"\nversion = 1\nname = "d"\nprompt = "p"\nstatus = "ACTIVE"\nrrule = "FREQ=WEEKLY;BYDAY=SU;BYHOUR=1;BYMINUTE=0"\ncwds = ["/tmp"]\n',
        encoding="utf-8",
    )
    assert module.export_specs(paths) == 0
    assert (repo_dir / "specs" / "daily.toml").exists()

    (repo_dir / "specs" / "daily.toml").write_text('id = "other"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="id mismatch for daily"):
        module.apply_specs(paths)

    (repo_dir / "specs" / "daily.toml").write_text(
        'id = "daily"\nversion = 1\nname = "d"\nprompt = "p"\nstatus = "ACTIVE"\nrrule = "FREQ=WEEKLY;BYDAY=SU;BYHOUR=1;BYMINUTE=0"\ncwds = ["/tmp"]\n',
        encoding="utf-8",
    )
    assert module.apply_specs(paths) == 0
    assert (codex_home / "automations" / "daily" / "automation.toml").exists()

    fresh_paths = module.Paths(
        codex_home=tmp_path / "fresh-codex",
        repo_dir=repo_dir,
        ids_file=repo_dir / "ids.txt",
        specs_dir=repo_dir / "specs",
    )
    assert module.apply_specs(fresh_paths) == 0
    assert (fresh_paths.codex_home / "automations" / "daily" / "automation.toml").exists()

    monkeypatch.setattr(module, "_resolve_paths", lambda **_: paths)
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda _self, _argv: SimpleNamespace(cmd="export", codex_home=None, repo_dir=None),
    )
    monkeypatch.setattr(
        module, "export_specs", lambda _paths: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    assert module.main([]) == 2
    assert "ERROR: boom" in capsys.readouterr().err

    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda _self, _argv: SimpleNamespace(cmd="weird", codex_home=None, repo_dir=None),
    )
    assert module.main([]) == 2
    assert "ERROR: unhandled cmd: weird" in capsys.readouterr().err
