"""DOCX parser (body paragraphs and tables, in document order)."""

import zipfile
from collections.abc import Iterable, Iterator
from io import BytesIO
from typing import Any, ClassVar, cast

from docx import Document
from docx.document import Document as DocumentType
from docx.table import Table, _Cell, _Row
from docx.text.paragraph import Paragraph

from agents.fetch.formats import base
from agents.fetch.formats._safety import (
    MAX_COMPRESSION_RATIO,
    MAX_NESTING_DEPTH,
    MAX_UNCOMPRESSED_BYTES,
    MAX_ZIP_ENTRIES,
    RATIO_MIN_BYTES,
    CorruptDocumentError,
    EncryptedDocumentError,
    NoTextLayerError,
)
from agents.fetch.formats.base import FORMATS, FormatError, TextLimitError
from agents.fetch.formats.text import clean_text

__all__ = [
    "CorruptDocumentError",
    "DocxParser",
    "EncryptedDocumentError",
    "NoTextLayerError",
]

_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_BODY_MEMBER = "word/document.xml"


def _check_infos(infos: list[zipfile.ZipInfo]) -> None:
    if len(infos) > MAX_ZIP_ENTRIES:
        raise TextLimitError("docx has too many entries")
    if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
        raise TextLimitError("docx is too large when unpacked")
    for info in infos:
        ratio = info.file_size / max(info.compress_size, 1)
        if info.file_size > RATIO_MIN_BYTES and ratio > MAX_COMPRESSION_RATIO:
            raise TextLimitError("docx compression ratio is too high")
        if info.flag_bits & 0x1:
            raise EncryptedDocumentError("docx has an encrypted entry")
    if _BODY_MEMBER not in {i.filename for i in infos}:
        raise CorruptDocumentError("docx has no body")


def _check_zip(data: bytes) -> None:
    if data.startswith(_OLE_SIGNATURE):
        raise CorruptDocumentError("docx is not a zip (encrypted or legacy doc)")
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise CorruptDocumentError("docx is not a valid zip") from exc
    _check_infos(infos)


def _row_texts(row: _Row, depth: int) -> list[str]:
    texts: list[str] = []
    for tc in cast(Any, row)._tr.tc_lst:
        cell = _Cell(tc, row.table)
        parts = (line for line in _lines(cell.iter_inner_content(), depth + 1) if line)
        texts.append(" ".join(parts))
    return texts


def _lines(items: Iterable[Paragraph | Table], depth: int) -> Iterator[str]:
    if depth > MAX_NESTING_DEPTH:
        raise TextLimitError("docx tables are nested too deeply")
    for item in items:
        if isinstance(item, Paragraph):
            yield item.text
            continue
        for row in item.rows:
            texts = _row_texts(row, depth)
            if any(texts):
                yield " | ".join(texts)


def _collect(document: DocumentType) -> list[str]:
    lines: list[str] = []
    total = 0
    for line in _lines(document.iter_inner_content(), 0):
        line = line.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
        line = clean_text(line.replace("\x00", "")).strip()
        if not line:
            continue
        total += len(line)
        if total > base.MAX_TEXT_CHARS:
            raise TextLimitError("docx text is too large")
        lines.append(line)
    return lines


@FORMATS.register("docx")
class DocxParser:
    suffixes: ClassVar[tuple[str, ...]] = (".docx",)
    mime_types: ClassVar[tuple[str, ...]] = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    def parse(self, data: bytes, *, charset: str | None = None) -> str:
        try:
            _check_zip(data)
            lines = _collect(Document(BytesIO(data)))
        except FormatError:
            raise
        except Exception as exc:
            raise CorruptDocumentError("docx is corrupt") from exc
        if not lines:
            raise NoTextLayerError("docx has no text")
        return "\n".join(lines)
