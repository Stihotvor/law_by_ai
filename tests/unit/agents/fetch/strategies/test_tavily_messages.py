from typing import Any
from unittest.mock import MagicMock

import pytest
from tavily.errors import InvalidAPIKeyError

from agents.fetch.contracts import DocumentFilter, DocumentRef
from agents.fetch.errors import (
    DocumentNotFoundError,
    FetchTransportError,
    InvalidReferenceError,
    PayloadError,
    ResponseTooLargeError,
    SourceConfigError,
)
from agents.fetch.strategies.tavily import TavilyCrawlStrategy

BASE = "https://api.example/v1"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setenv("FETCH_MAX_BYTES", "10")


def _ref(eid: str) -> DocumentRef:
    return DocumentRef(source="s", external_id=eid, url=f"{BASE}/{eid}")


def _extract(body: Any) -> TavilyCrawlStrategy:
    client = MagicMock()
    client.extract.return_value = body
    return TavilyCrawlStrategy(BASE, client=client)


def _mapped(results: list[Any]) -> list[str]:
    client = MagicMock()
    client.map.return_value = {"results": results}
    page = TavilyCrawlStrategy(BASE, client=client).list_refs("s", DocumentFilter())
    return [r.external_id for r in page.items]


@pytest.mark.parametrize(
    ("base", "message"),
    [
        ("http://a.example", "base_url must start with https://"),
        ("https://u:p@a.example", "base_url must not contain credentials"),
        ("https://@a.example", "base_url must not contain credentials"),
        ("https://", "base_url needs a host"),
    ],
)
def test_constructor_messages(base: str, message: str) -> None:
    with pytest.raises(SourceConfigError) as err:
        TavilyCrawlStrategy(base, client=MagicMock())
    assert str(err.value) == message


def test_missing_key_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "")
    with pytest.raises(SourceConfigError) as err:
        TavilyCrawlStrategy(BASE)
    assert str(err.value) == "Tavily API key is not set"


@pytest.mark.parametrize("base", [BASE + "/", BASE + "//", "https://x.example/X/"])
def test_trailing_slashes_are_trimmed(base: str) -> None:
    ref = _ref("a")
    client = MagicMock()
    client.extract.return_value = {"results": [{"raw_content": "x"}]}
    TavilyCrawlStrategy(base, client=client).read(ref)
    assert client.extract.call_args.kwargs["urls"] == base.rstrip("/") + "/a"


def test_space_is_not_a_control_character() -> None:
    assert TavilyCrawlStrategy(BASE, client=MagicMock()).get_meta(_ref("a b")).title == "a b"
    assert _mapped([BASE + "/a b"]) == ["a b"]


@pytest.mark.parametrize("char", ["\x7f", "\x80", "\x1f"])
def test_control_characters_in_map_urls(char: str) -> None:
    assert _mapped([BASE + "/a" + char]) == ([] if char != "\x80" else ["a\x80"])


def test_title_is_last_segment() -> None:
    meta = TavilyCrawlStrategy(BASE, client=MagicMock()).get_meta(_ref("x/y/z.html"))
    assert meta.title == "z.html"


def test_message_texts() -> None:
    with pytest.raises(InvalidReferenceError) as err:
        TavilyCrawlStrategy(BASE, client=MagicMock()).get_meta(_ref("../x"))
    assert str(err.value) == "unsafe external_id"
    with pytest.raises(InvalidReferenceError) as err:
        TavilyCrawlStrategy(BASE, client=MagicMock()).list_refs("s", DocumentFilter(cursor="x"))
    assert str(err.value) == "invalid cursor"
    client = MagicMock()
    client.map.return_value = None
    with pytest.raises(PayloadError) as err2:
        TavilyCrawlStrategy(BASE, client=client).list_refs("s", DocumentFilter())
    assert str(err2.value) == "tavily map: unexpected response"


def test_extract_message_texts() -> None:
    cases: list[tuple[Any, type[Exception], str]] = [
        (None, PayloadError, "tavily extract: unexpected response"),
        ({"results": 3}, PayloadError, "tavily extract: unexpected response"),
        ({"results": []}, DocumentNotFoundError, "tavily extract: no content"),
        ({"results": [], "failed_results": [1]}, FetchTransportError, "tavily extract failed"),
        ({"results": [{}]}, PayloadError, "tavily extract: unexpected result"),
        (
            {"results": [{"raw_content": "x" * 11}]},
            ResponseTooLargeError,
            "extracted text is larger than the size limit",
        ),
    ]
    for body, kind, message in cases:
        with pytest.raises(kind) as err:
            _extract(body).read(_ref("a"))
        assert str(err.value) == message


def test_content_is_utf8() -> None:
    assert _extract({"results": [{"raw_content": "ż"}]}).read(_ref("a")) == b"\xc5\xbc"


def test_rejected_key_message_is_exact() -> None:
    client = MagicMock()
    client.map.side_effect = InvalidAPIKeyError("x")
    with pytest.raises(SourceConfigError) as err:
        TavilyCrawlStrategy(BASE, client=client).list_refs("s", DocumentFilter())
    assert str(err.value) == "Tavily rejected the API key"
