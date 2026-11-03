"""Sejm ELI source: statutes of the Dziennik Ustaw from the Sejm ELI API.

The list uses ``/acts/search`` and not ``/acts/{publisher}/{year}``. The year
list is about 1 MB per call, has no filters, and ignores ``limit`` and
``offset``, so client-side paging would download 1 MB again for every page. The
search endpoint pushes filters and paging to the server.

The mapper returns ids only, so an in-memory filter would need one metadata
request per act. Every ``DocumentFilter`` field is therefore mapped to a query
param.

Rate-limit politeness: no limit is documented. One request at a time per call,
a process-wide minimum gap of ``SEJM_MIN_INTERVAL`` seconds before every
outbound request, no retries, no parallel fan-out. A fetch costs two requests
(meta, content). Status 429 or 5xx surfaces as ``FetchTransportError`` with the
status code. ``Retry-After`` is not honoured.

The live API filters ``pubDateFrom`` (exclusive) and ``pubDateTo`` (inclusive) by
the promulgation date, so the source sends the day before ``date_from`` and
reports ``promulgation`` as ``published_at``. Only the main text (text.html or
text.pdf) is fetched, not consolidated texts or attachments.
"""

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from agents.fetch.contracts import (
    DocumentFilter,
    DocumentMeta,
    DocumentPage,
    DocumentRef,
    FetchedDocument,
)
from agents.fetch.errors import DocumentNotFoundError, InvalidReferenceError
from agents.fetch.sources._throttle import Throttle
from agents.fetch.sources.base import SOURCES, LegalSource
from agents.fetch.strategies.rest_api import (
    REST_MAPPERS,
    RestListing,
    RestMapper,
    with_content_variant,
)
from config.settings import get_settings

_BASE = "https://api.sejm.gov.pl/eli"
_PUBLISHER = "DU"  # Dziennik Ustaw (statutes)
_ID_PATTERN = r"[A-Z]{2,10}/[0-9]{4}/[0-9]{1,6}"
_WARSAW = ZoneInfo("Europe/Warsaw")
_THROTTLE = Throttle(lambda: get_settings().sejm_min_interval)
_CURSOR = re.compile(r"[0-9]{1,9}")
_MAX_TEXT = 200


def _warsaw_day(value: datetime) -> str:
    return value.astimezone(_WARSAW).strftime("%Y-%m-%d")


def _day_before(value: datetime) -> str:
    day = value.astimezone(_WARSAW).date() - timedelta(days=1)
    return day.isoformat()


def _text_param(value: str) -> str:
    if len(value) > _MAX_TEXT or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise InvalidReferenceError("invalid filter value")
    return value


def _offset(cursor: str | None) -> str:
    if cursor is None:
        return "0"
    if not _CURSOR.fullmatch(cursor):
        raise InvalidReferenceError("invalid cursor")
    return cursor


def _list_params(flt: DocumentFilter) -> dict[str, str]:
    params = {
        "publisher": _PUBLISHER,
        "sortBy": "change",
        "sortDir": "desc",
        "limit": str(flt.limit),
        "offset": _offset(flt.cursor),
    }
    if flt.date_from is not None:
        params["pubDateFrom"] = _day_before(flt.date_from)
    if flt.date_to is not None:
        params["pubDateTo"] = _warsaw_day(flt.date_to)
    if flt.doc_type is not None:
        params["type"] = _text_param(flt.doc_type)
    if flt.keyword is not None:
        params["title"] = _text_param(flt.keyword)
    return params


def _parse_list(payload: Any) -> RestListing:
    items = payload["items"]
    ids = tuple(item["ELI"] for item in items)
    nxt = int(payload["offset"]) + len(items)
    more = bool(items) and nxt < int(payload["totalCount"])
    return RestListing(ids, str(nxt) if more else None)


def _content_type(payload: Any) -> str | None:
    if payload.get("textHTML") is True:
        return "text/html"
    if payload.get("textPDF") is True:
        return "application/pdf"
    return None


def _published(payload: Any) -> datetime | None:
    day = payload.get("promulgation")
    if not day:
        return None
    return datetime.fromisoformat(day).replace(tzinfo=_WARSAW)


def _parse_meta(payload: Any, ref: DocumentRef) -> DocumentMeta:
    if payload["ELI"] != ref.external_id:
        raise ValueError("ELI does not match the reference")
    return DocumentMeta(
        ref=ref,
        title=payload["title"].strip(),
        doc_type=payload["type"],
        published_at=_published(payload),
        language="pl",
        extra={
            "eli": payload["ELI"],
            "address": payload.get("address"),
            "display_address": payload.get("displayAddress"),
            "status": payload.get("status"),
            "in_force": payload.get("inForce"),
            "change_date": payload.get("changeDate"),
            "text_html": payload.get("textHTML") is True,
            "text_pdf": payload.get("textPDF") is True,
            "content_type": _content_type(payload),
        },
    )


MAPPER = RestMapper(
    list_path="/acts/search",
    meta_path="/acts/{external_id}",
    content_path="/acts/{external_id}/text.html",
    alt_content_paths={"pdf": "/acts/{external_id}/text.pdf"},
    id_safe="/",
    id_pattern=_ID_PATTERN,
    list_params=_list_params,
    parse_list=_parse_list,
    parse_meta=_parse_meta,
)
REST_MAPPERS.register("sejm_eli")(MAPPER)


@SOURCES.register("sejm_eli")
class SejmEliSource(LegalSource):
    name = "sejm_eli"
    base_url = _BASE
    strategy_name = "rest_api"

    def list_documents(self, flt: DocumentFilter) -> DocumentPage:
        _THROTTLE.wait()
        return self.strategy.list_refs(self.name, flt)

    def get_document_meta(self, ref: DocumentRef) -> DocumentMeta:
        _THROTTLE.wait()
        return self.strategy.get_meta(ref)

    def fetch_document(self, ref: DocumentRef) -> FetchedDocument:
        _THROTTLE.wait()
        meta = self.strategy.get_meta(ref)
        read_ref = ref
        if meta.extra.get("text_html") is not True:
            if meta.extra.get("text_pdf") is not True:
                raise DocumentNotFoundError("act has no text")
            read_ref = with_content_variant(self.base_url, MAPPER, ref, "pdf")
        _THROTTLE.wait()
        content = self.strategy.read(read_ref)
        return FetchedDocument(
            meta=meta,
            content=content,
            content_type=meta.extra.get("content_type"),
            fetched_at=datetime.now(UTC),
        )
