from typing import Any
from unittest.mock import MagicMock

import pytest

from agents.fetch.contracts import DocumentFilter, DocumentMeta, DocumentRef
from agents.fetch.strategies._hosts import parse_base_url
from agents.fetch.strategies._rest_mapper import RestListing, RestMapper, with_content_variant
from agents.fetch.strategies.tavily import TavilyCrawlStrategy


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "k")


def _ids(base: str, results: list[Any]) -> list[str]:
    client = MagicMock()
    client.map.return_value = {"results": results}
    page = TavilyCrawlStrategy(base, client=client).list_refs("s", DocumentFilter())
    return [r.external_id for r in page.items]


def test_explicit_default_port_url_does_not_start_with_portless_base() -> None:
    # Dropping the prefix check would leave "nts/abcdefgh" as the id for this URL.
    base = "https://api.example/documents"
    assert _ids(base, ["https://api.example:443/documents/abcdefgh"]) == []


def test_matching_url_is_accepted_for_portless_base() -> None:
    assert _ids("https://api.example/v1", ["https://api.example/v1/a"]) == ["a"]


def test_trailing_slash_base_keeps_path_without_slash() -> None:
    assert parse_base_url("https://api.example/vXX/").path == "/vXX"
    assert _ids("https://api.example/vXX/", ["https://api.example/vXX/a"]) == ["a"]


def _meta(payload: Any, ref: DocumentRef) -> DocumentMeta:
    return DocumentMeta(ref=ref, title="t")


def test_content_variant_url_drops_trailing_slash_of_base() -> None:
    mapper = RestMapper(
        list_path="/l",
        meta_path="/m/{external_id}",
        content_path="/c/{external_id}",
        list_params=lambda flt: {},
        parse_list=lambda payload: RestListing(()),
        parse_meta=_meta,
        alt_content_paths={"alt": "/alt/{external_id}"},
    )
    ref = DocumentRef(source="s", external_id="1", url="https://h/v1/c/1")
    out = with_content_variant("https://h/vXX/", mapper, ref, "alt")
    assert out.url == "https://h/vXX/alt/1"
