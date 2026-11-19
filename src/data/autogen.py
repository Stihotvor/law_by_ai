"""Shared Alembic autogenerate comparison options.

``migrations/env.py`` and the drift test both use this dict, so autogenerate
and the test apply the same rule. ``compare_server_default`` makes Alembic
report changed server defaults (it ignores them by default).
"""

from typing import Any, Final

AUTOGEN_COMPARE_OPTS: Final[dict[str, Any]] = {"compare_server_default": True}
