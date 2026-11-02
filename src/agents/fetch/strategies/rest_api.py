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
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from agents.fetch.contracts import DocumentFilter, DocumentMeta, DocumentPage, DocumentRef
from agents.fetch.errors import (
    DocumentNotFoundError,
    FetchError,
    FetchTransportError,
    InvalidReferenceError,
    PayloadError,
    RedirectNotAllowedError,
    ResponseTooLargeError,
    SourceConfigError,
)
from agents.fetch.registry import Registry, UnknownNameError
from agents.fetch.strategies.base import STRATEGIES
from config.settings import get_settings

_MAPPER_ERRORS = (KeyError, IndexError, TypeError, ValueError, AttributeError)
_ID_PLACEHOLDER = "{external_id}"
_HTTPS_PORT = 443


@dataclass(frozen=True, slots=True)
class RestListing:
    external_ids: tuple[str, ...]
    next_cursor: str | None = None


@dataclass(frozen=True, slots=True)
class RestMapper:
    list_path: str
    meta_path: str
    content_path: str
    list_params: Callable[[DocumentFilter], Mapping[str, str]]
    parse_list: Callable[[Any], RestListing]
    parse_meta: Callable[[Any, DocumentRef], DocumentMeta]

    def __post_init__(self) -> None:
        if not self.list_path.startswith("/") or "{" in self.list_path:
            raise SourceConfigError("list_path must start with '/' and have no '{'")
        for name, path in (("meta_path", self.meta_path), ("content_path", self.content_path)):
            if not path.startswith("/") or _ID_PLACEHOLDER not in path:
                raise SourceConfigError(f"{name} must start with '/' and have {_ID_PLACEHOLDER}")


REST_MAPPERS: Registry[RestMapper] = Registry("rest_mappers")


def _check_id(external_id: str) -> None:
    if external_id in {"", ".", ".."} or any(ord(c) < 32 or ord(c) == 127 for c in external_id):
        raise InvalidReferenceError("unsafe external_id")


def _call[**P, R](fn: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
    try:
        return fn(*args, **kwargs)
    except FetchError:
        raise
    except _MAPPER_ERRORS as exc:
        raise PayloadError(f"mapper failed: {type(exc).__name__}") from exc


@STRATEGIES.register("rest_api")
class RestApiStrategy:
    def __init__(
        self,
        base_url: str,
        *,
        mappers: Registry[RestMapper] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
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
        self._mappers = REST_MAPPERS if mappers is None else mappers
        self._transport = transport

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
                    url=self._base + self._path(mapper.content_path, eid),
                )
                for eid in listing.external_ids
            )
            return DocumentPage(items=refs, next_cursor=listing.next_cursor)
        except (ValueError, TypeError) as exc:
            raise PayloadError(f"mapper returned an invalid id: {type(exc).__name__}") from exc

    def get_meta(self, ref: DocumentRef) -> DocumentMeta:
        mapper = self._mapper(ref.source)
        path = self._path(mapper.meta_path, ref.external_id)
        body = self._get_json("GET " + path, path, None)
        meta = _call(mapper.parse_meta, body, ref)
        if meta.ref != ref:
            raise PayloadError("mapper returned a different ref")
        return meta

    def read(self, ref: DocumentRef) -> bytes:
        mapper = self._mapper(ref.source)
        path = self._path(mapper.content_path, ref.external_id)
        return self._get_bytes(path, None)

    def _mapper(self, source: str) -> RestMapper:
        try:
            return self._mappers.get(source)
        except UnknownNameError:
            raise SourceConfigError(f"no REST mapper for source {source!r}") from None

    @staticmethod
    def _path(template: str, external_id: str) -> str:
        _check_id(external_id)
        return template.format(external_id=quote(external_id, safe=""))

    def _guard(self, request: httpx.Request) -> None:
        url = request.url
        port = url.port or (_HTTPS_PORT if url.scheme == "https" else 80)
        if url.scheme != "https" or url.host != self._host or port != self._port:
            raise RedirectNotAllowedError("redirect outside the source host or not https")

    def _client(self) -> httpx.Client:
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
        limit = get_settings().fetch_max_bytes
        try:
            with (
                self._client() as client,
                client.stream("GET", self._base + path, params=params) as response,
            ):
                return self._consume(response, label, limit)
        except httpx.HTTPError as exc:
            raise FetchTransportError(f"{label}: {type(exc).__name__}") from exc

    @staticmethod
    def _consume(response: httpx.Response, label: str, limit: int) -> bytes:
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
            size += len(chunk)
            if size > limit:
                raise ResponseTooLargeError(f"{label}: body larger than {limit} bytes")
            chunks.append(chunk)
        return b"".join(chunks)
