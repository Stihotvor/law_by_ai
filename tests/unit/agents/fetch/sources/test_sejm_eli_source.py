import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

import agents.fetch.sources.sejm_eli as sejm
from agents.fetch.contracts import DocumentFilter, DocumentRef
from agents.fetch.document_fetcher import DocumentFetcherAgent
from agents.fetch.errors import DocumentNotFoundError, PayloadError
from agents.fetch.sources.base import SOURCES
from agents.fetch.sources.sejm_eli import MAPPER, SejmEliSource
from agents.fetch.strategies.rest_api import REST_MAPPERS, RestApiStrategy

pytestmark = pytest.mark.usefixtures("no_throttle")

EID = "DU/2024/12"
ROOT = "/eli/acts/DU/2024/12"
REF = DocumentRef(source="sejm_eli", external_id=EID, url=f"{sejm._BASE}/acts/{EID}/text.html")


def _act(html: bool, pdf: bool) -> dict[str, Any]:
    return {
        "ELI": EID,
        "title": "T",
        "type": "Ustawa",
        "announcementDate": "2024-01-02",
        "textHTML": html,
        "textPDF": pdf,
    }


def _source(
    events: list[str], html: bool = True, pdf: bool = True, content_status: int = 200
) -> tuple[SejmEliSource, list[str]]:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        events.append("request")
        path = request.url.raw_path.decode().split("?")[0]
        paths.append(path)
        if path == ROOT:
            return httpx.Response(200, content=json.dumps(_act(html, pdf)))
        if path == "/eli/acts/search":
            body = {"items": [{"ELI": EID}], "offset": 0, "totalCount": 1}
            return httpx.Response(200, content=json.dumps(body))
        if path.endswith("text.html"):
            return httpx.Response(content_status, content=b"<html><p>Tekst</p></html>")
        if path.endswith("text.pdf"):
            return httpx.Response(200, content=b"%PDF-1.7")
        return httpx.Response(404)

    strategy = RestApiStrategy(sejm._BASE, transport=httpx.MockTransport(handler))
    return SejmEliSource(strategy), paths


def test_registration() -> None:
    assert SOURCES.get("sejm_eli") is SejmEliSource
    assert SejmEliSource.name == "sejm_eli"
    assert SejmEliSource.base_url == "https://api.sejm.gov.pl/eli"
    assert SejmEliSource.strategy_name == "rest_api"
    assert SOURCES.names() == ("sejm_eli",)
    assert "sejm_eli" in REST_MAPPERS
    assert REST_MAPPERS.get("sejm_eli") is MAPPER


def test_html_and_pdf_prefers_html(events: list[str]) -> None:
    source, paths = _source(events)
    doc = source.fetch_document(REF)
    assert paths == [ROOT, ROOT + "/text.html"]
    assert doc.content_type == "text/html"
    assert doc.content == b"<html><p>Tekst</p></html>"
    assert doc.meta.ref == REF
    assert doc.fetched_at.utcoffset() is not None
    assert doc.tenant_id is None


def test_pdf_only(events: list[str]) -> None:
    source, paths = _source(events, html=False)
    doc = source.fetch_document(REF)
    assert paths == [ROOT, ROOT + "/text.pdf"]
    assert doc.content_type == "application/pdf"
    assert doc.content == b"%PDF-1.7"


def test_no_text(events: list[str]) -> None:
    source, paths = _source(events, html=False, pdf=False)
    with pytest.raises(DocumentNotFoundError, match="no text"):
        source.fetch_document(REF)
    assert paths == [ROOT]
    assert events == ["wait", "request"]


def test_html_404_does_not_fall_back(events: list[str]) -> None:
    source, paths = _source(events, content_status=404)
    with pytest.raises(DocumentNotFoundError):
        source.fetch_document(REF)
    assert paths == [ROOT, ROOT + "/text.html"]


def test_throttle_order(events: list[str]) -> None:
    source, _ = _source(events)
    source.list_documents(DocumentFilter())
    assert events == ["wait", "request"]
    events.clear()
    source.get_document_meta(REF)
    assert events == ["wait", "request"]
    events.clear()
    source.fetch_document(REF)
    assert events == ["wait", "request", "wait", "request"]


def test_meta_404(events: list[str]) -> None:
    ref = REF.model_copy(update={"external_id": "DU/2024/13"})
    source, _ = _source(events)
    with pytest.raises(DocumentNotFoundError):
        source.get_document_meta(ref)


def test_bad_eli_in_search(events: list[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = {"items": [{"ELI": "../x"}], "offset": 0, "totalCount": 1}
        return httpx.Response(200, content=json.dumps(body))

    strategy = RestApiStrategy(sejm._BASE, transport=httpx.MockTransport(handler))
    with pytest.raises(PayloadError):
        SejmEliSource(strategy).list_documents(DocumentFilter())


def test_through_the_agent(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> None:
    source, _ = _source(events)
    transport = source.strategy._transport  # type: ignore[attr-defined]
    real_init: Callable[..., None] = RestApiStrategy.__init__

    def init(self: RestApiStrategy, base_url: str, **kw: Any) -> None:
        real_init(self, base_url, transport=transport, **kw)

    monkeypatch.setattr(RestApiStrategy, "__init__", init)
    doc = DocumentFetcherAgent().fetch_document("sejm_eli", REF, tenant_id="t1")
    assert doc.content_type == "text/html"
    assert doc.tenant_id == "t1"
    assert b"Tekst" in doc.content
