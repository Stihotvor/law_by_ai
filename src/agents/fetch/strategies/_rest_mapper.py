"""REST mapper contract: paths, id checks and the mapper-call error guard."""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from agents.fetch.contracts import DocumentFilter, DocumentMeta, DocumentRef
from agents.fetch.errors import (
    FetchError,
    InvalidReferenceError,
    PayloadError,
    SourceConfigError,
)
from agents.fetch.registry import Registry

_MAPPER_ERRORS = (KeyError, IndexError, TypeError, ValueError, AttributeError)
_ID_PLACEHOLDER = "{external_id}"


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
    id_safe: str = ""
    id_pattern: str | None = None
    alt_content_paths: Mapping[str, str] = field(default_factory=dict[str, str])

    def __post_init__(self) -> None:
        if self.id_safe not in {"", "/"}:
            raise SourceConfigError("id_safe must be '' or '/'")
        if self.id_pattern is not None:
            try:
                re.compile(self.id_pattern)
            except re.error as exc:
                raise SourceConfigError("id_pattern is not a valid regex") from exc
        if not self.list_path.startswith("/") or "{" in self.list_path:
            raise SourceConfigError("list_path must start with '/' and have no '{'")
        named = [("meta_path", self.meta_path), ("content_path", self.content_path)]
        named += [(f"alt_content_paths[{k!r}]", v) for k, v in self.alt_content_paths.items()]
        for name, path in named:
            if not path.startswith("/") or _ID_PLACEHOLDER not in path:
                raise SourceConfigError(f"{name} must start with '/' and have {_ID_PLACEHOLDER}")


REST_MAPPERS: Registry[RestMapper] = Registry("rest_mappers")


def _check_id(external_id: str, mapper: RestMapper) -> None:
    if external_id in {"", ".", ".."} or any(ord(c) < 32 or ord(c) == 127 for c in external_id):
        raise InvalidReferenceError("unsafe external_id")
    if "/" in mapper.id_safe and (
        "\\" in external_id or any(seg in {"", ".", ".."} for seg in external_id.split("/"))
    ):
        raise InvalidReferenceError("unsafe external_id")
    if mapper.id_pattern is not None and not re.fullmatch(mapper.id_pattern, external_id):
        raise InvalidReferenceError("unsafe external_id")


def build_path(template: str, external_id: str, mapper: RestMapper) -> str:
    _check_id(external_id, mapper)
    return template.format(external_id=quote(external_id, safe=mapper.id_safe))


def with_content_variant(
    base_url: str, mapper: RestMapper, ref: DocumentRef, variant: str
) -> DocumentRef:
    """Return ``ref`` pointing at the named alternative content path."""
    template = mapper.alt_content_paths.get(variant)
    if template is None:
        raise SourceConfigError(f"unknown content variant {variant!r}")
    path = build_path(template, ref.external_id, mapper)
    return ref.model_copy(update={"url": base_url.rstrip("/") + path})


def call_mapper[**P, R](fn: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
    try:
        return fn(*args, **kwargs)
    except FetchError:
        raise
    except _MAPPER_ERRORS as exc:
        raise PayloadError(f"mapper failed: {type(exc).__name__}") from exc
