from __future__ import annotations

import sys
import types
from typing import Any

from tools.horadus.python.horadus_workflow import _task_preflight_checks as checks_module
from tools.horadus.python.horadus_workflow import _task_preflight_eligibility as eligibility_module
from tools.horadus.python.horadus_workflow import _task_preflight_guard as guard_module
from tools.horadus.python.horadus_workflow import _task_preflight_intake as intake_module
from tools.horadus.python.horadus_workflow import _task_preflight_start as start_module
from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow.result import CommandResult, ExitCode

_MODULE_EXPORTS: dict[object, list[str]] = {
    intake_module: list(intake_module.__all__),
    checks_module: list(checks_module.__all__),
    guard_module: list(guard_module.__all__),
    eligibility_module: list(eligibility_module.__all__),
    start_module: list(start_module.__all__),
}

_EXPORT_SOURCES: dict[str, object] = {}
for module, names in _MODULE_EXPORTS.items():
    for name in names:
        globals()[name] = getattr(module, name)
        _EXPORT_SOURCES[name] = module


class _CompatModule(types.ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        source = _EXPORT_SOURCES.get(name)
        if source is not None:  # pragma: no branch
            setattr(source, name, value)


def handle_preflight(_args: Any) -> CommandResult:
    return guard_module._preflight_result()


def handle_eligibility(args: Any) -> CommandResult:
    try:
        task_id = task_repo.normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = eligibility_module.eligibility_data(task_id)
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_start(args: Any) -> CommandResult:
    try:
        task_id = task_repo.normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = start_module.start_task_data(
        task_id, args.name, dry_run=bool(args.dry_run)
    )
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_safe_start(args: Any) -> CommandResult:
    try:
        task_id = task_repo.normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = start_module.safe_start_task_data(
        task_id, args.name, dry_run=bool(args.dry_run)
    )
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


_module = sys.modules[__name__]
if not isinstance(_module, _CompatModule):  # pragma: no branch
    _module.__class__ = _CompatModule

__all__ = sorted(
    [
        *_EXPORT_SOURCES,
        "handle_eligibility",
        "handle_preflight",
        "handle_safe_start",
        "handle_start",
    ]
)
