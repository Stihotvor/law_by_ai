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


def _collect(source: str) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
            names += [node.module + "." + a.name for a in node.names]
    return names


def _imports(path: Path) -> list[str]:
    return _collect(path.read_text())


def test_collector_catches_aliased_from_import() -> None:
    names = _collect("from agents.fetch import sources\n")
    assert "agents.fetch.sources" in names


def test_formats_do_not_import_forbidden_modules() -> None:
    root = Path(__file__).resolve().parents[5] / "src" / "agents" / "fetch" / "formats"
    files = list(root.glob("*.py"))
    assert files
    for path in files:
        for name in _imports(path):
            for bad in _FORBIDDEN:
                assert name != bad and not name.startswith(bad + "."), f"{path.name}: {name}"


def test_format_errors_derive_from_fetch_error() -> None:
    from agents.fetch.errors import FetchError
    from agents.fetch.formats import base

    assert issubclass(base.FormatError, FetchError)
    for cls in (base.UnsupportedFormatError, base.TextLimitError):
        assert issubclass(cls, base.FormatError)


def test_formats_may_import_errors_module() -> None:
    root = Path(__file__).resolve().parents[5] / "src" / "agents" / "fetch" / "formats"
    assert "agents.fetch.errors" in _imports(root / "base.py")
