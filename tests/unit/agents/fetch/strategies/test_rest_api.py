from collections.abc import Callable
from datetime import datetime
from typing import Any, cast

import httpx
import pytest

from agents.fetch.contracts import DocumentFilter, DocumentMeta, DocumentRef
from agents.fetch.errors import (
    DocumentNotFoundError,
    FetchTransportError,
    InvalidReferenceError,
    PayloadError,
    RedirectNotAllowedError,
    ResponseTooLargeError,
    SourceConfigError,
)
from agents.fetch.registry import Registry
from agents.fetch.strategies import STRATEGIES
from agents.fetch.strategies.base import FetchStrategy
from agents.fetch.strategies.rest_api import (
    REST_MAPPERS,
    RestApiStrategy,
    RestListing,
    RestMapper,
)

BASE = "https://api.example/v1"
Handler = Callable[[httpx.Request], httpx.Response]
pytestmark = pytest.mark.usefixtures("settings_env")


def _parse_list(payload: Any) -> RestListing:
    return RestListing(tuple(i["id"] for i in payload["items"]), payload.get("next"))


def _parse_meta(payload: Any, ref: DocumentRef) -> DocumentMeta:
    return DocumentMeta(
        ref=ref,
        title=payload["title"],
        doc_type=payload["type"],
        published_at=datetime.fromisoformat(payload["date"]),
        language=payload["lang"],
        extra={"content_type": payload["mime"]},
    )


def _mapper(**over: Any) -> RestMapper:
    args: dict[str, Any] = {
        "list_path": "/documents",
        "meta_path": "/documents/{external_id}",
        "content_path": "/documents/{external_id}/file",
        "list_params": lambda flt: {"q": flt.keyword or "", "n": str(flt.limit)},
        "parse_list": _parse_list,
        "parse_meta": _parse_meta,
    }
    args.update(over)
    return RestMapper(**args)


def _registry(mapper: RestMapper | None = None) -> Registry[RestMapper]:
    reg: Registry[RestMapper] = Registry("test_mappers")
    reg.register("src")(mapper or _mapper())
    return reg


def _strategy(handler: Handler, mapper: RestMapper | None = None) -> RestApiStrategy:
    return RestApiStrategy(BASE, mappers=_registry(mapper), transport=httpx.MockTransport(handler))


def _ref(eid: str = "1") -> DocumentRef:
    return DocumentRef(source="src", external_id=eid, url="https://x/y")


def _json(data: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data)


META = {
    "title": "T",
    "type": "act",
    "date": "2024-01-02T03:04:05+00:00",
    "lang": "pl",
    "mime": "application/pdf",
}


def test_list_refs_request_and_refs() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return _json({"items": [{"id": "1"}, {"id": "a b"}], "next": "c2"})

    page = _strategy(handler).list_refs("src", DocumentFilter(keyword="k", limit=5))
    assert len(seen) == 1
    assert seen[0].method == "GET"
    assert str(seen[0].url) == "https://api.example/v1/documents?q=k&n=5"
    assert [r.external_id for r in page.items] == ["1", "a b"]
    assert all(r.source == "src" for r in page.items)
    assert page.items[1].url == f"{BASE}/documents/a%20b/file"
    assert page.next_cursor == "c2"


def test_list_params_gets_same_filter_and_ignored_fields_not_sent() -> None:
    got: list[DocumentFilter] = []

    def params(flt: DocumentFilter) -> dict[str, str]:
        got.append(flt)
        return {"n": str(flt.limit)}

    urls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        urls.append(str(req.url))
        return _json({"items": []})

    flt = DocumentFilter(keyword="secret-kw", doc_type="act", limit=7)
    _strategy(handler, _mapper(list_params=params)).list_refs("src", flt)
    assert got == [flt] and got[0] is flt
    assert urls == ["https://api.example/v1/documents?n=7"]


def test_list_refs_too_many_ids() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return _json({"items": [{"id": "1"}, {"id": "2"}]})

    with pytest.raises(PayloadError):
        _strategy(handler).list_refs("src", DocumentFilter(limit=1))


def test_list_refs_exactly_limit_ok() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return _json({"items": [{"id": "1"}, {"id": "2"}]})

    page = _strategy(handler).list_refs("src", DocumentFilter(limit=2))
    assert len(page.items) == 2
    assert page.next_cursor is None


def test_get_meta() -> None:
    urls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        urls.append(str(req.url))
        return _json(META)

    meta = _strategy(handler).get_meta(_ref("a/b"))
    assert urls == [f"{BASE}/documents/a%2Fb"]
    assert meta.title == "T"
    assert meta.extra["content_type"] == "application/pdf"


def test_get_meta_ref_mismatch() -> None:
    def other(payload: Any, ref: DocumentRef) -> DocumentMeta:
        return DocumentMeta(ref=_ref("other"), title="t")

    with pytest.raises(PayloadError):
        _strategy(lambda r: _json(META), _mapper(parse_meta=other)).get_meta(_ref())


def test_read_returns_bytes() -> None:
    urls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        urls.append(str(req.url))
        return httpx.Response(200, content=b"%PDF")

    assert _strategy(handler).read(_ref("7")) == b"%PDF"
    assert urls == [f"{BASE}/documents/7/file"]


def test_read_ignores_ref_url() -> None:
    hosts: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        hosts.append(req.url.host)
        return httpx.Response(200, content=b"x")

    ref = DocumentRef(source="src", external_id="1", url="https://evil.example/x")
    _strategy(handler).read(ref)
    _strategy(lambda r: (hosts.append(r.url.host), _json(META))[1]).get_meta(ref)
    assert hosts == ["api.example", "api.example"]


def test_external_id_encoded_as_one_segment() -> None:
    raw: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        raw.append(req.url.raw_path.decode())
        return httpx.Response(200, content=b"x")

    _strategy(handler).read(_ref("a/b?x=1#f"))
    assert raw == ["/v1/documents/a%2Fb%3Fx%3D1%23f/file"]


@pytest.mark.parametrize("eid", ["", ".", "..", "a\nb", "a\x00b", "a\x7fb"])
def test_unsafe_ids_never_hit_transport(eid: str) -> None:
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append("hit")
        return httpx.Response(200, content=b"x")

    strategy = _strategy(handler)
    ref = DocumentRef.model_construct(source="src", external_id=eid, url="https://x/y")
    with pytest.raises(InvalidReferenceError):
        strategy.read(ref)
    with pytest.raises(InvalidReferenceError):
        strategy.get_meta(ref)
    assert calls == []


def test_dotted_but_valid_ids_allowed() -> None:
    assert _strategy(lambda r: httpx.Response(200, content=b"x")).read(_ref("..a")) == b"x"
    assert _strategy(lambda r: httpx.Response(200, content=b"x")).read(_ref("a b")) == b"x"


def test_redirect_same_host_followed() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/file"):
            return httpx.Response(302, headers={"location": "https://api.example/v1/real"})
        return httpx.Response(200, content=b"ok")

    assert _strategy(handler).read(_ref()) == b"ok"


def test_redirect_explicit_default_port_followed() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/file"):
            return httpx.Response(302, headers={"location": "https://api.example:443/v1/real"})
        return httpx.Response(200, content=b"ok")

    assert _strategy(handler).read(_ref()) == b"ok"


def test_redirect_other_host_blocked_before_request() -> None:
    hosts: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        hosts.append(req.url.host)
        return httpx.Response(302, headers={"location": "https://other.example/x"})

    with pytest.raises(RedirectNotAllowedError):
        _strategy(handler).read(_ref())
    assert hosts == ["api.example"]


def test_redirect_other_port_blocked() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://api.example:8443/x"})

    with pytest.raises(RedirectNotAllowedError):
        _strategy(handler).read(_ref())


def test_redirect_to_http_blocked() -> None:
    hosts: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        hosts.append(req.url.scheme)
        return httpx.Response(302, headers={"location": "http://api.example/x"})

    with pytest.raises(RedirectNotAllowedError):
        _strategy(handler).read(_ref())
    assert hosts == ["https"]


def test_redirect_loop_limited() -> None:
    n = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal n
        n += 1
        return httpx.Response(302, headers={"location": "https://api.example/v1/loop"})

    with pytest.raises(FetchTransportError) as info:
        _strategy(handler).read(_ref())
    assert not isinstance(info.value, RedirectNotAllowedError)
    assert n == 4


def test_timeout_maps_to_transport_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=req)

    with pytest.raises(FetchTransportError) as info:
        _strategy(handler).read(_ref())
    assert isinstance(info.value.__cause__, httpx.ReadTimeout)


def test_client_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    real = httpx.Client

    def spy(**kwargs: Any) -> httpx.Client:
        captured.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr("agents.fetch.strategies.rest_api.httpx.Client", spy)
    _strategy(lambda r: httpx.Response(200, content=b"x")).read(_ref())
    assert captured["timeout"] == httpx.Timeout(3.5)
    assert captured["follow_redirects"] is True
    assert captured["max_redirects"] == 3
    assert captured["trust_env"] is False
    assert "verify" not in captured
    assert len(captured["event_hooks"]["request"]) == 1


def test_not_found() -> None:
    with pytest.raises(DocumentNotFoundError):
        _strategy(lambda r: httpx.Response(404)).read(_ref())


def test_server_error_status_and_message() -> None:
    strategy = _strategy(lambda r: httpx.Response(500))
    with pytest.raises(FetchTransportError) as info:
        strategy.list_refs("src", DocumentFilter(keyword="private-kw"))
    assert info.value.status_code == 500
    assert "private-kw" not in str(info.value)
    assert "?" not in str(info.value)
    assert "/documents" in str(info.value)


def test_status_boundary_300_is_error_299_ok() -> None:
    assert _strategy(lambda r: httpx.Response(204)).read(_ref()) == b""
    with pytest.raises(FetchTransportError):
        _strategy(lambda r: httpx.Response(304)).read(_ref())


def test_too_large_by_content_length() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-length": "101"}, content=b"x" * 101)

    with pytest.raises(ResponseTooLargeError):
        _strategy(handler).read(_ref())


def test_exactly_max_bytes_ok() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-length": "100"}, content=b"x" * 100)

    assert len(_strategy(handler).read(_ref())) == 100


def test_too_large_by_stream_without_header() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        def gen() -> Any:
            yield b"x" * 60
            yield b"x" * 60

        return httpx.Response(200, content=gen())

    with pytest.raises(ResponseTooLargeError):
        _strategy(handler).read(_ref())


def test_total_deadline_stops_slow_body(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = iter([0.0, 1.0, 100.0, 200.0])
    monkeypatch.setattr("agents.fetch.strategies.rest_api._monotonic", lambda: next(ticks))

    def handler(req: httpx.Request) -> httpx.Response:
        def gen() -> Any:
            yield b"x"
            yield b"x"

        return httpx.Response(200, content=gen())

    with pytest.raises(FetchTransportError, match="total timeout"):
        _strategy(handler).read(_ref())


def test_stream_exactly_max_ok() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        def gen() -> Any:
            yield b"x" * 50
            yield b"x" * 50

        return httpx.Response(200, content=gen())

    assert len(_strategy(handler).read(_ref())) == 100


def test_invalid_json() -> None:
    with pytest.raises(PayloadError):
        _strategy(lambda r: httpx.Response(200, content=b"{nope")).get_meta(_ref())
    with pytest.raises(PayloadError):
        _strategy(lambda r: httpx.Response(200, content=b"\xff\xfe")).get_meta(_ref())


def test_mapper_errors_become_payload_error() -> None:
    with pytest.raises(PayloadError) as info:
        _strategy(lambda r: _json({})).list_refs("src", DocumentFilter())
    assert isinstance(info.value.__cause__, KeyError)

    bad = dict(META, date="2024-01-02T03:04:05")  # naive datetime
    with pytest.raises(PayloadError):
        _strategy(lambda r: _json(bad)).get_meta(_ref())

    def boom(flt: DocumentFilter) -> dict[str, str]:
        raise TypeError("x")

    with pytest.raises(PayloadError):
        _strategy(lambda r: _json({}), _mapper(list_params=boom)).list_refs("src", DocumentFilter())


def test_fetch_errors_pass_through_mapper() -> None:
    def boom(payload: Any) -> RestListing:
        raise DocumentNotFoundError("inner")

    with pytest.raises(DocumentNotFoundError):
        _strategy(lambda r: _json({}), _mapper(parse_list=boom)).list_refs("src", DocumentFilter())


def test_no_mapper_and_bad_base_url() -> None:
    strategy = RestApiStrategy(
        BASE, mappers=Registry("empty"), transport=httpx.MockTransport(lambda r: _json({}))
    )
    with pytest.raises(SourceConfigError):
        strategy.list_refs("src", DocumentFilter())
    with pytest.raises(SourceConfigError):
        strategy.read(_ref())
    with pytest.raises(SourceConfigError):
        RestApiStrategy("http://x")


def test_base_url_trailing_slash_and_port() -> None:
    urls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        urls.append(str(req.url))
        return httpx.Response(200, content=b"x")

    strategy = RestApiStrategy(
        "https://api.example:8443/v1/",
        mappers=_registry(),
        transport=httpx.MockTransport(handler),
    )
    strategy.read(_ref())
    assert urls == ["https://api.example:8443/v1/documents/1/file"]


def test_default_registry_used() -> None:
    with pytest.raises(SourceConfigError):
        RestApiStrategy(BASE).read(_ref("1"))


def test_registered_and_protocol() -> None:
    assert STRATEGIES.get("rest_api") is RestApiStrategy
    assert isinstance(RestApiStrategy(BASE), FetchStrategy)


def test_real_rest_sources_have_mappers() -> None:
    from agents.fetch.sources import SOURCES

    for name in SOURCES.names():
        if SOURCES.get(name).strategy_name == "rest_api":
            assert name in REST_MAPPERS


def _msg(exc: pytest.ExceptionInfo[Any]) -> str:
    return str(exc.value)


def test_mapper_validation_messages() -> None:
    with pytest.raises(SourceConfigError) as a:
        _mapper(list_path="documents")
    assert _msg(a) == "list_path must start with '/' and have no '{'"
    with pytest.raises(SourceConfigError) as b:
        _mapper(meta_path="/m")
    assert _msg(b) == "meta_path must start with '/' and have {external_id}"
    with pytest.raises(SourceConfigError) as c:
        _mapper(content_path="/c")
    assert _msg(c) == "content_path must start with '/' and have {external_id}"


def test_base_url_message_and_trailing_slash() -> None:
    with pytest.raises(SourceConfigError) as a:
        RestApiStrategy("http://x")
    assert _msg(a) == "base_url must start with https://"
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        return _json({"items": []})

    s = RestApiStrategy(
        "https://api.example/vXX/", mappers=_registry(), transport=httpx.MockTransport(handler)
    )
    s.list_refs("src", DocumentFilter())
    assert seen[0].startswith("https://api.example/vXX/documents?")


def test_unknown_source_message() -> None:
    s = _strategy(lambda r: _json({}))
    with pytest.raises(SourceConfigError) as a:
        s.list_refs("zzz", DocumentFilter())
    assert _msg(a) == "no REST mapper for source 'zzz'"


def test_unsafe_id_message() -> None:
    s = _strategy(lambda r: _json({}))
    with pytest.raises(InvalidReferenceError) as a:
        s.read(_ref(".."))
    assert _msg(a) == "unsafe external_id"


def test_mapper_failure_message() -> None:
    s = _strategy(lambda r: _json({}))
    with pytest.raises(PayloadError) as a:
        s.list_refs("src", DocumentFilter())
    assert _msg(a) == "mapper failed: KeyError"


def test_list_messages() -> None:
    s = _strategy(lambda r: _json({"items": [{"id": "1"}, {"id": "2"}]}))
    with pytest.raises(PayloadError) as a:
        s.list_refs("src", DocumentFilter(limit=1))
    assert _msg(a) == "mapper returned more ids than limit"
    s = _strategy(lambda r: httpx.Response(500))
    with pytest.raises(FetchTransportError) as b:
        s.list_refs("src", DocumentFilter())
    assert _msg(b) == "GET /documents: HTTP 500"
    s = _strategy(lambda r: httpx.Response(200, content=b"{"))
    with pytest.raises(PayloadError) as c:
        s.list_refs("src", DocumentFilter())
    assert _msg(c) == "GET /documents: invalid JSON"


def test_get_meta_messages() -> None:
    s = _strategy(lambda r: httpx.Response(503))
    with pytest.raises(FetchTransportError) as a:
        s.get_meta(_ref())
    assert _msg(a) == "GET /documents/1: HTTP 503"

    def parse_meta(payload: Any, ref: Any) -> Any:
        return _mapper().parse_meta(payload, _ref("other"))

    s = _strategy(lambda r: _json(META), _mapper(parse_meta=parse_meta))
    with pytest.raises(PayloadError) as b:
        s.get_meta(_ref())
    assert _msg(b) == "mapper returned a different ref"


def test_read_messages_and_status_300() -> None:
    s = _strategy(lambda r: httpx.Response(404))
    with pytest.raises(DocumentNotFoundError) as a:
        s.read(_ref())
    assert _msg(a) == "GET /documents/1/file: not found"
    s = _strategy(lambda r: httpx.Response(300))
    with pytest.raises(FetchTransportError) as b:
        s.read(_ref())
    assert _msg(b) == "GET /documents/1/file: HTTP 300"


def test_transport_error_message() -> None:
    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("x")

    with pytest.raises(FetchTransportError) as a:
        _strategy(boom).read(_ref())
    assert _msg(a) == "GET /documents/1/file: ConnectError"


def test_too_large_declared_and_streamed() -> None:
    s = _strategy(lambda r: httpx.Response(200, content=b"x", headers={"content-length": "101"}))
    with pytest.raises(ResponseTooLargeError) as a:
        s.read(_ref())
    assert _msg(a) == "GET /documents/1/file: body larger than 100 bytes"

    def chunks() -> Any:
        yield b"x" * 60
        yield b"x" * 41

    s = _strategy(lambda r: httpx.Response(200, content=chunks()))
    with pytest.raises(ResponseTooLargeError) as b:
        s.read(_ref())
    assert _msg(b) == "GET /documents/1/file: body larger than 100 bytes"


def test_redirect_message_and_default_port() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "api.example":
            return httpx.Response(302, headers={"location": "http://api.example/x"})
        return httpx.Response(200)

    with pytest.raises(RedirectNotAllowedError) as a:
        _strategy(handler).read(_ref())
    assert _msg(a) == "redirect outside the source host or not https"


def test_mapper_supplied_invalid_id_is_payload_error() -> None:
    mapper = _mapper(parse_list=lambda payload: RestListing(external_ids=cast(Any, (5,))))
    s = _strategy(lambda r: _json({}), mapper)
    with pytest.raises(PayloadError):
        s.list_refs("src", DocumentFilter())


@pytest.mark.parametrize("url", ["https://user:pw@api.example/v1", "https://user@api.example"])
def test_base_url_userinfo_rejected(url: str) -> None:
    with pytest.raises(SourceConfigError):
        RestApiStrategy(url)


@pytest.mark.parametrize("url", ["https://", "https:///v1", "https://:443/v1"])
def test_base_url_without_host_rejected(url: str) -> None:
    with pytest.raises(SourceConfigError):
        RestApiStrategy(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.example:abc/v1",
        "https://api.example:99999/v1",
        "https://a.example/v1?x=1",
        "https://a.example/v1#f",
    ],
)
def test_base_url_bad_port_query_fragment_rejected(url: str) -> None:
    with pytest.raises(SourceConfigError):
        RestApiStrategy(url)


def test_idn_base_url_matches_punycode_host() -> None:
    s = RestApiStrategy(
        "https://bücher.example/v1",
        mappers=_registry(),
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"ok")),
    )
    assert s.read(_ref()) == b"ok"


def test_invalid_url_maps_to_transport_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.InvalidURL("bad")

    with pytest.raises(FetchTransportError):
        _strategy(handler).read(_ref())


def test_close_closes_client_and_is_idempotent() -> None:
    s = _strategy(lambda r: httpx.Response(200, content=b"x"))
    s.read(_ref())
    client = s._http
    assert client is not None
    s.read(_ref())
    assert s._http is client
    s.close()
    assert client.is_closed
    s.close()


def test_closed_strategy_does_not_rebuild_client() -> None:
    s = _strategy(lambda r: httpx.Response(200, content=b"x"))
    s.close()
    with pytest.raises(FetchTransportError, match="closed"):
        s.read(_ref())


def test_client_closed_mid_request_is_typed() -> None:
    s = _strategy(lambda r: httpx.Response(200, content=b"x"))
    client = s._client()
    client.close()
    with pytest.raises(FetchTransportError, match="closed"):
        s.read(_ref())
