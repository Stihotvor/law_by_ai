import ast
import itertools
from pathlib import Path

import pytest

from agents.fetch import registry as registry_module
from agents.fetch.registry import (
    AutoloadError,
    DuplicateNameError,
    InvalidNameError,
    Registry,
    UnknownNameError,
    autoload,
)

_counter = itertools.count()


def _make_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, files: dict[str, str]) -> str:
    name = f"tpkg_{next(_counter)}"
    pkg = tmp_path / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    for fname, body in files.items():
        (pkg / fname).write_text(body)
    monkeypatch.syspath_prepend(str(tmp_path))
    return name


def test_register_and_get() -> None:
    reg: Registry[type] = Registry("k")

    class A: ...

    assert reg.register("a")(A) is A
    assert reg.get("a") is A


def test_duplicate() -> None:
    reg: Registry[int] = Registry("k")
    reg.register("a")(1)
    with pytest.raises(DuplicateNameError, match=r"k.*a"):
        reg.register("a")


def test_unknown() -> None:
    with pytest.raises(UnknownNameError):
        Registry[int]("k").get("x")


@pytest.mark.parametrize("bad", ["Bad", "1x", "a-b", ""])
def test_invalid_names(bad: str) -> None:
    with pytest.raises(InvalidNameError):
        Registry[int]("k").register(bad)


def test_names_sorted_and_contains() -> None:
    reg: Registry[int] = Registry("k")
    reg.register("b")(1)
    reg.register("a")(2)
    assert reg.names() == ("a", "b")
    assert "a" in reg
    assert "z" not in reg


def test_validate_failure_not_stored() -> None:
    def validate(name: str, obj: int) -> None:
        raise TypeError("nope")

    reg: Registry[int] = Registry("k", validate)
    with pytest.raises(TypeError):
        reg.register("a")(1)
    assert "a" not in reg


def test_autoload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = _make_package(
        tmp_path,
        monkeypatch,
        {
            "alpha.py": ("from tests_reg import REG\n@REG.register('alpha')\nclass Alpha: ...\n"),
            "base.py": "raise RuntimeError('base must be skipped')\n",
            "_private.py": "raise RuntimeError('private must be skipped')\n",
        },
    )
    reg: Registry[type] = Registry("k")
    import sys
    import types

    mod = types.ModuleType("tests_reg")
    attr = "REG"
    setattr(mod, attr, reg)
    monkeypatch.setitem(sys.modules, "tests_reg", mod)
    autoload(pkg, reg)
    assert reg.names() == ("alpha",)


def test_autoload_missing_registration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = _make_package(tmp_path, monkeypatch, {"lazy.py": "x = 1\n"})
    with pytest.raises(AutoloadError, match="lazy"):
        autoload(pkg, Registry[int]("k"))


def test_registry_has_no_project_imports() -> None:
    tree = ast.parse(Path(registry_module.__file__).read_text())
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        for n in names:
            assert n.split(".")[0] not in {"agents", "core", "plugins"}


def test_registry_error_messages() -> None:
    reg: Registry[int] = Registry("kind")
    with pytest.raises(InvalidNameError) as bad:
        reg.register("Bad")
    assert str(bad.value) == "kind: invalid name 'Bad'"
    with pytest.raises(UnknownNameError) as unknown:
        reg.get("nope")
    assert str(unknown.value) == "kind: unknown name 'nope'"


def test_no_validator_stores_any_object_unchecked() -> None:
    reg: Registry[int] = Registry("k")
    wrong: object = "not-an-int"
    reg.register("a")(wrong)
    assert reg.get("a") is wrong
