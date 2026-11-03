import threading
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests
from tavily.errors import (
    BadRequestError,
    ForbiddenError,
    InvalidAPIKeyError,
    KeylessUnsupportedEndpointError,
    MissingAPIKeyError,
    UsageLimitExceededError,
)
from tavily.errors import TimeoutError as TavilyTimeoutError

from agents.fetch import document_fetcher
from agents.fetch.contracts import DocumentFilter, DocumentRef
from agents.fetch.errors import (
    DocumentNotFoundError,
    FetchError,
    FetchTransportError,
    InvalidReferenceError,
    PayloadError,
    ResponseTooLargeError,
    SourceConfigError,
)
from agents.fetch.sources.base import SOURCES
from agents.fetch.strategies.base import STRATEGIES, FetchStrategy
from agents.fetch.strategies.tavily import TavilyCrawlStrategy

_REGISTERED = document_fetcher  # importing it registers the strategies
BASE = "https://api.example/v1"
KEY = "tvly-KEY-VALUE-123"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", KEY)
    monkeypatch.setenv("TAVILY_TIMEOUT", "60")
    monkeypatch.setenv("TAVILY_MAX_PAGES", "7")
    monkeypatch.setenv("FETCH_MAX_BYTES", "100")


def _client(results: list[Any] | None = None) -> MagicMock:
    client = MagicMock()
    client.map.return_value = {"results": results if results is not None else []}
    return client


def _urls(*names: str) -> list[str]:
    return [f"{BASE}/{n}" for n in names]


def _strategy(client: MagicMock) -> TavilyCrawlStrategy:
    return TavilyCrawlStrategy(BASE, client=client)


def _ref(eid: str = "a/b.html") -> DocumentRef:
    return DocumentRef(source="s", external_id=eid, url=f"{BASE}/{eid}")


def _ids(client: MagicMock, **flt: Any) -> list[str]:
    page = _strategy(client).list_refs("s", DocumentFilter(**flt))
    return [r.external_id for r in page.items]


@pytest.mark.parametrize(
    "base",
    ["http://api.example/v1", "https://u:p@api.example/v1", "https://@api.example", "https://"],
)
def test_constructor_rejects_bad_base(base: str) -> None:
    with pytest.raises(SourceConfigError):
        TavilyCrawlStrategy(base, client=_client())


def test_empty_key_rejected_without_leak(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "")
    with (
        patch("agents.fetch.strategies.tavily.TavilyClient") as cls,
        pytest.raises(SourceConfigError, match="API key is not set") as err,
    ):
        TavilyCrawlStrategy(BASE)
    cls.assert_not_called()
    assert KEY not in str(err.value)


def test_key_comes_from_settings_and_session_ignores_env() -> None:
    with patch("agents.fetch.strategies.tavily.TavilyClient") as cls:
        cls.return_value.map.return_value = {"results": []}
        strategy = TavilyCrawlStrategy(BASE)
        strategy.list_refs("s", DocumentFilter())
    cls.assert_called_once_with(api_key=KEY)
    assert cls.return_value.session.trust_env is False
    assert KEY not in repr(strategy)


def test_list_refs_call_and_filtering() -> None:
    client = _client(
        [
            *_urls("z.html", "a.html", "a.html", "d/e?x=1"),
            BASE,
            BASE + "/",
            "https://other.example/v1/a",
            "http://api.example/v1/a",
            "https://api.example/v1x/a",
            "https://api.example:8443/v1/a",
            BASE + "/f#frag",
            "https://u@api.example/v1/a",
            BASE + "/c\x00d",
            BASE + "/../x",
            BASE + "//x",
            BASE + "/a\\b",
            "https://api.example:bad/v1/a",
            7,
            None,
        ]
    )
    assert _ids(client) == ["a.html", "d/e?x=1", "z.html"]
    client.map.assert_called_once_with(
        url=BASE,
        max_depth=2,
        max_breadth=20,
        limit=7,
        allow_external=False,
        select_domains=[r"^api\.example$"],
        timeout=60.0,
    )


def test_map_results_beyond_max_pages_are_ignored() -> None:
    client = _client(_urls(*[f"p{i}" for i in range(20)]))
    assert _ids(client, limit=50) == sorted(f"p{i}" for i in range(7))


def test_refs_carry_urls() -> None:
    page = _strategy(_client(_urls("a/b"))).list_refs("s", DocumentFilter())
    ref = page.items[0]
    assert (ref.source, ref.external_id, ref.url) == ("s", "a/b", BASE + "/a/b")


def test_default_port_is_accepted() -> None:
    client = _client(["https://api.example:443/v1/a"])
    strategy = TavilyCrawlStrategy("https://api.example:443/v1", client=client)
    assert [r.external_id for r in strategy.list_refs("s", DocumentFilter()).items] == ["a"]


@pytest.mark.parametrize("body", [None, [], {}, {"results": "x"}])
def test_bad_map_payload(body: Any) -> None:
    client = MagicMock()
    client.map.return_value = body
    with pytest.raises(PayloadError):
        _strategy(client).list_refs("s", DocumentFilter())


def _five() -> MagicMock:
    return _client(_urls("a1", "a2", "a3", "a4", "b5"))


def test_paging_first_page() -> None:
    page = _strategy(_five()).list_refs("s", DocumentFilter(limit=2))
    assert [r.external_id for r in page.items] == ["a1", "a2"]
    assert page.next_cursor == "2"


def test_paging_last_page() -> None:
    page = _strategy(_five()).list_refs("s", DocumentFilter(limit=2, cursor="4"))
    assert [r.external_id for r in page.items] == ["b5"]
    assert page.next_cursor is None


def test_paging_exact_end_has_no_cursor() -> None:
    page = _strategy(_five()).list_refs("s", DocumentFilter(limit=3, cursor="2"))
    assert len(page.items) == 3
    assert page.next_cursor is None


@pytest.mark.parametrize("cursor", ["abc", "-1", "1e3", "9999999999", "", "1 ", "8"])
def test_bad_cursor_makes_no_call(cursor: str) -> None:
    client = _client()
    with pytest.raises(InvalidReferenceError):
        _strategy(client).list_refs("s", DocumentFilter(cursor=cursor))
    client.map.assert_not_called()


def test_keyword_filters_before_paging_case_insensitive() -> None:
    client = _client(_urls("A1", "b2", "a3", "a4"))
    page = _strategy(client).list_refs("s", DocumentFilter(keyword="a", limit=2))
    assert [r.external_id for r in page.items] == ["A1", "a3"]
    assert page.next_cursor == "2"


def test_unsupported_filters_ignored() -> None:
    from datetime import UTC, datetime

    client = _client(_urls("a", "b"))
    flt = {
        "date_from": datetime(2024, 1, 1, tzinfo=UTC),
        "date_to": datetime(2024, 2, 1, tzinfo=UTC),
        "doc_type": "x",
    }
    assert _ids(client, **flt) == ["a", "b"]


@pytest.mark.parametrize(
    ("setting", "expected"),
    [("5", 10.0), ("500", 150.0), ("30", 30.0), ("10", 10.0), ("150", 150.0)],
)
def test_map_timeout_clamp(monkeypatch: pytest.MonkeyPatch, setting: str, expected: float) -> None:
    monkeypatch.setenv("TAVILY_TIMEOUT", setting)
    client = _client()
    _ids(client)
    assert client.map.call_args.kwargs["timeout"] == expected


@pytest.mark.parametrize(
    ("setting", "expected"), [("0.5", 1.0), ("120", 60.0), ("30", 30.0), ("1", 1.0), ("60", 60.0)]
)
def test_extract_timeout_clamp(
    monkeypatch: pytest.MonkeyPatch, setting: str, expected: float
) -> None:
    monkeypatch.setenv("TAVILY_TIMEOUT", setting)
    client = _extract({"results": [{"raw_content": "x"}]})
    _strategy(client).read(_ref())
    assert client.extract.call_args.kwargs["timeout"] == expected


def test_get_meta_no_call() -> None:
    client = _client()
    meta = _strategy(client).get_meta(_ref("docs/My%20Page.html?x=1"))
    assert meta.title == "My Page.html"
    assert meta.doc_type is None
    assert meta.published_at is None
    assert meta.language is None
    assert meta.extra == {"content_type": "text/plain; charset=utf-8"}
    assert client.mock_calls == []


def test_get_meta_title_falls_back_to_id() -> None:
    assert _strategy(_client()).get_meta(_ref("?q=1")).title == "?q=1"
    assert _strategy(_client()).get_meta(_ref("x/%20")).title == " "


@pytest.mark.parametrize(
    "eid", ["/a", "a//b", "../a", "a/./b", "a\\b", "a#b", "a://b", "a\x01b", "a\x7fb"]
)
def test_unsafe_ids(eid: str) -> None:
    strategy = _strategy(_client())
    with pytest.raises(InvalidReferenceError):
        strategy.get_meta(_ref(eid))
    with pytest.raises(InvalidReferenceError):
        strategy.read(_ref(eid))


def _extract(body: Any) -> MagicMock:
    client = MagicMock()
    client.extract.return_value = body
    return client


def test_read_returns_utf8_and_rebuilds_url() -> None:
    client = _extract({"results": [{"url": "u", "raw_content": "zażółć"}]})
    ref = DocumentRef(source="s", external_id="a/b", url="https://evil.example/x")
    assert _strategy(client).read(ref) == "zażółć".encode()
    client.extract.assert_called_once_with(
        urls=BASE + "/a/b", extract_depth="basic", format="text", timeout=60.0
    )


def test_read_failed_results_is_transport_error() -> None:
    client = _extract({"results": [], "failed_results": [{"url": "u", "error": "e"}]})
    with pytest.raises(FetchTransportError, match="tavily extract failed"):
        _strategy(client).read(_ref())


def test_read_empty_is_not_found() -> None:
    for body in ({"results": []}, {"results": [], "failed_results": []}):
        with pytest.raises(DocumentNotFoundError):
            _strategy(_extract(body)).read(_ref())


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"results": "x"},
        {"results": [{"raw_content": "a"}, {"raw_content": "b"}]},
        {"results": [{"raw_content": 5}]},
        {"results": [{"raw_content": ""}]},
        {"results": [{}]},
        {"results": ["x"]},
    ],
)
def test_read_bad_payload(body: Any) -> None:
    with pytest.raises(PayloadError):
        _strategy(_extract(body)).read(_ref())


def test_read_size_limit_boundary() -> None:
    ok = _extract({"results": [{"raw_content": "a" * 100}]})
    assert len(_strategy(ok).read(_ref())) == 100
    big = _extract({"results": [{"raw_content": "a" * 101}]})
    with pytest.raises(ResponseTooLargeError):
        _strategy(big).read(_ref())
    multi = _extract({"results": [{"raw_content": "ż" * 51}]})
    with pytest.raises(ResponseTooLargeError):
        _strategy(multi).read(_ref())


def _error_cases() -> list[tuple[Exception, type[FetchError], int | None]]:
    marker = "SECRET-MARKER"
    return [
        (InvalidAPIKeyError(marker), SourceConfigError, None),
        (UsageLimitExceededError(marker), FetchTransportError, 429),
        (ForbiddenError(marker), FetchTransportError, 403),
        (BadRequestError(marker), FetchTransportError, 400),
        (TavilyTimeoutError(30), FetchTransportError, None),
        (requests.exceptions.ConnectionError(marker + KEY), FetchTransportError, None),
    ]


@pytest.mark.parametrize("op", ["map", "extract"])
@pytest.mark.parametrize(("exc", "kind", "status"), _error_cases())
def test_error_mapping(op: str, exc: Exception, kind: type[FetchError], status: int | None) -> None:
    client = MagicMock()
    getattr(client, op).side_effect = exc
    strategy = _strategy(client)
    with pytest.raises(kind) as err:
        if op == "map":
            strategy.list_refs("s", DocumentFilter())
        else:
            strategy.read(_ref())
    text = str(err.value)
    assert "SECRET-MARKER" not in text
    assert KEY not in text
    assert getattr(err.value, "status_code", None) == status
    if kind is FetchTransportError:
        assert type(exc).__name__ in text


def test_status_text_in_message() -> None:
    client = MagicMock()
    client.map.side_effect = UsageLimitExceededError("x")
    with pytest.raises(FetchTransportError, match=r"UsageLimitExceededError \(HTTP 429\)"):
        _strategy(client).list_refs("s", DocumentFilter())


def test_key_rejected_message() -> None:
    client = MagicMock()
    client.map.side_effect = InvalidAPIKeyError("x")
    with pytest.raises(SourceConfigError, match="Tavily rejected the API key"):
        _strategy(client).list_refs("s", DocumentFilter())


def test_fetch_error_passes_through() -> None:
    client = MagicMock()
    err = PayloadError("mine")
    client.extract.side_effect = err
    with pytest.raises(PayloadError) as got:
        _strategy(client).read(_ref())
    assert got.value is err


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (MissingAPIKeyError(), SourceConfigError),
        (KeylessUnsupportedEndpointError("map"), FetchTransportError),
        (Exception("secret"), FetchTransportError),
        (AttributeError("secret"), FetchTransportError),
        (RuntimeError("secret"), FetchTransportError),
    ],
)
def test_any_sdk_exception_becomes_typed(exc: Exception, kind: type[FetchError]) -> None:
    client = MagicMock()
    client.map.side_effect = exc
    with pytest.raises(kind) as err:
        _strategy(client).list_refs("s", DocumentFilter())
    assert "secret" not in str(err.value)
    if kind is FetchTransportError:
        assert type(exc).__name__ in str(err.value)


def test_total_timeout_bounds_a_blocked_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_TIMEOUT", "0.2")
    release = threading.Event()
    client = MagicMock()
    client.map.side_effect = lambda **_: release.wait(5)
    try:
        with pytest.raises(FetchTransportError, match="total timeout"):
            _strategy(client).list_refs("s", DocumentFilter())
    finally:
        release.set()


def test_injected_client_not_closed() -> None:
    client = _client()
    _ids(client)
    client.close.assert_not_called()


def test_owned_client_closed_after_each_operation() -> None:
    with patch("agents.fetch.strategies.tavily.TavilyClient") as cls:
        cls.return_value.map.return_value = {"results": []}
        cls.return_value.extract.return_value = {"results": [{"raw_content": "x"}]}
        strategy = TavilyCrawlStrategy(BASE)
        strategy.list_refs("s", DocumentFilter())
        assert cls.return_value.close.call_count == 1
        strategy.read(_ref())
        assert cls.return_value.close.call_count == 2


def test_owned_client_closed_on_error() -> None:
    with patch("agents.fetch.strategies.tavily.TavilyClient") as cls:
        cls.return_value.map.side_effect = ForbiddenError("x")
        with pytest.raises(FetchTransportError):
            TavilyCrawlStrategy(BASE).list_refs("s", DocumentFilter())
        cls.return_value.close.assert_called_once_with()


def test_registered() -> None:
    assert STRATEGIES.get("tavily") is TavilyCrawlStrategy
    assert isinstance(_strategy(_client()), FetchStrategy)
    assert STRATEGIES.names() == ("minio", "rest_api", "tavily")


def test_tavily_sources_use_https() -> None:
    for name in SOURCES.names():
        cls = SOURCES.get(name)
        if cls.strategy_name == "tavily":
            assert cls.base_url.startswith("https://")


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (MissingAPIKeyError(), SourceConfigError),
        (requests.exceptions.ConnectionError("x"), FetchTransportError),
    ],
)
def test_client_construction_errors_are_typed(exc: Exception, kind: type[FetchError]) -> None:
    with patch("agents.fetch.strategies.tavily.TavilyClient", side_effect=exc):
        strategy = TavilyCrawlStrategy(BASE)
        with pytest.raises(kind) as err:
            strategy.list_refs("s", DocumentFilter())
    assert KEY not in str(err.value)


@pytest.mark.parametrize("exc", [ValueError("secret"), TypeError("secret"), KeyError("secret")])
def test_unexpected_sdk_errors_become_typed(exc: Exception) -> None:
    client = _client()
    client.map.side_effect = exc
    with pytest.raises(FetchTransportError) as err:
        _strategy(client).list_refs("s", DocumentFilter())
    assert "secret" not in str(err.value)
