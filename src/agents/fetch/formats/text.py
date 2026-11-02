"""Plain text and HTML parsers."""

import codecs
import re
from html.parser import HTMLParser
from typing import ClassVar

from agents.fetch.formats.base import FORMATS

_META_RE = re.compile(rb'charset\s*=\s*["\']?([A-Za-z0-9._:-]+)', re.I)
_SNIFF_BYTES = 2048
_BLOCK_TAGS = frozenset(
    {
        *("p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article"),
        *("header", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "hr"),
    }
)
_SKIP_TAGS = frozenset({"script", "style"})
_HSPACE_RE = re.compile(r"[^\S\n]+")


def _try_decode(data: bytes, charset: str | None) -> str | None:
    if charset is None:
        return None
    try:
        codecs.lookup(charset)
        return data.decode(charset)
    except (LookupError, UnicodeDecodeError):
        return None


def _bom_charset(data: bytes) -> str | None:
    if data.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16"
    return None


def _meta_charset(data: bytes) -> str | None:
    match = _META_RE.search(data[:_SNIFF_BYTES])
    return match.group(1).decode("ascii") if match else None


def _decode(data: bytes, charset: str | None, sniff_meta: bool) -> str:
    candidates = [_bom_charset(data), charset]
    if sniff_meta:
        candidates.append(_meta_charset(data))
    candidates.append("utf-8")
    for candidate in candidates:
        text = _try_decode(data, candidate)
        if text is not None:
            return text
    return data.decode("cp1250", errors="replace")


@FORMATS.register("text")
class PlainTextParser:
    suffixes: ClassVar[tuple[str, ...]] = (".txt",)
    mime_types: ClassVar[tuple[str, ...]] = ("text/plain",)

    def parse(self, data: bytes, *, charset: str | None = None) -> str:
        text = _decode(data, charset, sniff_meta=False)
        return text.replace("\r\n", "\n").replace("\r", "\n")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pieces: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self.pieces.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _BLOCK_TAGS:
            self.pieces.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.pieces.append(data)


def _normalise(text: str) -> str:
    lines = (_HSPACE_RE.sub(" ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


@FORMATS.register("html")
class HtmlParser:
    suffixes: ClassVar[tuple[str, ...]] = (".html", ".htm")
    mime_types: ClassVar[tuple[str, ...]] = ("text/html", "application/xhtml+xml")

    def parse(self, data: bytes, *, charset: str | None = None) -> str:
        extractor = _TextExtractor()
        extractor.feed(_decode(data, charset, sniff_meta=True))
        extractor.close()
        return _normalise("".join(extractor.pieces).replace("\r", "\n"))
