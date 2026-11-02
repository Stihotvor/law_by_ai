"""Tavily based fetch strategy for sites without an API.

The strategy discovers pages with Tavily ``map`` and reads one page with Tavily
``extract``. It does not call ``crawl``. The agent builds a fresh strategy for
every call, so a crawl result cannot be cached between ``list_refs`` and
``read``. ``crawl`` would pay for page content in the list step and again in the
read step. ``map`` (URLs only, 1 credit per 10 pages) plus ``extract`` (1 credit
per 5 pages, only for pages that are read) costs less. The name keeps the
"Tavily crawl" wording of the design.

Every ``list_refs`` call runs ``map`` again and costs credits, also for later
pages of the same listing. ``TAVILY_MAX_PAGES`` caps what one call can see.

``read`` returns Tavily's plain text extraction of a web page. It is not the
original bytes of the page.
"""

import re
from typing import Any
from urllib.parse import unquote, urlsplit

import requests
from tavily import TavilyClient
from tavily.errors import (
    BadRequestError,
    ForbiddenError,
    InvalidAPIKeyError,
    UsageLimitExceededError,
)
from tavily.errors import TimeoutError as TavilyTimeoutError

from agents.fetch.contracts import DocumentFilter, DocumentMeta, DocumentPage, DocumentRef
from agents.fetch.errors import (
    DocumentNotFoundError,
    FetchError,
    FetchTransportError,
    InvalidReferenceError,
    PayloadError,
    ResponseTooLargeError,
    SourceConfigError,
)
from agents.fetch.strategies.base import STRATEGIES
from config.settings import get_settings

_HTTPS_PORT = 443
_MAP_DEPTH = 2
_MAP_BREADTH = 20
_MAP_TIMEOUT = (10.0, 150.0)
_EXTRACT_TIMEOUT = (1.0, 60.0)
_CURSOR = re.compile(r"[0-9]{1,9}")
_STATUS_ERRORS: tuple[tuple[type[Exception], int], ...] = (
    (UsageLimitExceededError, 429),
    (ForbiddenError, 403),
    (BadRequestError, 400),
)


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    return max(bounds[0], min(bounds[1], value))


def _translate(exc: Exception) -> FetchError:
    """Map an SDK or requests error to a fetch error. Never echo ``str(exc)``."""
    if isinstance(exc, FetchError):
        return exc
    name = type(exc).__name__
    if isinstance(exc, InvalidAPIKeyError):
        return SourceConfigError("Tavily rejected the API key")
    for kind, status in _STATUS_ERRORS:
        if isinstance(exc, kind):
            return FetchTransportError(f"tavily: {name} (HTTP {status})", status_code=status)
    return FetchTransportError(f"tavily: {name}")


def _bad_id(external_id: str) -> bool:
    segments = external_id.split("/")
    return (
        not external_id
        or external_id.startswith("/")
        or any(seg in {"", ".", ".."} for seg in segments)
        or any(c in external_id for c in ("\\", "#"))
        or "://" in external_id
    )


def _check_id(external_id: str) -> None:
    if _bad_id(external_id) or any(ord(c) < 32 or ord(c) == 127 for c in external_id):
        raise InvalidReferenceError("unsafe external_id")


@STRATEGIES.register("tavily")
class TavilyCrawlStrategy:
    def __init__(self, base_url: str, *, client: TavilyClient | None = None) -> None:
        if not base_url.startswith("https://"):
            raise SourceConfigError("base_url must start with https://")
        self._base = base_url.rstrip("/")
        parts = urlsplit(self._base)
        if parts.username is not None or parts.password is not None or "@" in parts.netloc:
            raise SourceConfigError("base_url must not contain credentials")
        if not parts.hostname:
            raise SourceConfigError("base_url needs a host")
        self._host = parts.hostname
        self._port = parts.port or _HTTPS_PORT
        self._path = parts.path
        self._client = client
        if client is None and not get_settings().tavily_api_key:
            raise SourceConfigError("Tavily API key is not set")

    def _open(self) -> tuple[TavilyClient, bool]:
        if self._client is not None:
            return self._client, False
        client = TavilyClient(api_key=get_settings().tavily_api_key)
        client.session.trust_env = False
        return client, True

    def list_refs(self, source: str, flt: DocumentFilter) -> DocumentPage:
        offset = self._offset(flt.cursor)
        body = self._call(
            "map",
            url=self._base,
            max_depth=_MAP_DEPTH,
            max_breadth=_MAP_BREADTH,
            limit=get_settings().tavily_max_pages,
            allow_external=False,
            select_domains=["^" + re.escape(self._host) + "$"],
            timeout=_clamp(get_settings().tavily_timeout, _MAP_TIMEOUT),
        )
        ids = self._ids(body)
        if flt.keyword:
            needle = flt.keyword.lower()
            ids = [i for i in ids if needle in i.lower()]
        page = ids[offset : offset + flt.limit]
        more = offset + flt.limit < len(ids)
        refs = tuple(
            DocumentRef(source=source, external_id=i, url=f"{self._base}/{i}") for i in page
        )
        return DocumentPage(items=refs, next_cursor=str(offset + flt.limit) if more else None)

    def get_meta(self, ref: DocumentRef) -> DocumentMeta:
        _check_id(ref.external_id)
        segments = [s for s in ref.external_id.split("?")[0].split("/") if s]
        title = unquote(segments[-1]) if segments else ref.external_id
        return DocumentMeta(
            ref=ref,
            title=title or ref.external_id,
            doc_type=None,
            published_at=None,
            language=None,
            extra={"content_type": "text/plain; charset=utf-8"},
        )

    def read(self, ref: DocumentRef) -> bytes:
        _check_id(ref.external_id)
        url = f"{self._base}/{ref.external_id}"
        body = self._call(
            "extract",
            urls=url,
            extract_depth="basic",
            format="text",
            timeout=_clamp(get_settings().tavily_timeout, _EXTRACT_TIMEOUT),
        )
        data = self._content(body)
        if len(data) > get_settings().fetch_max_bytes:
            raise ResponseTooLargeError("extracted text is larger than the size limit")
        return data

    @staticmethod
    def _offset(cursor: str | None) -> int:
        if cursor is None:
            return 0
        if not _CURSOR.fullmatch(cursor):
            raise InvalidReferenceError("invalid cursor")
        return int(cursor)

    def _call(self, method: str, **kwargs: Any) -> Any:
        client, owned = self._open()
        try:
            return getattr(client, method)(**kwargs)
        except (
            FetchError,
            InvalidAPIKeyError,
            UsageLimitExceededError,
            ForbiddenError,
            BadRequestError,
            TavilyTimeoutError,
            requests.exceptions.RequestException,
        ) as exc:
            raise _translate(exc) from exc
        finally:
            if owned:
                client.close()

    def _ids(self, body: Any) -> list[str]:
        if not isinstance(body, dict) or not isinstance(body.get("results"), list):
            raise PayloadError("tavily map: unexpected response")
        found: set[str] = set()
        for item in body["results"]:
            eid = self._relative(item) if isinstance(item, str) else None
            if eid is not None:
                found.add(eid)
        return sorted(found)

    def _relative(self, url: str) -> str | None:
        if any(ord(c) < 32 or ord(c) == 127 for c in url):
            return None
        try:
            parts = urlsplit(url)
            port = parts.port or _HTTPS_PORT
        except ValueError:
            return None
        if (
            parts.scheme != "https"
            or parts.hostname != self._host
            or port != self._port
            or parts.fragment
            or "@" in parts.netloc
            or not url.startswith(self._base + "/")
            or not parts.path.startswith(self._path + "/")
        ):
            return None
        eid = url[len(self._base) + 1 :]
        return None if _bad_id(eid) else eid

    @staticmethod
    def _content(body: Any) -> bytes:
        if not isinstance(body, dict):
            raise PayloadError("tavily extract: unexpected response")
        results = body.get("results")
        if not isinstance(results, list):
            raise PayloadError("tavily extract: unexpected response")
        if not results:
            if body.get("failed_results"):
                raise FetchTransportError("tavily extract failed")
            raise DocumentNotFoundError("tavily extract: no content")
        first = results[0]
        text = first.get("raw_content") if len(results) == 1 and isinstance(first, dict) else None
        if not isinstance(text, str) or not text:
            raise PayloadError("tavily extract: unexpected result")
        return text.encode("utf-8")
