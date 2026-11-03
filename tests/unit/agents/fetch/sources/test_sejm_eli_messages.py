import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from agents.fetch.contracts import DocumentFilter, DocumentMeta, DocumentRef
from agents.fetch.errors import DocumentNotFoundError, InvalidReferenceError
from agents.fetch.sources.sejm_eli import SejmEliSource, _list_params, _parse_meta


@pytest.fixture
def tz(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[str], None]]:
    def _set(name: str) -> None:
        monkeypatch.setenv("TZ", name)
        time.tzset()

    yield _set
    monkeypatch.undo()
    time.tzset()


@pytest.mark.parametrize("zone", ["UTC", "Pacific/Auckland", "America/Los_Angeles"])
def test_date_uses_warsaw_not_local_zone(tz: Callable[[str], None], zone: str) -> None:
    tz(zone)
    moment = datetime(2024, 1, 31, 23, 30, tzinfo=UTC)
    assert _list_params(DocumentFilter(date_from=moment))["pubDateFrom"] == "2024-01-31"
    assert _list_params(DocumentFilter(date_to=moment))["pubDateTo"] == "2024-02-01"


def test_message_texts() -> None:
    with pytest.raises(InvalidReferenceError) as err:
        _list_params(DocumentFilter(cursor="x"))
    assert str(err.value) == "invalid cursor"
    with pytest.raises(InvalidReferenceError) as err:
        _list_params(DocumentFilter(keyword="x" * 201))
    assert str(err.value) == "invalid filter value"
    ref = DocumentRef(source="sejm_eli", external_id="DU/2024/1", url="https://x")
    with pytest.raises(ValueError) as err2:
        _parse_meta({"ELI": "DU/2024/2"}, ref)
    assert str(err2.value) == "ELI does not match the reference"


@pytest.mark.usefixtures("no_throttle")
def test_no_text_message() -> None:
    class Strat:
        def get_meta(self, ref: DocumentRef) -> DocumentMeta:
            return _parse_meta({"ELI": ref.external_id, "title": "t", "type": "u"}, ref)

    ref = DocumentRef(source="sejm_eli", external_id="DU/2024/1", url="https://x")
    source = SejmEliSource(cast(Any, Strat()))
    with pytest.raises(DocumentNotFoundError) as err:
        source.fetch_document(ref)
    assert str(err.value) == "act has no text"
