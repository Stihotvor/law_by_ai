import json
import re
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from agents.fetch.contracts import DocumentFilter, DocumentRef
from agents.fetch.errors import InvalidReferenceError
from agents.fetch.registry import Registry
from agents.fetch.sources.sejm_eli import (
    _ID_PATTERN,
    _WARSAW,
    MAPPER,
    _list_params,
    _parse_list,
    _parse_meta,
)
from agents.fetch.strategies.rest_api import REST_MAPPERS, RestApiStrategy, RestMapper

BASE = "https://api.sejm.gov.pl/eli"


def _ref(eid: str = "DU/2024/12") -> DocumentRef:
    return DocumentRef(source="sejm_eli", external_id=eid, url=f"{BASE}/acts/{eid}/text.html")


def test_default_params() -> None:
    assert _list_params(DocumentFilter(limit=7)) == {
        "publisher": "DU",
        "limit": "7",
        "offset": "0",
        "sortBy": "change",
        "sortDir": "desc",
    }


def test_full_filter_params() -> None:
    flt = DocumentFilter(
        date_from=datetime(2024, 1, 31, 23, 30, tzinfo=UTC),
        date_to=datetime(2024, 6, 1, 12, 0, tzinfo=UTC),
        doc_type="Ustawa",
        keyword="kodeks pracy",
        cursor="40",
    )
    params = _list_params(flt)
    assert params["pubDateFrom"] == "2024-01-31"
    assert params["pubDateTo"] == "2024-06-01"
    assert params["type"] == "Ustawa"
    assert params["title"] == "kodeks pracy"
    assert params["offset"] == "40"
    assert len(params) == 9


def test_warsaw_date_from_other_zone() -> None:
    flt = DocumentFilter(
        date_from=datetime(2024, 3, 1, 0, 30, tzinfo=timezone(timedelta(hours=-5)))
    )
    assert _list_params(flt)["pubDateFrom"] == "2024-02-29"
    flt = DocumentFilter(date_from=datetime(2024, 3, 1, 0, 30, tzinfo=timezone(timedelta(hours=5))))
    assert _list_params(flt)["pubDateFrom"] == "2024-02-28"


@pytest.mark.parametrize("cursor", ["abc", "-1", "1e3", "9999999999", ""])
def test_bad_cursor(cursor: str) -> None:
    with pytest.raises(InvalidReferenceError):
        _list_params(DocumentFilter(cursor=cursor))


@pytest.mark.parametrize("field", ["keyword", "doc_type"])
@pytest.mark.parametrize("value", ["x" * 201, "a\nb", "a\x7fb"])
def test_bad_text_filter(field: str, value: str) -> None:
    with pytest.raises(InvalidReferenceError):
        _list_params(DocumentFilter(**{field: value}))


@pytest.mark.parametrize("field", ["keyword", "doc_type"])
def test_text_filter_boundary(field: str) -> None:
    flt = DocumentFilter(**{field: "x" * 200})
    assert "x" * 200 in _list_params(flt).values()


def _items(*ids: str) -> list[dict[str, Any]]:
    return [{"ELI": i, "title": "t"} for i in ids]


def test_parse_list_first_page() -> None:
    page = {"items": _items("DU/2024/1", "DU/2024/2"), "offset": 0, "totalCount": 5}
    got = _parse_list(page)
    assert got.external_ids == ("DU/2024/1", "DU/2024/2")
    assert got.next_cursor == "2"


def test_parse_list_last_page_and_empty() -> None:
    last = {"items": _items("DU/2024/1", "DU/2024/2"), "offset": 3, "totalCount": 5}
    assert _parse_list(last).next_cursor is None
    assert _parse_list({"items": [], "offset": 0, "totalCount": 9}).next_cursor is None


def test_parse_list_string_numbers() -> None:
    page = {"items": _items("DU/2024/1"), "offset": "1", "totalCount": "9"}
    assert _parse_list(page).next_cursor == "2"


@pytest.mark.parametrize("missing", ["items", "offset", "totalCount"])
def test_parse_list_missing_key(missing: str) -> None:
    page: dict[str, Any] = {"items": _items("DU/2024/1"), "offset": 0, "totalCount": 5}
    del page[missing]
    with pytest.raises(KeyError):
        _parse_list(page)


def test_parse_list_missing_eli() -> None:
    with pytest.raises(KeyError):
        _parse_list({"items": [{"title": "t"}], "offset": 0, "totalCount": 1})


def _act(**over: Any) -> dict[str, Any]:
    act: dict[str, Any] = {
        "ELI": "DU/2024/12",
        "address": "WDU20240000012",
        "displayAddress": "Dz.U. 2024 poz. 12",
        "title": "  Obwieszczenie  ",
        "type": "Obwieszczenie",
        "status": "obowiązujący",
        "inForce": "IN_FORCE",
        "announcementDate": "2023-11-01",
        "promulgation": "2023-12-07",
        "changeDate": "2026-03-31T13:20:23",
        "textHTML": True,
        "textPDF": True,
    }
    act.update(over)
    return act


def test_parse_meta_fields() -> None:
    meta = _parse_meta(_act(), _ref())
    assert meta.ref == _ref()
    assert meta.title == "Obwieszczenie"
    assert meta.doc_type == "Obwieszczenie"
    assert meta.language == "pl"
    assert meta.published_at == datetime(2023, 12, 7, tzinfo=_WARSAW)
    assert meta.published_at is not None
    assert meta.published_at.utcoffset() == timedelta(hours=1)
    assert meta.extra == {
        "eli": "DU/2024/12",
        "address": "WDU20240000012",
        "display_address": "Dz.U. 2024 poz. 12",
        "status": "obowiązujący",
        "in_force": "IN_FORCE",
        "change_date": "2026-03-31T13:20:23",
        "text_html": True,
        "text_pdf": True,
        "content_type": "text/html",
    }


def test_parse_meta_missing_date_and_optional_keys() -> None:
    payload = _act()
    for key in ("promulgation", "address", "textHTML", "textPDF"):
        del payload[key]
    meta = _parse_meta(payload, _ref())
    assert meta.published_at is None
    assert meta.extra["address"] is None
    assert meta.extra["content_type"] is None
    assert _parse_meta(_act(promulgation=""), _ref()).published_at is None


def test_parse_meta_eli_mismatch() -> None:
    with pytest.raises(ValueError, match="ELI"):
        _parse_meta(_act(ELI="DU/2024/13"), _ref())


@pytest.mark.parametrize(
    ("html", "pdf", "expected"),
    [
        (True, True, "text/html"),
        (True, False, "text/html"),
        (False, True, "application/pdf"),
        (False, False, None),
        ("yes", 1, None),
        (1, "true", None),
    ],
)
def test_content_type(html: Any, pdf: Any, expected: str | None) -> None:
    meta = _parse_meta(_act(textHTML=html, textPDF=pdf), _ref())
    assert meta.extra["content_type"] == expected
    assert meta.extra["text_html"] is (html is True)
    assert meta.extra["text_pdf"] is (pdf is True)


def test_registration_and_pattern() -> None:
    assert REST_MAPPERS.get("sejm_eli") is MAPPER
    assert MAPPER.id_safe == "/"
    assert MAPPER.id_pattern == _ID_PATTERN
    for ok in ("DU/2024/12", "MP/2023/9"):
        assert re.fullmatch(_ID_PATTERN, ok)
    for bad in ("DU/24/1", "du/2024/1", "DU/2024/1/x", "../x", "DU/2024/", "D/2024/1"):
        assert not re.fullmatch(_ID_PATTERN, bad)


def test_end_to_end_requests() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/search"):
            body = {"items": _items("DU/2024/12"), "offset": 0, "totalCount": 1}
            return httpx.Response(200, content=json.dumps(body))
        if request.url.path.endswith("text.html"):
            return httpx.Response(200, content=b"<p>x</p>")
        return httpx.Response(200, content=json.dumps(_act()))

    mappers: Registry[RestMapper] = Registry("test_mappers")
    mappers.register("sejm_eli")(MAPPER)
    strategy = RestApiStrategy(BASE, mappers=mappers, transport=httpx.MockTransport(handler))
    page = strategy.list_refs("sejm_eli", DocumentFilter(limit=3, keyword="k"))
    ref = page.items[0]
    assert ref.url == f"{BASE}/acts/DU/2024/12/text.html"
    meta = strategy.get_meta(ref)
    assert strategy.read(ref) == b"<p>x</p>"
    assert meta.title == "Obwieszczenie"
    assert [(r.method, r.url.raw_path.decode()) for r in seen[1:]] == [
        ("GET", "/eli/acts/DU/2024/12"),
        ("GET", "/eli/acts/DU/2024/12/text.html"),
    ]
    first = seen[0]
    assert (first.method, first.url.path) == ("GET", "/eli/acts/search")
    assert dict(first.url.params) == {
        "publisher": "DU",
        "limit": "3",
        "offset": "0",
        "sortBy": "change",
        "sortDir": "desc",
        "title": "k",
    }
