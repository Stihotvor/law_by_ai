import dataclasses
from typing import Any

import pytest

from agents.fetch.contracts import DocumentFilter, DocumentMeta, DocumentRef
from agents.fetch.errors import SourceConfigError
from agents.fetch.strategies.rest_api import RestListing, RestMapper


def _params(flt: DocumentFilter) -> dict[str, str]:
    return {}


def _parse_list(payload: Any) -> RestListing:
    return RestListing(())


def _parse_meta(payload: Any, ref: DocumentRef) -> DocumentMeta:
    return DocumentMeta(ref=ref, title="t")


def _make(**over: str) -> RestMapper:
    args: dict[str, str] = {
        "list_path": "/documents",
        "meta_path": "/documents/{external_id}",
        "content_path": "/documents/{external_id}/file",
    }
    args.update(over)
    return RestMapper(**args, list_params=_params, parse_list=_parse_list, parse_meta=_parse_meta)


def test_valid_mapper_builds() -> None:
    assert _make().list_path == "/documents"


@pytest.mark.parametrize(
    "over",
    [
        {"list_path": "/d/{x}"},
        {"list_path": "documents"},
        {"meta_path": "documents/{external_id}"},
        {"meta_path": "/documents"},
        {"content_path": "/documents/file"},
        {"content_path": "documents/{external_id}"},
    ],
)
def test_invalid_paths_rejected(over: dict[str, str]) -> None:
    with pytest.raises(SourceConfigError):
        _make(**over)


def _assign(obj: object, name: str, value: object) -> None:
    setattr(obj, name, value)


def test_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _assign(_make(), "list_path", "/x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        _assign(RestListing(()), "next_cursor", "x")
