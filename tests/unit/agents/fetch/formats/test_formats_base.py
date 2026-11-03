from pathlib import Path
from typing import Any, cast

import pytest

import agents.fetch.formats
from agents.fetch.formats.base import (
    FORMATS,
    UnsupportedFormatError,
    _validate_parser,
    charset_of,
    find_parser,
    parse_bytes,
)
from agents.fetch.formats.text import HtmlParser, PlainTextParser
from agents.fetch.registry import DuplicateNameError, Registry

_FORMATS_DIR = Path(agents.fetch.formats.__file__).parent


def test_autoload_registers_text_and_html() -> None:
    assert {"html", "text"} <= set(FORMATS.names())


def test_every_module_stem_registered() -> None:
    stems = {
        p.stem for p in _FORMATS_DIR.glob("*.py") if p.stem != "base" and not p.stem.startswith("_")
    }
    assert stems <= set(FORMATS.names())


def test_no_suffix_or_mime_claimed_twice() -> None:
    suffixes: list[str] = []
    mimes: list[str] = []
    for name in FORMATS.names():
        cls = FORMATS.get(name)
        suffixes += cls.suffixes
        mimes += cls.mime_types
    assert len(suffixes) == len(set(suffixes))
    assert len(mimes) == len(set(mimes))


@pytest.mark.parametrize(
    ("name", "mime", "expected"),
    [
        ("a.txt", None, PlainTextParser),
        ("A.TXT", None, PlainTextParser),
        ("a.html", None, HtmlParser),
        ("a.HTM", None, HtmlParser),
        ("blob", "text/html; charset=utf-8", HtmlParser),
        ("a.txt", "text/html", PlainTextParser),
        ("Act 12.03.2020", "text/plain", PlainTextParser),
        ("a.html?x=1#f", None, HtmlParser),
        ("a.txt#f.html", None, PlainTextParser),
        ("blob", "TEXT/HTML ; charset=x", HtmlParser),
    ],
)
def test_find_parser_dispatch(name: str, mime: str | None, expected: type) -> None:
    assert type(find_parser(name, mime)) is expected


@pytest.mark.parametrize(("name", "mime"), [("a.xyz", "application/x-unknown"), ("blob", None)])
def test_find_parser_unsupported(name: str, mime: str | None) -> None:
    with pytest.raises(UnsupportedFormatError) as exc:
        find_parser(name, mime)
    assert str(exc.value) == f"unsupported format: name={name!r} mime={mime!r}"


@pytest.mark.parametrize(
    ("mime", "expected"),
    [
        ("text/html; charset=UTF-8", "utf-8"),
        ('text/html; charset="windows-1250"', "windows-1250"),
        ("text/html; x=1; charset = latin1", "latin1"),
        ("text/html", None),
        (None, None),
        ("text/html; charset=", None),
        ("text/html;charset=utf-8", "utf-8"),
        ("text/html; charset=a; x=1", "a"),
        ("charset=utf-8", None),
    ],
)
def test_charset_of(mime: str | None, expected: str | None) -> None:
    assert charset_of(mime) == expected


class _Good:
    suffixes = (".ok",)
    mime_types = ("a/b",)

    def parse(self, data: bytes, *, charset: str | None = None) -> str:
        return ""


def _derive(**attrs: object) -> type:
    return type(
        "Bad", (), {"parse": _Good.parse, "suffixes": (".ok",), "mime_types": ("a/b",), **attrs}
    )


def _no_suffixes() -> type:
    return type("Bad", (), {"parse": _Good.parse, "mime_types": ("a/b",)})


def _no_mime() -> type:
    return type("Bad", (), {"parse": _Good.parse, "suffixes": (".ok",)})


def _no_parse() -> type:
    return type("Bad", (), {"suffixes": (".ok",), "mime_types": ("a/b",)})


@pytest.mark.parametrize(
    "cls",
    [
        _no_suffixes(),
        _no_mime(),
        _derive(mime_types=("a/b;c",)),
        _derive(suffixes=("txt",)),
        _derive(suffixes=(".TXT",)),
        _derive(suffixes=(".",)),
        _derive(suffixes=()),
        _derive(suffixes=[".ok"]),
        _derive(suffixes=(1,)),
        _derive(mime_types=()),
        _derive(mime_types=("text",)),
        _derive(mime_types=("text/plain; x=1",)),
        _derive(mime_types=("text/a b",)),
        _derive(mime_types=("Text/Plain",)),
        _derive(mime_types=["a/b"]),
        _derive(mime_types=(1,)),
        _derive(parse=None),
        _no_parse(),
        "not a class",
    ],
)
def test_validate_rejects(cls: object) -> None:
    with pytest.raises(TypeError, match=r"^format 'x': "):
        _validate_parser("x", cast(Any, cls))


def test_register_and_duplicate() -> None:
    reg: Registry[type] = Registry("formats", _validate_parser)
    reg.register("good")(_Good)
    assert reg.get("good") is _Good
    with pytest.raises(DuplicateNameError):
        reg.register("good")


def test_parse_bytes() -> None:
    assert parse_bytes(b"hi", "a.txt", "text/plain; charset=utf-8") == "hi"
    with pytest.raises(UnsupportedFormatError):
        parse_bytes(b"x", "a.xyz")


def test_validate_accepts_short_suffix() -> None:
    _validate_parser("x", cast(Any, _derive(suffixes=(".a",))))


def test_parse_bytes_passes_charset_and_mime() -> None:
    data = "\u0105".encode("iso-8859-2")
    assert parse_bytes(data, "a.txt", "text/plain; charset=iso-8859-2") == "\u0105"
    assert parse_bytes(b"<p>x</p>", "blob", "text/html") == "x"


def test_unsupported_message_truncates_name_and_mime() -> None:
    with pytest.raises(UnsupportedFormatError) as exc:
        find_parser("n" * 500, "m/" + "x" * 500)
    assert (
        str(exc.value) == f"unsupported format: name={'n' * 64!r} mime={('m/' + 'x' * 500)[:64]!r}"
    )
