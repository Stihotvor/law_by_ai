from typing import Any

import httpx
import pytest

from agents.fetch.contracts import DocumentFilter
from agents.fetch.errors import (
    DocumentNotFoundError,
    FetchTransportError,
    InvalidReferenceError,
    PayloadError,
    RedirectNotAllowedError,
    ResponseTooLargeError,
    SourceConfigError,
)
from agents.fetch.strategies.rest_api import RestApiStrategy

from .test_rest_api import (
    META,
    _json,
    _mapper,
    _ref,
    _registry,
    _strategy,
)

pytestmark = pytest.mark.usefixtures("settings_env")


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
