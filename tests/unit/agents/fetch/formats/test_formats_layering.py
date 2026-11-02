import ast
from pathlib import Path

_FORBIDDEN = (
    "agents.fetch.document_fetcher",
    "agents.fetch.sources",
    "agents.fetch.strategies",
    "core.plugins",
    "plugins",
    "httpx",
    "minio",
    "socket",
    "urllib",
)


def _imports(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def test_formats_do_not_import_forbidden_modules() -> None:
    root = Path(__file__).resolve().parents[5] / "src" / "agents" / "fetch" / "formats"
    files = list(root.glob("*.py"))
    assert files
    for path in files:
        for name in _imports(path):
            for bad in _FORBIDDEN:
                assert name != bad and not name.startswith(bad + "."), f"{path.name}: {name}"
