"""Format parser contract, registry and dispatch."""

import re
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import ClassVar, Protocol, runtime_checkable

from agents.fetch.errors import FetchError
from agents.fetch.registry import Registry

MAX_TEXT_CHARS = 5_000_000
_CHARSET_RE = re.compile(r'charset\s*=\s*"?([A-Za-z0-9._:-]+)"?', re.I)


class FormatError(FetchError):
    """Base class for format errors."""


class UnsupportedFormatError(FormatError):
    """No parser matches the file name or MIME type."""


class TextLimitError(FormatError):
    """Extracted text exceeds MAX_TEXT_CHARS."""


@runtime_checkable
class FormatParser(Protocol):
    suffixes: ClassVar[tuple[str, ...]]
    mime_types: ClassVar[tuple[str, ...]]

    def parse(self, data: bytes, *, charset: str | None = None) -> str: ...


def _valid_suffix(value: object) -> bool:
    return isinstance(value, str) and len(value) > 1 and value.startswith(".") and value.islower()


def _valid_mime(value: object) -> bool:
    return (
        isinstance(value, str)
        and "/" in value
        and ";" not in value
        and " " not in value
        and value == value.lower()
    )


def _all_valid(values: object, check: Callable[[object], bool]) -> bool:
    return isinstance(values, tuple) and len(values) > 0 and all(check(v) for v in values)


def _validate_parser(name: str, cls: type[FormatParser]) -> None:
    if not isinstance(cls, type):
        raise TypeError(f"format {name!r}: not a class")
    if not _all_valid(getattr(cls, "suffixes", None), _valid_suffix):
        raise TypeError(f"format {name!r}: invalid suffixes")
    if not _all_valid(getattr(cls, "mime_types", None), _valid_mime):
        raise TypeError(f"format {name!r}: invalid mime_types")
    if not callable(getattr(cls, "parse", None)):
        raise TypeError(f"format {name!r}: parse is not callable")


FORMATS: Registry[type[FormatParser]] = Registry("formats", _validate_parser)


def charset_of(mime: str | None) -> str | None:
    if mime is None or ";" not in mime:
        return None
    match = _CHARSET_RE.search(mime.split(";", 1)[1])
    return match.group(1).lower() if match else None


def _by_suffix(suffix: str) -> FormatParser | None:
    for name in FORMATS.names():
        cls = FORMATS.get(name)
        if suffix in cls.suffixes:
            return cls()
    return None


def _by_mime(essence: str) -> FormatParser | None:
    for name in FORMATS.names():
        cls = FORMATS.get(name)
        if essence in cls.mime_types:
            return cls()
    return None


def find_parser(name: str, mime: str | None = None) -> FormatParser:
    clean = re.split(r"[?#]", name, maxsplit=1)[0]
    found = _by_suffix(PurePosixPath(clean).suffix.lower())
    if found is None and mime is not None:
        found = _by_mime(mime.split(";")[0].strip().lower())
    if found is None:
        raise UnsupportedFormatError(f"unsupported format: name={name!r} mime={mime!r}")
    return found


def parse_bytes(data: bytes, name: str, mime: str | None = None) -> str:
    return find_parser(name, mime).parse(data, charset=charset_of(mime))
