"""DOCX parser (body paragraphs and tables, in document order)."""

import re
import zipfile
from collections.abc import Iterable, Iterator
from io import BytesIO
from typing import ClassVar

from docx import Document
from docx.document import Document as DocumentType
from docx.table import Table, _Row
from docx.text.paragraph import Paragraph

from agents.fetch.formats._safety import (
    MAX_COMPRESSION_RATIO,
    MAX_NESTING_DEPTH,
    MAX_TEXT_CHARS,
    MAX_UNCOMPRESSED_BYTES,
    MAX_ZIP_ENTRIES,
    RATIO_MIN_BYTES,
    CorruptDocumentError,
    DocumentLimitError,
    EncryptedDocumentError,
    NoTextLayerError,
)
from agents.fetch.formats.base import FORMATS, FormatError

__all__ = [
    "CorruptDocumentError",
    "DocumentLimitError",
    "DocxParser",
    "EncryptedDocumentError",
    "NoTextLayerError",
]

_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_BODY_MEMBER = "word/document.xml"
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _check_infos(infos: list[zipfile.ZipInfo]) -> None:
    if len(infos) > MAX_ZIP_ENTRIES:
        raise DocumentLimitError("docx has too many entries")
    if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
        raise DocumentLimitError("docx is too large when unpacked")
    for info in infos:
        ratio = info.file_size / max(info.compress_size, 1)
        if info.file_size > RATIO_MIN_BYTES and ratio > MAX_COMPRESSION_RATIO:
            raise DocumentLimitError("docx compression ratio is too high")
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
    previous: object = None
    for cell in row.cells:
        if previous is not None and cell._tc is previous:  # pyright: ignore[reportPrivateUsage]
            continue
        previous = cell._tc  # pyright: ignore[reportPrivateUsage]
        parts = (line for line in _lines(cell.iter_inner_content(), depth + 1) if line)
        texts.append(" ".join(parts))
    return texts


def _lines(items: Iterable[Paragraph | Table], depth: int) -> Iterator[str]:
    if depth > MAX_NESTING_DEPTH:
        raise DocumentLimitError("docx tables are nested too deeply")
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
        line = _CONTROL_RE.sub("", line.replace("\xa0", " ")).strip()
        if not line:
            continue
        total += len(line)
        if total > MAX_TEXT_CHARS:
            raise DocumentLimitError("docx text is too large")
        lines.append(line)
    return lines


@FORMATS.register("docx")
class DocxParser:
    suffixes: ClassVar[tuple[str, ...]] = (".docx",)
    mime_types: ClassVar[tuple[str, ...]] = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    def parse(self, data: bytes, *, charset: str | None = None) -> str:
        _check_zip(data)
        try:
            lines = _collect(Document(BytesIO(data)))
        except FormatError:
            raise
        except Exception as exc:
            raise CorruptDocumentError("docx is corrupt") from exc
        if not lines:
            raise NoTextLayerError("docx has no text")
        return "\n".join(lines)
