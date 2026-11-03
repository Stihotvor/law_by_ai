"""Live checks against the public Sejm ELI API.

Opt in with ``SEJM_LIVE_TEST=1``. A live public API must not run in the Docker
CI by default. The whole module uses at most 10 requests.
"""

import os
import re
from datetime import datetime

import pytest

from agents.fetch.contracts import DocumentFilter, DocumentRef
from agents.fetch.document_fetcher import DocumentFetcherAgent
from agents.fetch.errors import DocumentNotFoundError

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("SEJM_LIVE_TEST") != "1", reason="set SEJM_LIVE_TEST=1 to run"),
]

SOURCE = "sejm_eli"
ID = re.compile(r"[A-Z]{2,10}/[0-9]{4}/[0-9]{1,6}")


@pytest.fixture(scope="module")
def agent() -> DocumentFetcherAgent:
    return DocumentFetcherAgent()


@pytest.fixture(scope="module")
def refs(agent: DocumentFetcherAgent) -> list[DocumentRef]:
    return list(agent.list_documents(SOURCE, DocumentFilter(limit=3)).items)


def test_list_is_sorted_by_change_desc(
    agent: DocumentFetcherAgent, refs: list[DocumentRef]
) -> None:
    assert len(refs) == 3
    assert all(ID.fullmatch(r.external_id) for r in refs)
    changes = [str(agent.get_document_meta(SOURCE, r).extra["change_date"]) for r in refs]
    assert changes == sorted(changes, reverse=True)


def test_fetch_document_has_text(agent: DocumentFetcherAgent, refs: list[DocumentRef]) -> None:
    doc = agent.fetch_document(SOURCE, refs[0])
    assert doc.content
    parse = getattr(agent, "parse", None)
    if parse is not None:
        assert parse(doc.content, refs[0].external_id, doc.content_type)


def test_date_filter_semantics(agent: DocumentFetcherAgent, refs: list[DocumentRef]) -> None:
    meta = agent.get_document_meta(SOURCE, refs[0])
    published = meta.published_at
    assert isinstance(published, datetime)
    flt = DocumentFilter(date_from=published, date_to=published, limit=500)
    found = {r.external_id for r in agent.list_documents(SOURCE, flt).items}
    assert refs[0].external_id in found, (
        "pubDateFrom/pubDateTo did not return the act for its announcement day: "
        "open item on the meaning of the date parameters"
    )


def test_unknown_act_is_not_found(agent: DocumentFetcherAgent, refs: list[DocumentRef]) -> None:
    bad = refs[0].model_copy(update={"external_id": "DU/2024/999999"})
    with pytest.raises(DocumentNotFoundError):
        agent.get_document_meta(SOURCE, bad)
