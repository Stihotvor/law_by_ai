import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[5] / "src"
OCR_DIR = SRC / "agents" / "fetch" / "ocr"
IMAGE = SRC / "agents" / "fetch" / "formats" / "image.py"
OCR_FORBIDDEN = (
    "agents.fetch.formats",
    "agents.fetch.sources",
    "agents.fetch.strategies",
    "agents.fetch.document_fetcher",
    "core.plugins",
    "plugins",
)
IMAGE_FORBIDDEN = ("httpx", "socket", "urllib", "agents.fetch.ocr.mistral")


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


def _hits(mod: str, forbidden: tuple[str, ...]) -> bool:
    return any(mod == f or mod.startswith(f + ".") for f in forbidden)


def test_ocr_is_a_leaf_package() -> None:
    files = list(OCR_DIR.glob("*.py"))
    assert {f.stem for f in files} >= {"errors", "manager", "mistral"}
    for path in files:
        for mod in _imports(path):
            assert not _hits(mod, OCR_FORBIDDEN), (path, mod)


def test_image_parser_has_no_transport() -> None:
    mods = _imports(IMAGE)
    assert "agents.fetch.ocr.manager" in mods
    for mod in mods:
        assert not _hits(mod, IMAGE_FORBIDDEN), mod
