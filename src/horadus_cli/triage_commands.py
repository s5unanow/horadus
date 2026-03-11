import sys

from src.horadus_cli.v1 import triage_commands as _module

globals().update(_module.__dict__)

sys.modules[__name__] = _module
