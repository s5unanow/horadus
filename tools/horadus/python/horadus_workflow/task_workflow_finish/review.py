from __future__ import annotations

import sys
import types

from . import _review_gate as gate_module
from . import _review_refresh as refresh_module
from . import _review_threads as threads_module
from . import _review_window as window_module

_run_review_gate = gate_module._run_review_gate
_parse_review_gate_result = gate_module._parse_review_gate_result
_unresolved_review_thread_lines = threads_module._unresolved_review_thread_lines
_review_threads = threads_module._review_threads
_review_thread_lines = threads_module._review_thread_lines
_outdated_unresolved_review_thread_ids = threads_module._outdated_unresolved_review_thread_ids
_resolve_review_threads = threads_module._resolve_review_threads
_maybe_request_fresh_review = refresh_module._maybe_request_fresh_review
_fresh_review_request_blocker = refresh_module._fresh_review_request_blocker
_needs_pre_review_fresh_review_request = refresh_module._needs_pre_review_fresh_review_request
_current_head_finish_blocker = window_module._current_head_finish_blocker
_head_changed_review_gate_blocker = window_module._head_changed_review_gate_blocker
_prepare_current_head_review_window = window_module._prepare_current_head_review_window
_review_gate_lines = window_module._review_gate_lines
review_gate_data = window_module.review_gate_data

_EXPORT_SOURCES: dict[str, object] = {
    "_run_review_gate": gate_module,
    "_parse_review_gate_result": gate_module,
    "_unresolved_review_thread_lines": threads_module,
    "_review_threads": threads_module,
    "_review_thread_lines": threads_module,
    "_outdated_unresolved_review_thread_ids": threads_module,
    "_resolve_review_threads": threads_module,
    "_maybe_request_fresh_review": refresh_module,
    "_fresh_review_request_blocker": refresh_module,
    "_needs_pre_review_fresh_review_request": refresh_module,
    "_current_head_finish_blocker": window_module,
    "_head_changed_review_gate_blocker": window_module,
    "_prepare_current_head_review_window": window_module,
    "_review_gate_lines": window_module,
}


class _CompatModule(types.ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        source = _EXPORT_SOURCES.get(name)
        if source is not None:
            setattr(source, name, value)


_module = sys.modules[__name__]
if not isinstance(_module, _CompatModule):  # pragma: no branch
    _module.__class__ = _CompatModule

__all__ = [
    "_current_head_finish_blocker",
    "_fresh_review_request_blocker",
    "_head_changed_review_gate_blocker",
    "_maybe_request_fresh_review",
    "_needs_pre_review_fresh_review_request",
    "_outdated_unresolved_review_thread_ids",
    "_parse_review_gate_result",
    "_prepare_current_head_review_window",
    "_resolve_review_threads",
    "_review_gate_lines",
    "_review_thread_lines",
    "_review_threads",
    "_run_review_gate",
    "_unresolved_review_thread_lines",
]
