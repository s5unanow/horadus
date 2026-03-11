import sys

from src.horadus_cli.v2 import ops_commands as _module

_legacy_name = __name__
globals().update(_module.__dict__)

sys.modules[_legacy_name] = _module
