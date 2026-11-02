from collections.abc import Callable
from datetime import datetime
from typing import Any

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
