from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest

from agents.fetch.contracts import DocumentFilter, DocumentMeta, DocumentRef
from agents.fetch.errors import (
    FetchTransportError,
    InvalidReferenceError,
    PayloadError,
    ResponseTooLargeError,
    SourceConfigError,
)
from agents.fetch.registry import Registry
from agents.fetch.strategies._rest_mapper import build_path, call_mapper
from agents.fetch.strategies.rest_api import (
    RestApiStrategy,
    RestListing,
    RestMapper,
    with_content_variant,
)

BASE = "https://api.example/v1"
pytestmark = pytest.mark.usefixtures("settings_env")


def _mapper(**over: Any) -> RestMapper:
    args: dict[str, Any] = {
        "list_path": "/acts",
        "meta_path": "/acts/{external_id}",
        "content_path": "/acts/{external_id}/text",
        "list_params": lambda flt: {},
        "parse_list": lambda p: RestListing(tuple(p["ids"])),
        "parse_meta": lambda p, ref: DocumentMeta(ref=ref, title="t"),
    }
    args.update(over)
    return RestMapper(**args)


def _strategy(mapper: RestMapper, handler: Any) -> RestApiStrategy:
    reg: Registry[RestMapper] = Registry("t")
    reg.register("s")(mapper)
    return RestApiStrategy(BASE, mappers=reg, transport=httpx.MockTransport(handler))


def _ref(eid: str = "1") -> DocumentRef:
    return DocumentRef(source="s", external_id=eid, url=BASE + "/x")


def _json(body: str) -> httpx.Response:
    return httpx.Response(200, content=body.encode())


def test_new_strategy_is_open() -> None:
    assert _strategy(_mapper(), lambda r: _json("{}"))._closed is False


def test_invalid_id_message_for_unsafe_id() -> None:
    strategy = _strategy(_mapper(), lambda r: _json('{"ids": [".."]}'))
    with pytest.raises(PayloadError) as err:
        strategy.list_refs("s", DocumentFilter())
    assert str(err.value) == "mapper returned an invalid id"


def test_invalid_id_message_names_the_error_type() -> None:
    strategy = _strategy(_mapper(), lambda r: _json('{"ids": [5]}'))
    with pytest.raises(PayloadError) as err:
        strategy.list_refs("s", DocumentFilter())
    assert str(err.value) == "mapper returned an invalid id: TypeError"


def test_meta_invalid_json_message_carries_the_label() -> None:
    strategy = _strategy(_mapper(), lambda r: _json("not json"))
    with pytest.raises(PayloadError) as err:
        strategy.get_meta(_ref())
    assert str(err.value) == "GET /acts/1: invalid JSON"


def test_closed_message_for_closed_client_and_for_runtime_error() -> None:
    strategy = _strategy(_mapper(), lambda r: _json("{}"))
    strategy.close()
    with pytest.raises(FetchTransportError) as err:
        strategy.read(_ref())
    assert str(err.value) == "closed"

    def boom(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("client closed")

    with pytest.raises(FetchTransportError) as err2:
        _strategy(_mapper(), boom).read(_ref())
    assert str(err2.value) == "closed"


def test_request_method_is_upper_case_get(monkeypatch: pytest.MonkeyPatch) -> None:
    methods: list[str] = []
    original = httpx.Client.stream

    def spy(self: httpx.Client, method: str, *args: Any, **kwargs: Any) -> Any:
        methods.append(method)
        return original(self, method, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "stream", spy)
    _strategy(_mapper(), lambda r: _json("x")).read(_ref())
    assert methods == ["GET"]


def test_content_length_header_is_read_in_lower_case() -> None:
    response = SimpleNamespace(
        status_code=200, headers={"content-length": "101"}, iter_bytes=lambda: iter([b""])
    )
    with pytest.raises(ResponseTooLargeError):
        RestApiStrategy._consume(cast(Any, response), "L", 100, 1e18)


def test_a_chunk_read_exactly_at_the_deadline_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = SimpleNamespace(status_code=200, headers={}, iter_bytes=lambda: iter([b"x"]))
    monkeypatch.setattr("agents.fetch.strategies.rest_api._monotonic", lambda: 5.0)
    assert RestApiStrategy._consume(cast(Any, response), "L", 100, 5.0) == b"x"


def test_mapper_config_messages() -> None:
    with pytest.raises(SourceConfigError) as a:
        _mapper(id_safe="x")
    assert str(a.value) == "id_safe must be '' or '/'"
    with pytest.raises(SourceConfigError) as b:
        _mapper(id_pattern="(")
    assert str(b.value) == "id_pattern is not a valid regex"


def test_unsafe_id_messages() -> None:
    for mapper, eid in [
        (_mapper(id_safe="/"), "a//b"),
        (_mapper(id_pattern=r"\d+"), "abc"),
    ]:
        with pytest.raises(InvalidReferenceError) as err:
            build_path("/x/{external_id}", eid, mapper)
        assert str(err.value) == "unsafe external_id"


def test_content_variant_message_and_trailing_slash() -> None:
    mapper = _mapper(alt_content_paths={"pdf": "/acts/{external_id}/t.pdf"})
    with pytest.raises(SourceConfigError) as err:
        with_content_variant(BASE, mapper, _ref(), "doc")
    assert str(err.value) == "unknown content variant 'doc'"
    assert with_content_variant(BASE + "/", mapper, _ref(), "pdf").url == BASE + "/acts/1/t.pdf"
    assert with_content_variant(BASE + "//", mapper, _ref(), "pdf").url == BASE + "/acts/1/t.pdf"


def test_call_mapper_forwards_keyword_arguments() -> None:
    def fn(a: int, *, b: int) -> int:
        return a - b

    assert call_mapper(fn, 5, b=2) == 3
