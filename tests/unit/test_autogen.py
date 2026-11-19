"""Tests for the shared Alembic autogenerate options in ``data.autogen``."""

import ast
from pathlib import Path

from data import autogen


def test_opts_only_enable_compare_server_default() -> None:
    assert autogen.AUTOGEN_COMPARE_OPTS == {"compare_server_default": True}


def test_module_does_not_import_alembic() -> None:
    tree = ast.parse(Path(autogen.__file__).read_text())
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not [m for m in imported if m.split(".")[0] == "alembic"]
