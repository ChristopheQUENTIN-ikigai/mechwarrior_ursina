"""
Importing this package eagerly imports all built-in map modules so
their @registry.map decorators run.
"""
from . import megacity   # noqa: F401
from . import arena_flat # noqa: F401
from . import canyon     # noqa: F401
