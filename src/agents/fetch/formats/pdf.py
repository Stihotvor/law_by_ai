"""PDF parser (text layer only)."""

import re
from io import BytesIO
from typing import ClassVar

from pypdf import PasswordType, PdfReader

from agents.fetch.formats import base
from agents.fetch.formats._safety import (
    MAX_PDF_PAGES,
    CorruptDocumentError,
    EncryptedDocumentError,
    NoTextLayerError,
)
from agents.fetch.formats.base import FORMATS, FormatError, TextLimitError

__all__ = [
    "CorruptDocumentError",
    "EncryptedDocumentError",
    "NoTextLayerError",
    "PdfParser",
]

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_RE.sub("", text)
    return "\n".join(line.rstrip(" ") for line in text.split("\n")).strip()


def _open(data: bytes) -> PdfReader:
    reader = PdfReader(BytesIO(data), strict=False)
    if reader.is_encrypted:
        _decrypt(reader)
    return reader


def _decrypt(reader: PdfReader) -> None:
    try:
        result = reader.decrypt("")
    except Exception as exc:
        raise EncryptedDocumentError("pdf is encrypted") from exc
    if result == PasswordType.NOT_DECRYPTED:
        raise EncryptedDocumentError("pdf is encrypted")


def _page_texts(reader: PdfReader) -> list[str]:
    if len(reader.pages) > MAX_PDF_PAGES:
        raise TextLimitError("pdf has too many pages")
    total = 0
    texts: list[str] = []
    for page in reader.pages:
        raw = page.extract_text()
        total += len(raw)
        if total > base.MAX_TEXT_CHARS:
            raise TextLimitError("pdf text is too large")
        texts.append(raw)
    return texts


@FORMATS.register("pdf")
class PdfParser:
    suffixes: ClassVar[tuple[str, ...]] = (".pdf",)
    mime_types: ClassVar[tuple[str, ...]] = ("application/pdf",)

    def parse(self, data: bytes, *, charset: str | None = None) -> str:
        try:
            reader = _open(data)
            texts = _page_texts(reader)
        except FormatError:
            raise
        except Exception as exc:
            raise CorruptDocumentError("pdf is corrupt") from exc
        pages = [page for page in (_clean(t) for t in texts) if page]
        if not pages:
            raise NoTextLayerError("pdf has no text layer: OCR needed")
        return "\n\n".join(pages)
