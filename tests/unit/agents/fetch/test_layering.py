import ast
from pathlib import Path

FETCH = Path(__file__).resolve().parents[4] / "src" / "agents" / "fetch"


def _imports(path: Path) -> list[str]:
    out: list[str] = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            out.append(mod)
            out += [f"{mod}.{a.name}" if mod else a.name for a in node.names]
    return out


def test_no_plugin_imports_and_no_upward_imports() -> None:
    files = list(FETCH.rglob("*.py"))
    assert files
    for path in files:
        in_sub = path.parent.name in {"sources", "strategies"}
        for mod in _imports(path):
            assert mod != "plugins" and not mod.startswith(("plugins.", "core.plugins")), path
            if in_sub:
                assert mod != "agents.fetch.document_fetcher", path
