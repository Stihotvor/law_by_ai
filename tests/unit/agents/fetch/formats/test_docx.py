import ast
import socket
import time
import zipfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from docx.document import Document as DocumentType
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

from agents.fetch.formats import docx as docx_module
from agents.fetch.formats.base import find_parser
from agents.fetch.formats.docx import (
    CorruptDocumentError,
    DocumentLimitError,
    DocxParser,
    EncryptedDocumentError,
    NoTextLayerError,
)

_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XML_DECL = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


def _docx(build: Callable[[DocumentType], None]) -> bytes:
    document = Document()
    build(document)
    out = BytesIO()
    document.save(out)
    return out.getvalue()


def _rewrite(
    data: bytes,
    replace: dict[str, bytes] | None = None,
    extra: dict[str, bytes] | None = None,
) -> bytes:
    replace = replace or {}
    out = BytesIO()
    with (
        zipfile.ZipFile(BytesIO(data)) as src,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for info in src.infolist():
            dst.writestr(info.filename, replace.get(info.filename, src.read(info.filename)))
        for name, content in (extra or {}).items():
            dst.writestr(name, content)
    return out.getvalue()


def _member(data: bytes, name: str) -> bytes:
    with zipfile.ZipFile(BytesIO(data)) as archive:
        return archive.read(name)


def _simple(*paragraphs: str) -> bytes:
    def build(doc: DocumentType) -> None:
        for text in paragraphs:
            doc.add_paragraph(text)

    return _docx(build)


def _parse(data: bytes) -> str:
    return DocxParser().parse(data)


def test_paragraphs_and_registry() -> None:
    assert _parse(_simple("first", "second", "third")) == "first\nsecond\nthird"
    assert isinstance(find_parser("a.docx"), DocxParser)
    assert isinstance(find_parser("blob", _MIME), DocxParser)


def test_table_order_merge_empty_row_nested() -> None:
    def build(doc: DocumentType) -> None:
        doc.add_paragraph("before")
        table = doc.add_table(rows=4, cols=3)
        table.cell(0, 0).text = "a"
        table.cell(0, 1).text = "b"
        table.cell(0, 2).text = "c"
        merged = table.cell(1, 0).merge(table.cell(1, 1))
        merged.text = "m"
        table.cell(1, 2).text = "z"
        # row 2 stays empty
        inner = table.cell(3, 0).add_table(rows=1, cols=2)
        inner.cell(0, 0).text = "n1"
        inner.cell(0, 1).text = "n2"
        doc.add_paragraph("after")

    out = _parse(_docx(build))
    assert out.split("\n") == ["before", "a | b | c", "m | z", "n1 | n2 |  |", "after"]


def test_headers_footers_skipped() -> None:
    def build(doc: DocumentType) -> None:
        doc.add_paragraph("body")
        section = doc.sections[0]
        section.header.paragraphs[0].text = "HEADER-MARK"
        section.footer.paragraphs[0].text = "FOOTER-MARK"

    assert _parse(_docx(build)) == "body"


def test_hyperlink_text_kept_url_absent() -> None:
    def build(doc: DocumentType) -> None:
        paragraph = doc.add_paragraph("see ")
        rel = doc.part.relate_to(
            "http://example.invalid/URL-MARK",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
            is_external=True,
        )
        link = parse_xml(
            f'<w:hyperlink {nsdecls("w", "r")} r:id="{rel}">'
            "<w:r><w:t>link text</w:t></w:r></w:hyperlink>"
        )
        paragraph._p.append(link)  # pyright: ignore[reportPrivateUsage]

    out = _parse(_docx(build))
    assert out == "see link text"
    assert "URL-MARK" not in out


def test_polish_round_trip() -> None:
    assert _parse(_simple("zażółć gęślą jaźń")) == "zażółć gęślą jaźń"


def test_whitespace_and_control_cleanup() -> None:
    assert _parse(_simple("  a\xa0b  ", "", "   ", "c")) == "a b\nc"


def test_empty_document() -> None:
    with pytest.raises(NoTextLayerError) as info:
        _parse(_docx(lambda doc: None))
    assert str(info.value) == "docx has no text"


def _png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _truncated() -> bytes:
    data = _simple("hello")
    return data[: len(data) // 2]


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"PK\x03\x04junk",
        _png(),
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64,
        _truncated(),
    ],
)
def test_corrupt(data: bytes) -> None:
    with pytest.raises(CorruptDocumentError):
        _parse(data)


def test_bad_zip_message() -> None:
    with pytest.raises(CorruptDocumentError) as info:
        _parse(b"")
    assert str(info.value) == "docx is not a valid zip"


def test_ole_message() -> None:
    with pytest.raises(CorruptDocumentError) as info:
        _parse(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    assert str(info.value) == "docx is not a zip (encrypted or legacy doc)"


def test_zip_without_body() -> None:
    out = BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("other.xml", "<a/>")
    with pytest.raises(CorruptDocumentError) as info:
        _parse(out.getvalue())
    assert str(info.value) == "docx has no body"


def test_body_not_xml_is_corrupt() -> None:
    data = _rewrite(_simple("x"), replace={"word/document.xml": b"<not closed"})
    with pytest.raises(CorruptDocumentError):
        _parse(data)


def test_zip_bomb_total(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docx_module, "MAX_UNCOMPRESSED_BYTES", 1024 * 1024)
    data = _rewrite(_simple("x"), extra={"big.bin": bytes(2 * 1024 * 1024)})
    with pytest.raises(DocumentLimitError) as info:
        _parse(data)
    assert str(info.value) == "docx is too large when unpacked"


def test_total_at_limit_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _simple("x")
    with zipfile.ZipFile(BytesIO(data)) as archive:
        total = sum(i.file_size for i in archive.infolist())
    monkeypatch.setattr(docx_module, "MAX_UNCOMPRESSED_BYTES", total)
    assert _parse(data) == "x"


def test_zip_bomb_ratio() -> None:
    data = _rewrite(_simple("x"), extra={"big.bin": bytes(2 * 1024 * 1024)})
    with pytest.raises(DocumentLimitError) as info:
        _parse(data)
    assert str(info.value) == "docx compression ratio is too high"


def test_ratio_small_entry_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docx_module, "RATIO_MIN_BYTES", 10 * 1024 * 1024)
    data = _rewrite(_simple("x"), extra={"big.bin": bytes(2 * 1024 * 1024)})
    assert _parse(data) == "x"


def test_ratio_at_limit_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docx_module, "MAX_COMPRESSION_RATIO", 10**9)
    data = _rewrite(_simple("x"), extra={"big.bin": bytes(2 * 1024 * 1024)})
    assert _parse(data) == "x"


def test_too_many_entries() -> None:
    extra = {f"f{i}.txt": b"x" for i in range(1001)}
    with pytest.raises(DocumentLimitError) as info:
        _parse(_rewrite(_simple("x"), extra=extra))
    assert str(info.value) == "docx has too many entries"


def test_entries_at_limit_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _simple("x")
    with zipfile.ZipFile(BytesIO(data)) as archive:
        count = len(archive.infolist())
    monkeypatch.setattr(docx_module, "MAX_ZIP_ENTRIES", count)
    assert _parse(data) == "x"


def test_encrypted_entry() -> None:
    data = bytearray(_simple("x"))
    central = data.index(b"PK\x01\x02")
    data[central + 8] |= 0x01  # general purpose flag, low byte
    with pytest.raises(EncryptedDocumentError) as info:
        _parse(bytes(data))
    assert str(info.value) == "docx has an encrypted entry"


def _nested_table_xml(depth: int) -> bytes:
    inner = "<w:p><w:r><w:t>deep</w:t></w:r></w:p>"
    for _ in range(depth):
        inner = f"<w:tbl><w:tr><w:tc>{inner}<w:p/></w:tc></w:tr></w:tbl>"
    return inner.encode()


def _with_body(data: bytes, body: bytes) -> bytes:
    xml = _member(data, "word/document.xml")
    start = xml.index(b"<w:body>") + len(b"<w:body>")
    end = xml.index(b"</w:body>")
    return _rewrite(data, replace={"word/document.xml": xml[:start] + body + xml[end:]})


def test_nesting_limit() -> None:
    base = _simple("x")
    with pytest.raises(DocumentLimitError) as info:
        _parse(_with_body(base, _nested_table_xml(9)))
    assert str(info.value) == "docx tables are nested too deeply"
    assert _parse(_with_body(base, _nested_table_xml(3))) == "deep"


def test_nesting_at_limit_passes() -> None:
    assert _parse(_with_body(_simple("x"), _nested_table_xml(8))) == "deep"


def test_text_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docx_module, "MAX_TEXT_CHARS", 10)
    with pytest.raises(DocumentLimitError) as info:
        _parse(_simple("x" * 20))
    assert str(info.value) == "docx text is too large"
    assert _parse(_simple("x" * 10)) == "x" * 10


def test_text_limit_is_cumulative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docx_module, "MAX_TEXT_CHARS", 10)
    with pytest.raises(DocumentLimitError):
        _parse(_simple("x" * 6, "y" * 6))


def _with_doctype(data: bytes, doctype: str, text_xml: str) -> bytes:
    xml = _member(data, "word/document.xml")
    decl_end = xml.index(b"?>") + 2
    body = f"<w:p><w:r><w:t>{text_xml}</w:t></w:r></w:p>".encode()
    start = xml.index(b"<w:body>") + len(b"<w:body>")
    new = xml[:decl_end] + doctype.encode() + xml[decl_end:start] + body + xml[start:]
    return _rewrite(data, replace={"word/document.xml": new})


def _assert_safe(data: bytes, marker: str) -> str | None:
    try:
        out = _parse(data)
    except CorruptDocumentError:
        return None
    assert marker not in out
    return out


def test_xxe_internal_entity() -> None:
    # Observed outcome: the entity is not expanded and the document parses.
    doctype = '<!DOCTYPE d [<!ENTITY a "EXPANDED-MARKER">]>'
    _assert_safe(_with_doctype(_simple("x"), doctype, "&a;"), "EXPANDED-MARKER")


def test_xxe_external_file(tmp_path: Path) -> None:
    # Observed outcome: the external entity is not resolved, SECRET-MARKER is absent.
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET-MARKER")
    doctype = f'<!DOCTYPE d [<!ENTITY x SYSTEM "file://{secret}">]>'
    _assert_safe(_with_doctype(_simple("x"), doctype, "&x;"), "SECRET-MARKER")


def test_entity_expansion() -> None:
    entities = ['<!ENTITY e0 "lol">']
    for level in range(1, 10):
        refs = f"&e{level - 1};" * 10
        entities.append(f'<!ENTITY e{level} "{refs}">')
    doctype = "<!DOCTYPE d [" + "".join(entities) + "]>"
    data = _with_doctype(_simple("x"), doctype, "&e9;")
    started = time.monotonic()
    out = _assert_safe(data, "lollollol")
    assert time.monotonic() - started < 5
    assert out is None or len(out) < 1000


def test_external_relationship_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _simple("kept")
    rels = _member(data, "word/_rels/document.xml.rels").decode()
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
    extra = (
        f'<Relationship Id="rIdH" Type="{rel}hyperlink" '
        'Target="http://127.0.0.1:9/x" TargetMode="External"/>'
        f'<Relationship Id="rIdT" Type="{rel}attachedTemplate" '
        'Target="http://127.0.0.1:9/t.dotm" TargetMode="External"/>'
    )
    new = rels.replace("</Relationships>", extra + "</Relationships>").encode()
    data = _rewrite(data, replace={"word/_rels/document.xml.rels": new})

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("socket not allowed")

    monkeypatch.setattr(socket, "socket", forbidden)
    assert _parse(data) == "kept"


def test_document_exception_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("secret content")

    data = _simple("x")
    monkeypatch.setattr(docx_module, "Document", boom)
    with pytest.raises(CorruptDocumentError) as info:
        _parse(data)
    assert isinstance(info.value.__cause__, RuntimeError)
    assert "secret content" not in str(info.value)
    assert str(info.value) == "docx is corrupt"


def test_layering() -> None:
    source = Path(docx_module.__file__).read_text()
    forbidden = {"lxml", "xml", "socket", "urllib", "httpx", "os"}
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            roots.add((node.module or "").split(".")[0])
    assert not roots & forbidden


def test_cell_with_several_paragraphs_joined_by_space() -> None:
    def build(doc: DocumentType) -> None:
        table = doc.add_table(rows=1, cols=2)
        cell = table.cell(0, 0)
        cell.text = "one"
        cell.add_paragraph("two")
        table.cell(0, 1).text = "three"

    assert _parse(_docx(build)) == "one two | three"


def test_delete_control_character() -> None:
    assert _parse(_simple("a\x7fb")) == "ab"


def test_ratio_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    size = 2 * 1024 * 1024
    data = _rewrite(_simple("x"), extra={"big.bin": bytes(size)})
    with zipfile.ZipFile(BytesIO(data)) as archive:
        info = archive.getinfo("big.bin")
        ratio = info.file_size / info.compress_size
    monkeypatch.setattr(docx_module, "RATIO_MIN_BYTES", size)
    assert _parse(data) == "x"  # size equal to the minimum is not checked
    monkeypatch.setattr(docx_module, "RATIO_MIN_BYTES", size - 1)
    monkeypatch.setattr(docx_module, "MAX_COMPRESSION_RATIO", ratio)
    assert _parse(data) == "x"  # ratio equal to the maximum is allowed
    monkeypatch.setattr(docx_module, "MAX_COMPRESSION_RATIO", ratio - 0.5)
    with pytest.raises(DocumentLimitError):
        _parse(data)
