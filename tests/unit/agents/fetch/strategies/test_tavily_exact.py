import threading
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from tavily.errors import MissingAPIKeyError

from agents.fetch.contracts import DocumentFilter, DocumentRef
from agents.fetch.errors import FetchTransportError, PayloadError, SourceConfigError
from agents.fetch.strategies.tavily import TavilyCrawlStrategy

BASE = "https://api.example/v1"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setenv("TAVILY_MAX_PAGES", "7")
    monkeypatch.setenv("FETCH_MAX_BYTES", "100")


def _mapped(strategy_base: str, results: list[Any]) -> list[str]:
    client = MagicMock()
    client.map.return_value = {"results": results}
    page = TavilyCrawlStrategy(strategy_base, client=client).list_refs("s", DocumentFilter())
    return [r.external_id for r in page.items]


def test_missing_api_key_error_from_sdk_is_translated() -> None:
    with patch("agents.fetch.strategies.tavily.TavilyClient") as cls:
        cls.side_effect = MissingAPIKeyError()
        with pytest.raises(SourceConfigError) as err:
            TavilyCrawlStrategy(BASE).list_refs("s", DocumentFilter())
    assert str(err.value) == "Tavily API key is not set"


def test_closed_message_is_exact() -> None:
    strategy = TavilyCrawlStrategy(BASE, client=MagicMock())
    strategy.close()
    with pytest.raises(FetchTransportError) as err:
        strategy.list_refs("s", DocumentFilter())
    assert str(err.value) == "closed"


def test_pool_has_one_worker_and_is_shut_down_without_waiting() -> None:
    client = MagicMock()
    client.map.return_value = {"results": []}
    with patch("agents.fetch.strategies.tavily.ThreadPoolExecutor") as pool_cls:
        pool = pool_cls.return_value
        strategy = TavilyCrawlStrategy(BASE, client=client)
        strategy._resources()
        pool_cls.assert_called_once_with(max_workers=1)
        strategy.close()
        pool.shutdown.assert_called_once_with(wait=False, cancel_futures=True)


def test_total_timeout_message_is_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_TIMEOUT", "0.2")
    release = threading.Event()
    client = MagicMock()
    client.map.side_effect = lambda **_: release.wait(5)
    try:
        with pytest.raises(FetchTransportError) as err:
            TavilyCrawlStrategy(BASE, client=client).list_refs("s", DocumentFilter())
    finally:
        release.set()
    assert str(err.value) == "tavily: total timeout"


def test_cursor_equal_to_max_pages_is_accepted_and_above_is_rejected() -> None:
    client = MagicMock()
    client.map.return_value = {"results": []}
    page = TavilyCrawlStrategy(BASE, client=client).list_refs("s", DocumentFilter(cursor="7"))
    assert page.items == ()
    assert page.next_cursor is None


def test_url_reached_without_the_base_prefix_is_dropped() -> None:
    # Same host, port and path prefix, but the text before the path differs from the base.
    assert _mapped("https://api.example:443/v1", ["https://api.example/v1/a"]) == []
    assert _mapped("https://api.example:443/v1", ["https://api.example:443/v1/a"]) == ["a"]


def test_fragment_url_is_dropped() -> None:
    assert _mapped(BASE, [BASE + "/a#frag", BASE + "/b"]) == ["b"]


def test_other_url_message_is_exact() -> None:
    client = MagicMock()
    client.extract.return_value = {"results": [{"raw_content": "x", "url": BASE + "/zzz"}]}
    ref = DocumentRef(source="s", external_id="a", url=BASE + "/a")
    with pytest.raises(PayloadError) as err:
        TavilyCrawlStrategy(BASE, client=client).read(ref)
    assert str(err.value) == "tavily extract: result is for another url"


def test_other_url_when_url_is_not_a_string_message_is_exact() -> None:
    client = MagicMock()
    client.extract.return_value = {"results": [{"raw_content": "x", "url": 5}]}
    ref = DocumentRef(source="s", external_id="a", url=BASE + "/a")
    with pytest.raises(PayloadError) as err:
        TavilyCrawlStrategy(BASE, client=client).read(ref)
    assert str(err.value) == "tavily extract: result is for another url"
