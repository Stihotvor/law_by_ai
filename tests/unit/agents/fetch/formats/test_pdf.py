import builtins
import socket
import time
import zlib
from io import BytesIO
from typing import Any, cast

import pypdf
import pytest
from pypdf import PasswordType, PdfWriter
from pypdf.errors import DependencyError
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

from agents.fetch.formats import base as base_module
from agents.fetch.formats import pdf as pdf_module
from agents.fetch.formats.base import FormatError, TextLimitError, find_parser, parse_bytes
from agents.fetch.formats.pdf import (
    CorruptDocumentError,
    EncryptedDocumentError,
    NoTextLayerError,
    PdfParser,
)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf(texts: list[str], **encrypt_kw: Any) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    font_ref = cast(Any, writer)._add_object(font)
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
        )
        stream = DecodedStreamObject()
        if text:
            stream.set_data(f"BT /F1 12 Tf 72 700 Td ({_escape(text)}) Tj ET".encode())
        page[NameObject("/Contents")] = cast(Any, writer)._add_object(stream)
    if encrypt_kw:
        writer.encrypt(**encrypt_kw)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def test_pages() -> None:
    assert PdfParser().parse(_pdf(["one page"])) == "one page"
    assert PdfParser().parse(_pdf(["first", "second"])) == "first\n\nsecond"


def test_registry() -> None:
    assert isinstance(find_parser("a.pdf"), PdfParser)
    assert isinstance(find_parser("blob", "application/pdf; x=1"), PdfParser)
    assert parse_bytes(_pdf(["hi"]), "a.pdf", "application/pdf") == "hi"


def test_mixed_pages() -> None:
    assert PdfParser().parse(_pdf(["a", "", "b"])) == "a\n\nb"


def test_no_text_layer() -> None:
    with pytest.raises(NoTextLayerError) as info:
        PdfParser().parse(_pdf(["", ""]))
    assert isinstance(info.value, FormatError)
    assert str(info.value) == "pdf has no text layer: OCR needed"


def test_special_characters_escaped() -> None:
    assert PdfParser().parse(_pdf(["a (b) \\ c"])) == "a (b) \\ c"


@pytest.mark.parametrize("data", [b"", b"not a pdf"])
def test_corrupt(data: bytes) -> None:
    with pytest.raises(CorruptDocumentError):
        PdfParser().parse(data)


def test_truncated() -> None:
    data = _pdf(["hello"])
    with pytest.raises(FormatError) as info:
        PdfParser().parse(data[: len(data) // 2])
    assert type(info.value) in (CorruptDocumentError, NoTextLayerError)


def test_encrypted_user_password() -> None:
    data = _pdf(["secret"], user_password="pw", algorithm="RC4-128")
    with pytest.raises(EncryptedDocumentError) as info:
        PdfParser().parse(data)
    assert str(info.value) == "pdf is encrypted"


def test_encrypted_empty_user_password() -> None:
    data = _pdf(["open text"], user_password="", owner_password="own", algorithm="RC4-128")
    assert PdfParser().parse(data) == "open text"


def test_decrypt_exception_is_encrypted_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(self: object, password: str) -> None:
        raise RuntimeError("secret content")

    monkeypatch.setattr(pypdf.PdfReader, "decrypt", boom)
    data = _pdf(["x"], user_password="pw", algorithm="RC4-128")
    with pytest.raises(EncryptedDocumentError) as info:
        PdfParser().parse(data)
    assert isinstance(info.value.__cause__, RuntimeError)
    assert "secret content" not in str(info.value)
    assert str(info.value) == "pdf is encrypted"


def test_missing_crypto_dependency_has_accurate_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(self: object, password: str) -> None:
        raise DependencyError("cryptography missing")

    monkeypatch.setattr(pypdf.PdfReader, "decrypt", boom)
    data = _pdf(["x"], user_password="pw", algorithm="RC4-128")
    with pytest.raises(EncryptedDocumentError) as info:
        PdfParser().parse(data)
    assert isinstance(info.value.__cause__, DependencyError)
    assert str(info.value) == "pdf is encrypted and decryption support is missing"


def test_page_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_module, "MAX_PDF_PAGES", 2)
    with pytest.raises(TextLimitError) as info:
        PdfParser().parse(_pdf(["a", "b", "c"]))
    assert str(info.value) == "pdf has too many pages"
    assert PdfParser().parse(_pdf(["a", "b"])) == "a\n\nb"


def test_page_limit_checked_before_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(self: object, *args: object, **kwargs: object) -> str:
        raise AssertionError("extracted")

    data = _pdf(["a", "b", "c"])
    monkeypatch.setattr(pdf_module, "MAX_PDF_PAGES", 2)
    monkeypatch.setattr(pypdf.PageObject, "extract_text", fail)
    with pytest.raises(TextLimitError):
        PdfParser().parse(data)


def test_text_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_module, "MAX_TEXT_CHARS", 10)
    with pytest.raises(TextLimitError) as info:
        PdfParser().parse(_pdf(["x" * 20]))
    assert str(info.value) == "pdf text is too large"
    assert PdfParser().parse(_pdf(["x" * 10])) == "x" * 10


def test_text_limit_is_cumulative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_module, "MAX_TEXT_CHARS", 10)
    with pytest.raises(TextLimitError):
        PdfParser().parse(_pdf(["x" * 6, "y" * 6]))


def test_flate_bomb() -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    stream = DecodedStreamObject()
    stream.set_data(b"")
    cast(Any, stream)._data = zlib.compress(bytes(100 * 1024 * 1024))
    stream[NameObject("/Filter")] = NameObject("/FlateDecode")
    page[NameObject("/Contents")] = cast(Any, writer)._add_object(stream)
    out = BytesIO()
    writer.write(out)
    with pytest.raises(FormatError):
        PdfParser().parse(out.getvalue())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a\x00b\x07c\x7f", "ab c\x7f"),
        ("a\r\nb\rc", "a\nb\nc"),
        ("a  \nb \t\n", "a\nb"),
        ("  x  ", "x"),
        ("a\tb\x0bc\x1fd", "a\tb c d"),
    ],
)
def test_clean(raw: str, expected: str) -> None:
    assert cast(Any, pdf_module)._clean(raw) == expected


def test_control_characters_removed_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pypdf.PageObject, "extract_text", lambda self, *a, **k: "a\x00b")
    assert PdfParser().parse(_pdf(["x"])) == "ab"


def test_pypdf_exception_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(self: object, *args: object, **kwargs: object) -> str:
        raise RuntimeError("secret content")

    monkeypatch.setattr(pypdf.PageObject, "extract_text", boom)
    with pytest.raises(CorruptDocumentError) as info:
        PdfParser().parse(_pdf(["x"]))
    assert isinstance(info.value.__cause__, RuntimeError)
    assert "secret content" not in str(info.value)
    assert str(info.value) == "pdf is corrupt"


def test_no_sockets_or_files(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _pdf(["hi"])

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("io not allowed")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    assert PdfParser().parse(data) == "hi"


def test_not_decrypted_result_is_encrypted_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pypdf.PdfReader, "decrypt", lambda self, password: PasswordType.NOT_DECRYPTED
    )
    data = _pdf(["x"], user_password="pw", algorithm="RC4-128")
    with pytest.raises(EncryptedDocumentError) as info:
        PdfParser().parse(data)
    assert str(info.value) == "pdf is encrypted"


def test_damaged_but_recoverable_pdf_is_read_leniently() -> None:
    assert PdfParser().parse(b"junk\n" + _pdf(["hello"])) == "hello"


def test_clean_long_space_run_is_linear() -> None:
    start = time.monotonic()
    assert cast(Any, pdf_module)._clean(" " * 300_000 + "x") == "x"
    assert time.monotonic() - start < 2


def test_clean_strips_trailing_spaces_only() -> None:
    cleaned = cast(Any, pdf_module)._clean("a  \nb\t \nc \t\n d   ")
    assert cleaned == "a\nb\t\nc \t\n d"


def test_nul_and_controls_become_clean_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pypdf.PageObject, "extract_text", lambda self, *a, **k: "a\x00b\x01c\x1fd")
    assert PdfParser().parse(_pdf(["x"])) == "ab c d"


def test_clean_strips_only_trailing_spaces() -> None:
    assert pdf_module._clean("aX  \nbX \n x") == "aX\nbX\n x"
