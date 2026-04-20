from __future__ import annotations

import shutil
import subprocess  # nosec B404
import sys
import time
import types

from tools.horadus.python.horadus_workflow import result as result_module
from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import (
    task_workflow_automation_lock as automation_lock_module,
)
from tools.horadus.python.horadus_workflow import task_workflow_finish as finish_module
from tools.horadus.python.horadus_workflow import task_workflow_friction as friction_module
from tools.horadus.python.horadus_workflow import task_workflow_intake as intake_module
from tools.horadus.python.horadus_workflow import task_workflow_ledgers as ledgers_module
from tools.horadus.python.horadus_workflow import task_workflow_lifecycle as lifecycle_module
from tools.horadus.python.horadus_workflow import task_workflow_local_review as local_review_module
from tools.horadus.python.horadus_workflow import task_workflow_preflight as preflight_module
from tools.horadus.python.horadus_workflow import task_workflow_query as query_module
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared_module

_MODULE_EXPORTS: dict[object, list[str]] = {
    result_module: [
        "CommandResult",
        "ExitCode",
    ],
    task_repo: [
        "CLOSED_TASK_ARCHIVE_GUIDANCE",
        "TaskClosureState",
        "active_section_text",
        "archived_task_record",
        "backlog_path",
        "closed_tasks_archive_path",
        "completed_path",
        "current_date",
        "current_sprint_path",
        "exec_plan_paths_for_task",
        "normalize_task_id",
        "parse_active_tasks",
        "parse_human_blockers",
        "planning_gates_required",
        "planning_gates_value_from_text",
        "repo_root",
        "search_task_records",
        "slugify_name",
        "spec_paths_for_task",
        "task_block_match",
        "task_closure_state",
        "task_id_from_exec_plan_path",
        "task_id_from_spec_path",
        "task_planning_gates_value",
        "task_record",
        "task_requires_exec_plan",
    ],
    shared_module: list(shared_module.__all__),
    preflight_module: list(preflight_module.__all__),
    intake_module: list(intake_module.__all__),
    ledgers_module: list(ledgers_module.__all__),
    lifecycle_module: list(lifecycle_module.__all__),
    automation_lock_module: list(automation_lock_module.__all__),
    local_review_module: list(local_review_module.__all__),
    finish_module: list(finish_module.__all__),
    query_module: list(query_module.__all__),
    friction_module: list(friction_module.__all__),
}

_EXPORT_SOURCES: dict[str, object] = {}
for module, names in _MODULE_EXPORTS.items():
    for name in names:
        globals()[name] = getattr(module, name)
        if module is not task_repo and module is not result_module:
            _EXPORT_SOURCES[name] = module

for name, module in {
    "shutil": shutil,
    "subprocess": subprocess,
    "sys": sys,
    "time": time,
}.items():
    globals()[name] = module


class _CompatModule(types.ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        source = _EXPORT_SOURCES.get(name)
        if source is not None:
            setattr(source, name, value)


_module = sys.modules[__name__]
if not isinstance(_module, _CompatModule):  # pragma: no branch
    _module.__class__ = _CompatModule

__all__ = sorted(_EXPORT_SOURCES)
