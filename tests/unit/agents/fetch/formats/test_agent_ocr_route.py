from io import BytesIO
from unittest.mock import MagicMock

import docx
import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import agents.fetch.document_fetcher as df
from agents.fetch.document_fetcher import PARSE_ERRORS, DocumentFetcherAgent
from agents.fetch.formats import image as image_mod
from agents.fetch.formats._safety import (
    CorruptDocumentError,
    EncryptedDocumentError,
    NoTextLayerError,
)
from agents.fetch.formats.base import FormatError, UnsupportedFormatError
from agents.fetch.ocr.errors import OcrDisabledError, OcrError
from agents.fetch.ocr.manager import OcrManager

PNG = b"\x89PNG\r\n\x1a\n" + b"junk"


class Fake:
    name = "fake"
    destination = "ocr.example"

    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes]] = []

    def ocr_pdf(self, data: bytes) -> str:
        self.calls.append(("pdf", data))
        return "scan text"

    def ocr_image(self, data: bytes, media_type: str) -> str:
        self.calls.append(("image", data))
        return "image text"


def _blank_pdf() -> bytes:
    w = PdfWriter()
    w.add_blank_page(72, 72)
    buf = BytesIO()
    w.write(buf)
    return buf.getvalue()


def _text_pdf() -> bytes:
    w = PdfWriter()
    page = w.add_blank_page(200, 200)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): w._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 100 Td (Hello text layer) Tj ET")
    page[NameObject("/Contents")] = w._add_object(stream)
    buf = BytesIO()
    w.write(buf)
    return buf.getvalue()


def _use(monkeypatch: pytest.MonkeyPatch, manager: OcrManager) -> MagicMock:
    getter = MagicMock(return_value=manager)
    monkeypatch.setattr(df, "get_ocr_manager", getter)
    return getter


def test_scanned_pdf_ocr_on(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = Fake()
    _use(monkeypatch, OcrManager(fake))
    pdf = _blank_pdf()
    assert DocumentFetcherAgent().parse(pdf, "a.pdf", "application/pdf") == "scan text"
    assert fake.calls == [("pdf", pdf)]


def test_scanned_pdf_ocr_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, OcrManager(None))
    with pytest.raises(OcrDisabledError) as exc:
        DocumentFetcherAgent().parse(_blank_pdf(), "a.pdf")
    assert isinstance(exc.value.__context__, NoTextLayerError)


def test_text_pdf_not_routed(monkeypatch: pytest.MonkeyPatch) -> None:
    getter = _use(monkeypatch, OcrManager(Fake()))
    assert "Hello text layer" in DocumentFetcherAgent().parse(_text_pdf(), "a.pdf")
    getter.assert_not_called()


def test_empty_docx_not_routed(monkeypatch: pytest.MonkeyPatch) -> None:
    getter = _use(monkeypatch, OcrManager(Fake()))
    buf = BytesIO()
    docx.Document().save(buf)
    with pytest.raises(NoTextLayerError):
        DocumentFetcherAgent().parse(buf.getvalue(), "a.docx")
    getter.assert_not_called()


def test_corrupt_and_encrypted_not_routed(monkeypatch: pytest.MonkeyPatch) -> None:
    getter = _use(monkeypatch, OcrManager(Fake()))
    with pytest.raises(CorruptDocumentError):
        DocumentFetcherAgent().parse(b"not a pdf", "a.pdf")
    w = PdfWriter()
    w.add_blank_page(72, 72)
    w.encrypt("pw")
    buf = BytesIO()
    w.write(buf)
    with pytest.raises(EncryptedDocumentError):
        DocumentFetcherAgent().parse(buf.getvalue(), "a.pdf")
    getter.assert_not_called()


def test_image_through_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = Fake()
    monkeypatch.setattr(image_mod, "get_ocr_manager", MagicMock(return_value=OcrManager(fake)))
    assert DocumentFetcherAgent().parse(PNG, "a.png", "image/png") == "image text"
    monkeypatch.setattr(image_mod, "get_ocr_manager", MagicMock(return_value=OcrManager(None)))
    with pytest.raises(OcrDisabledError):
        DocumentFetcherAgent().parse(PNG, "a.png", "image/png")


def test_parse_errors_and_unsupported() -> None:
    assert (FormatError, OcrError) == PARSE_ERRORS
    with pytest.raises(UnsupportedFormatError):
        DocumentFetcherAgent().parse(b"x", "a.xyz", "application/x-unknown")
