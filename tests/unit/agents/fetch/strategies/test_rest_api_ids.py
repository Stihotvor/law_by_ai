from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx
import pytest

from agents.fetch.contracts import DocumentFilter, DocumentMeta, DocumentRef
from agents.fetch.errors import InvalidReferenceError, PayloadError, SourceConfigError
from agents.fetch.registry import Registry
from agents.fetch.strategies.rest_api import (
    RestApiStrategy,
    RestListing,
    RestMapper,
    with_content_variant,
)

BASE = "https://api.example/v1"
pytestmark = pytest.mark.usefixtures("settings_env")


def _meta(payload: Any, ref: DocumentRef) -> DocumentMeta:
    return DocumentMeta(ref=ref, title="t", published_at=datetime(2024, 1, 1).astimezone())


def _mapper(**over: Any) -> RestMapper:
    args: dict[str, Any] = {
        "list_path": "/acts",
        "meta_path": "/acts/{external_id}",
        "content_path": "/acts/{external_id}/text.html",
        "list_params": lambda flt: {},
        "parse_list": lambda p: RestListing(tuple(p["ids"])),
        "parse_meta": _meta,
    }
    args.update(over)
    return RestMapper(**args)


def _strategy(mapper: RestMapper, handler: Callable[[httpx.Request], httpx.Response]):
    reg: Registry[RestMapper] = Registry("t")
    reg.register("s")(mapper)
    return RestApiStrategy(BASE, mappers=reg, transport=httpx.MockTransport(handler))


def _ref(eid: str = "DU/2024/12", url: str = BASE + "/x") -> DocumentRef:
    return DocumentRef(source="s", external_id=eid, url=url)


def _ok(seen: list[str]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.raw_path.decode())
        return httpx.Response(200, content=b"ok")

    return handler


def test_id_safe_slash_keeps_slashes() -> None:
    seen: list[str] = []
    _strategy(_mapper(id_safe="/"), _ok(seen)).read(_ref())
    assert seen == ["/v1/acts/DU/2024/12/text.html"]


def test_default_id_safe_encodes_slashes() -> None:
    seen: list[str] = []
    _strategy(_mapper(), _ok(seen)).read(_ref())
    assert seen == ["/v1/acts/DU%2F2024%2F12/text.html"]


@pytest.mark.parametrize("bad", ["DU//1", "DU/../1", "./x", "a\\b", "/a", "a/"])
def test_slash_mode_rejects_unsafe_ids(bad: str) -> None:
    seen: list[str] = []
    with pytest.raises(InvalidReferenceError):
        _strategy(_mapper(id_safe="/"), _ok(seen)).read(_ref(bad))
    assert seen == []


def test_encoded_dots_stay_encoded() -> None:
    seen: list[str] = []
    _strategy(_mapper(id_safe="/"), _ok(seen)).read(_ref("DU/%2e%2e/1"))
    assert seen == ["/v1/acts/DU/%252e%252e/1/text.html"]


def test_id_pattern_allow_list() -> None:
    seen: list[str] = []
    strat = _strategy(_mapper(id_safe="/", id_pattern=r"DU/\d+/\d+"), _ok(seen))
    strat.read(_ref())
    with pytest.raises(InvalidReferenceError) as err:
        strat.read(_ref("DU/2024/12?x=1"))
    assert "DU/2024" not in str(err.value)
    assert len(seen) == 1


def test_list_refs_bad_server_id_is_payload_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ids": ["DU/1/1", "evil"]})

    mapper = _mapper(id_safe="/", id_pattern=r"DU/\d+/\d+")
    with pytest.raises(PayloadError, match="invalid id"):
        _strategy(mapper, handler).list_refs("s", DocumentFilter())


def test_mapper_validation() -> None:
    with pytest.raises(SourceConfigError):
        _mapper(id_safe="x")
    with pytest.raises(SourceConfigError):
        _mapper(id_pattern="(")
    with pytest.raises(SourceConfigError):
        _mapper(alt_content_paths={"pdf": "/no-placeholder"})
    mapper = _mapper()
    assert (mapper.id_safe, mapper.id_pattern, dict(mapper.alt_content_paths)) == ("", None, {})


def test_alt_url_reads_alt_path_and_foreign_url_reads_default() -> None:
    seen: list[str] = []
    mapper = _mapper(id_safe="/", alt_content_paths={"pdf": "/acts/{external_id}/text.pdf"})
    strat = _strategy(mapper, _ok(seen))
    strat.read(with_content_variant(BASE, mapper, _ref(), "pdf"))
    strat.read(_ref(url="https://evil.example/x"))
    strat.read(_ref(url=BASE + "/acts/other/text.pdf"))
    assert seen == [
        "/v1/acts/DU/2024/12/text.pdf",
        "/v1/acts/DU/2024/12/text.html",
        "/v1/acts/DU/2024/12/text.html",
    ]


def test_with_content_variant() -> None:
    mapper = _mapper(id_safe="/", alt_content_paths={"pdf": "/acts/{external_id}/text.pdf"})
    out = with_content_variant(BASE + "/", mapper, _ref(), "pdf")
    assert out.url == BASE + "/acts/DU/2024/12/text.pdf"
    assert out.external_id == "DU/2024/12"
    with pytest.raises(SourceConfigError):
        with_content_variant(BASE, mapper, _ref(), "docx")
