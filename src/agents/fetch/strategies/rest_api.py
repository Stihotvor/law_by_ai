"""REST API fetch strategy.

The strategy owns URL building, the GET request, timeout, redirect guard, size
cap, JSON decode, error mapping and building ``DocumentRef``. A ``RestMapper``
registered in ``REST_MAPPERS`` under the SAME name as the source owns paths,
query params and the JSON-to-contract conversion. The mapper is pure.

Content type convention: the transport MIME type is not part of the ``read``
return value. ``parse_meta`` puts it in ``DocumentMeta.extra["content_type"]``
when the API payload gives it. A source copies ``meta.extra.get("content_type")``
into ``FetchedDocument.content_type``.
"""

import json
import threading
import time
from collections.abc import Mapping
from typing import Any

import httpx

from agents.fetch.contracts import DocumentFilter, DocumentMeta, DocumentPage, DocumentRef
from agents.fetch.errors import (
    DocumentNotFoundError,
    FetchTransportError,
    InvalidReferenceError,
    PayloadError,
    RedirectNotAllowedError,
    ResponseTooLargeError,
    SourceConfigError,
)
from agents.fetch.registry import Registry, UnknownNameError
from agents.fetch.strategies._hosts import check_public_host, parse_base_url
from agents.fetch.strategies._rest_mapper import (
    REST_MAPPERS,
    RestListing,
    RestMapper,
    _build_path,
    _call,
    with_content_variant,
)
from agents.fetch.strategies.base import STRATEGIES
from config.settings import get_settings

__all__ = ["REST_MAPPERS", "RestApiStrategy", "RestListing", "RestMapper", "with_content_variant"]

_HTTPS_PORT = 443
_monotonic = time.monotonic  # patchable clock for deadline tests


@STRATEGIES.register("rest_api")
class RestApiStrategy:
    def __init__(
        self,
        base_url: str,
        *,
        mappers: Registry[RestMapper] | None = None,
        transport: httpx.BaseTransport | None = None,
        allow_private_hosts: bool = False,
    ) -> None:
        parts = parse_base_url(base_url)
        self._base = base_url.rstrip("/")
        self._allow_private = allow_private_hosts
        self._host = httpx.URL(self._base).host
        self._port = parts.port or _HTTPS_PORT
        self._mappers = REST_MAPPERS if mappers is None else mappers
        self._transport = transport
        self._http: httpx.Client | None = None
        self._lock = threading.Lock()
        self._closed = False

    def close(self) -> None:
        with self._lock:
            self._closed = True
            client, self._http = self._http, None
        if client is not None:
            client.close()

    def list_refs(self, source: str, flt: DocumentFilter) -> DocumentPage:
        mapper = self._mapper(source)
        params = _call(mapper.list_params, flt)
        body = self._get_json("GET " + mapper.list_path, mapper.list_path, params)
        listing = _call(mapper.parse_list, body)
        if len(listing.external_ids) > flt.limit:
            raise PayloadError("mapper returned more ids than limit")
        try:
            refs = tuple(
                DocumentRef(
                    source=source,
                    external_id=eid,
                    url=self._base + self._path(mapper.content_path, eid, mapper),
                )
                for eid in listing.external_ids
            )
            return DocumentPage(items=refs, next_cursor=listing.next_cursor)
        except InvalidReferenceError as exc:
            raise PayloadError("mapper returned an invalid id") from exc
        except (ValueError, TypeError) as exc:
            raise PayloadError(f"mapper returned an invalid id: {type(exc).__name__}") from exc

    def get_meta(self, ref: DocumentRef) -> DocumentMeta:
        mapper = self._mapper(ref.source)
        path = self._path(mapper.meta_path, ref.external_id, mapper)
        body = self._get_json("GET " + path, path, None)
        meta = _call(mapper.parse_meta, body, ref)
        if meta.ref != ref:
            raise PayloadError("mapper returned a different ref")
        return meta

    def read(self, ref: DocumentRef) -> bytes:
        mapper = self._mapper(ref.source)
        path = self._path(mapper.content_path, ref.external_id, mapper)
        for template in mapper.alt_content_paths.values():
            alt = self._path(template, ref.external_id, mapper)
            if ref.url == self._base + alt:
                path = alt
                break
        return self._get_bytes(path, None)

    def _mapper(self, source: str) -> RestMapper:
        try:
            return self._mappers.get(source)
        except UnknownNameError:
            raise SourceConfigError(f"no REST mapper for source {source!r}") from None

    @staticmethod
    def _path(template: str, external_id: str, mapper: RestMapper) -> str:
        return _build_path(template, external_id, mapper)

    def _guard(self, request: httpx.Request) -> None:
        url = request.url
        check_public_host(url.host, allow_private=self._allow_private)
        port = url.port or (_HTTPS_PORT if url.scheme == "https" else 80)
        if url.scheme != "https" or url.host != self._host or port != self._port:
            raise RedirectNotAllowedError("redirect outside the source host or not https")

    def _client(self) -> httpx.Client:
        with self._lock:
            if self._closed:
                raise FetchTransportError("closed")
            if self._http is None:
                self._http = self._new_client()
            return self._http

    def _new_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(get_settings().fetch_http_timeout),
            follow_redirects=True,
            max_redirects=3,
            trust_env=False,
            transport=self._transport,
            event_hooks={"request": [self._guard]},
        )

    def _get_json(self, label: str, path: str, params: Mapping[str, str] | None) -> Any:
        data = self._get_bytes(path, params, label)
        try:
            return json.loads(data)
        except ValueError as exc:
            raise PayloadError(f"{label}: invalid JSON") from exc

    def _get_bytes(self, path: str, params: Mapping[str, str] | None, label: str = "") -> bytes:
        label = label or "GET " + path
        settings = get_settings()
        limit = settings.fetch_max_bytes
        deadline = _monotonic() + settings.fetch_total_timeout
        try:
            with self._client().stream("GET", self._base + path, params=params) as response:
                return self._consume(response, label, limit, deadline)
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            raise FetchTransportError(f"{label}: {type(exc).__name__}") from exc
        except RuntimeError as exc:  # httpx raises it for a client closed mid-request
            raise FetchTransportError("closed") from exc

    @staticmethod
    def _consume(response: httpx.Response, label: str, limit: int, deadline: float) -> bytes:
        status = response.status_code
        if status == 404:
            raise DocumentNotFoundError(f"{label}: not found")
        if status >= 300:
            raise FetchTransportError(f"{label}: HTTP {status}", status_code=status)
        declared = response.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            raise ResponseTooLargeError(f"{label}: body larger than {limit} bytes")
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            if _monotonic() > deadline:
                raise FetchTransportError(f"{label}: total timeout")
            size += len(chunk)
            if size > limit:
                raise ResponseTooLargeError(f"{label}: body larger than {limit} bytes")
            chunks.append(chunk)
        return b"".join(chunks)
