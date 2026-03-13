from __future__ import annotations

from typing import Any

from ._task_preflight_checks import _ensure_required_hooks, _open_task_prs
from ._task_preflight_eligibility import eligibility_data
from ._task_preflight_guard import _preflight_result, task_preflight_data
from ._task_preflight_intake import (
    TaskLedgerIntakeState,
    _backlog_task_id_for_line,
    _changed_line_numbers,
    _diff_texts_for_path,
    _dirty_task_refs_for_path,
    _git_status_dirty_paths,
    _head_text_for_path,
    _index_text_for_path,
    _path_owned_task_start_intake_ref,
    _path_owned_task_start_intake_refs_from_diff,
    _task_ledger_intake_state,
    _working_tree_text_for_path,
)
from ._task_preflight_start import safe_start_task_data, start_task_data
from .result import CommandResult

def handle_preflight(_args: Any) -> CommandResult: ...
def handle_eligibility(args: Any) -> CommandResult: ...
def handle_start(args: Any) -> CommandResult: ...
def handle_safe_start(args: Any) -> CommandResult: ...

__all__ = [
    "TaskLedgerIntakeState",
    "_backlog_task_id_for_line",
    "_changed_line_numbers",
    "_diff_texts_for_path",
    "_dirty_task_refs_for_path",
    "_ensure_required_hooks",
    "_git_status_dirty_paths",
    "_head_text_for_path",
    "_index_text_for_path",
    "_open_task_prs",
    "_path_owned_task_start_intake_ref",
    "_path_owned_task_start_intake_refs_from_diff",
    "_preflight_result",
    "_task_ledger_intake_state",
    "_working_tree_text_for_path",
    "eligibility_data",
    "handle_eligibility",
    "handle_preflight",
    "handle_safe_start",
    "handle_start",
    "safe_start_task_data",
    "start_task_data",
    "task_preflight_data",
]
