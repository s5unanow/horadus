import sys

from tools.horadus.python.horadus_cli import task_ledgers as _module

_legacy_name = __name__
globals().update(_module.__dict__)

sys.modules[_legacy_name] = _module
