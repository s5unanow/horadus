import sys

from src.horadus_cli.v1 import task_query as _module

globals().update(_module.__dict__)

sys.modules[__name__] = _module
