import pytest

import agents.fetch.document_fetcher
from agents.fetch.document_fetcher import DocumentFetcherAgent
from agents.fetch.formats.base import FORMATS, UnsupportedFormatError


def test_parse_txt_mime_optional() -> None:
    assert DocumentFetcherAgent().parse(b"hi", "a.txt", "text/plain") == "hi"
    assert DocumentFetcherAgent().parse(b"hi", "a.txt") == "hi"


def test_parse_html() -> None:
    assert DocumentFetcherAgent().parse(b"<p>x</p>", "a.html") == "x"


def test_parse_unsupported() -> None:
    with pytest.raises(UnsupportedFormatError):
        DocumentFetcherAgent().parse(b"x", "a.pdf", "application/pdf")


def test_import_populates_formats() -> None:
    assert agents.fetch.document_fetcher is not None
    assert FORMATS.names() == ("html", "text")
