import ast
from pathlib import Path

STRATEGIES_DIR = Path(__file__).resolve().parents[5] / "src" / "agents" / "fetch" / "strategies"
FORBIDDEN = ("agents.fetch.sources", "agents.fetch.document_fetcher", "agents.fetch.formats")


def _imports(path: Path) -> list[str]:
    out: list[str] = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            out.append(mod)
            out += [f"{mod}.{a.name}" for a in node.names]
    return out


def test_strategies_do_not_import_upward() -> None:
    files = list(STRATEGIES_DIR.glob("*.py"))
    assert {f.stem for f in files} >= {"rest_api", "minio"}
    for path in files:
        for mod in _imports(path):
            assert not mod.startswith(FORBIDDEN), (path, mod)
