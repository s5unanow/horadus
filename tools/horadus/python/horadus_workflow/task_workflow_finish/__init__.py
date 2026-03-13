from __future__ import annotations

import sys
import types

from . import checks as checks_module
from . import context as context_module
from . import orchestrator as orchestrator_module
from . import preconditions as preconditions_module
from . import review as review_module

_MODULE_EXPORTS: dict[object, list[str]] = {
    context_module: list(context_module.__all__),
    checks_module: list(checks_module.__all__),
    preconditions_module: list(preconditions_module.__all__),
    review_module: list(review_module.__all__),
    orchestrator_module: list(orchestrator_module.__all__),
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
        if source is not None:
            setattr(source, name, value)


_module = sys.modules[__name__]
if not isinstance(_module, _CompatModule):  # pragma: no branch
    _module.__class__ = _CompatModule

__all__ = sorted(_EXPORT_SOURCES)
