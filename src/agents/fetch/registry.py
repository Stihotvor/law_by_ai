"""Generic name registry with package autoload."""

import importlib
import pkgutil
import re
from collections.abc import Callable
from typing import cast

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class RegistryError(Exception):
    """Base class for registry errors."""


class DuplicateNameError(RegistryError):
    """Name is already registered."""


class UnknownNameError(RegistryError):
    """Name is not registered."""


class InvalidNameError(RegistryError):
    """Name does not match the allowed pattern."""


class AutoloadError(RegistryError):
    """A module did not register its stem name."""


class Registry[T]:
    """Maps names to registered objects."""

    def __init__(self, kind: str, validate: Callable[[str, T], None] | None = None) -> None:
        self._kind = kind
        self._validate = validate
        self._items: dict[str, T] = {}

    def register[C](self, name: str) -> Callable[[C], C]:
        if not _NAME_RE.match(name):
            raise InvalidNameError(f"{self._kind}: invalid name {name!r}")
        if name in self._items:
            raise DuplicateNameError(f"{self._kind}: duplicate name {name!r}")

        def decorator(obj: C) -> C:
            item = cast(T, obj)
            if self._validate is not None:
                self._validate(name, item)
            self._items[name] = item
            return obj

        return decorator

    def get(self, name: str) -> T:
        try:
            return self._items[name]
        except KeyError:
            raise UnknownNameError(f"{self._kind}: unknown name {name!r}") from None

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._items))

    def __contains__(self, name: object) -> bool:
        return name in self._items


def autoload[T](
    package: str, registry: Registry[T], *, skip: frozenset[str] = frozenset({"base"})
) -> None:
    """Import every module of a package and require it to register its stem."""
    pkg = importlib.import_module(package)
    stems = sorted(m.name for m in pkgutil.iter_modules(pkg.__path__))
    for stem in stems:
        if stem in skip or stem.startswith("_"):
            continue
        importlib.import_module(f"{package}.{stem}")
        if stem not in registry:
            raise AutoloadError(f"{package}.{stem} did not register {stem!r}")
