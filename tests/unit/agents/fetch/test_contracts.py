from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from agents.fetch.contracts import DocumentFilter, DocumentMeta, DocumentRef, FetchedDocument

NOW = datetime(2026, 1, 1, tzinfo=UTC)
REF = DocumentRef(source="s", external_id="1", url="https://x/1")
META = DocumentMeta(ref=REF, title="t")


def test_filter_rules() -> None:
    with pytest.raises(ValidationError):
        DocumentFilter(date_from=NOW + timedelta(days=1), date_to=NOW)
    for limit in (0, 501):
        with pytest.raises(ValidationError):
            DocumentFilter(limit=limit)
    flt = DocumentFilter()
    assert flt.limit == 50
    assert (flt.date_from, flt.date_to, flt.doc_type, flt.keyword, flt.cursor) == (None,) * 5


def test_naive_datetime_rejected() -> None:
    naive = datetime(2026, 1, 1)
    with pytest.raises(ValidationError):
        DocumentFilter(date_from=naive)
    with pytest.raises(ValidationError):
        FetchedDocument(meta=META, content=b"", fetched_at=naive)


def test_frozen_and_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        REF.source = "other"  # type: ignore[misc]
    kwargs: dict[str, Any] = {"source": "s", "external_id": "1", "url": "u", "bogus": 1}
    with pytest.raises(ValidationError):
        DocumentRef(**kwargs)


@pytest.mark.parametrize("field", ["source", "external_id", "url"])
def test_ref_rejects_empty(field: str) -> None:
    kwargs = {"source": "s", "external_id": "1", "url": "u", field: ""}
    with pytest.raises(ValidationError):
        DocumentRef(**kwargs)


def test_fetched_document_bytes_roundtrip() -> None:
    doc = FetchedDocument(meta=META, content=b"\x00\xff", fetched_at=NOW)
    assert FetchedDocument.model_validate(doc.model_dump()).content == b"\x00\xff"


def _msg(exc: pytest.ExceptionInfo[ValidationError]) -> str:
    return str(exc.value.errors()[0]["msg"])


def test_naive_datetime_message() -> None:
    naive = datetime(2026, 1, 1)
    expected = "Value error, datetime must be timezone-aware"
    with pytest.raises(ValidationError) as f:
        DocumentFilter(date_from=naive)
    assert _msg(f) == expected
    with pytest.raises(ValidationError) as m:
        DocumentMeta(ref=REF, title="t", published_at=naive)
    assert _msg(m) == expected
    with pytest.raises(ValidationError) as d:
        FetchedDocument(meta=META, content=b"", fetched_at=naive)
    assert _msg(d) == expected
