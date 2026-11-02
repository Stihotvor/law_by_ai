from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
import urllib3

from agents.fetch.contracts import DocumentFilter
from agents.fetch.errors import (
    DocumentNotFoundError,
    FetchTransportError,
    InvalidReferenceError,
    ResponseTooLargeError,
    SourceConfigError,
)
from agents.fetch.strategies.minio import MinioStrategy

from .test_minio import _make, _obj, _ref, _response, _s3

pytestmark = pytest.mark.usefixtures("settings_env")
KEY = "gov_pl/2024/act-12.pdf"


def test_prefix_messages_and_x_chars_kept() -> None:
    with pytest.raises(SourceConfigError) as info:
        MinioStrategy("https://m.local/", client=MagicMock())
    assert str(info.value) == "base_url needs a path prefix without '..'"
    c = MagicMock()
    c.list_objects.return_value = iter([_obj("XXgov_XX/a")])
    page = MinioStrategy("https://m.local/XXgov_XX/", client=c).list_refs("g", DocumentFilter())
    assert c.list_objects.call_args.kwargs["prefix"] == "XXgov_XX/"
    assert page.items[0].url == "https://m.local/XXgov_XX/a"


def test_label_strips_only_trailing_slash() -> None:
    c = MagicMock()
    c.list_objects.return_value = iter([_obj("gov_pl/a")])
    page = MinioStrategy("https://m.local/gov_pl/", client=c).list_refs("g", DocumentFilter())
    assert page.items[0].url == "https://m.local/gov_pl/a"


def test_aware_non_utc_is_preserved() -> None:
    s, c = _make()
    tz = timezone(timedelta(hours=2))
    when = datetime(2024, 1, 10, 5, tzinfo=tz)
    c.stat_object.return_value = _obj("k", when=when)
    got = s.get_meta(_ref()).published_at
    assert got is not None and got.utcoffset() == timedelta(hours=2)
    assert got.astimezone(UTC) == datetime(2024, 1, 10, 3, tzinfo=UTC)


@pytest.mark.parametrize("eid", ["a b.pdf", "a!b", "a\x80b"])
def test_boundary_characters_allowed(eid: str) -> None:
    s, c = _make()
    c.stat_object.return_value = _obj("k")
    s.get_meta(_ref(eid))


def test_unsafe_id_message_and_del_rejected() -> None:
    s, _ = _make()
    for eid in ("", "a\x7fb"):
        with pytest.raises(InvalidReferenceError) as info:
            s.get_meta(_ref(eid))
        assert str(info.value) == "unsafe external_id"


def test_cursor_message() -> None:
    s, _ = _make()
    with pytest.raises(InvalidReferenceError) as info:
        s.list_refs("g", DocumentFilter(cursor="other/x"))
    assert str(info.value) == "cursor outside the source prefix"


def test_list_next_cursor_is_last_returned_key() -> None:
    s, _ = _make([_obj(f"gov_pl/{n}") for n in "abcd"])
    page = s.list_refs("g", DocumentFilter(limit=3))
    assert [r.external_id for r in page.items] == ["a", "b", "c"]
    assert page.next_cursor == "gov_pl/c"
    s, _ = _make([_obj("gov_pl/a")])
    assert s.list_refs("g", DocumentFilter(limit=2)).next_cursor is None


def test_list_transport_message() -> None:
    s, c = _make()
    c.list_objects.side_effect = _s3("AccessDenied")
    with pytest.raises(FetchTransportError) as info:
        s.list_refs("g", DocumentFilter())
    assert str(info.value) == "list gov_pl/: AccessDenied"


def test_get_meta_messages() -> None:
    s, c = _make()
    c.stat_object.side_effect = _s3("NoSuchKey")
    with pytest.raises(DocumentNotFoundError) as nf:
        s.get_meta(_ref())
    assert str(nf.value) == f"stat {KEY}: not found"
    c.stat_object.side_effect = _s3("Boom")
    with pytest.raises(FetchTransportError) as s3e:
        s.get_meta(_ref())
    assert str(s3e.value) == f"stat {KEY}: Boom"
    c.stat_object.side_effect = urllib3.exceptions.HTTPError("down")
    with pytest.raises(FetchTransportError) as tr:
        s.get_meta(_ref())
    assert str(tr.value) == f"stat {KEY}: HTTPError"


@pytest.mark.parametrize(
    ("eid", "title"), [("a.pdf", "a.pdf"), ("x/a.pdf", "a.pdf"), ("x/y/a.pdf", "a.pdf")]
)
def test_title_is_last_segment(eid: str, title: str) -> None:
    s, c = _make()
    c.stat_object.return_value = _obj("k")
    assert s.get_meta(_ref(eid)).title == title


def test_read_messages() -> None:
    s, c = _make()
    c.get_object.side_effect = urllib3.exceptions.HTTPError("down")
    with pytest.raises(FetchTransportError) as tr:
        s.read(_ref())
    assert str(tr.value) == f"get {KEY}: HTTPError"
    c.get_object.side_effect = None
    c.get_object.return_value = _response(b"x" * 101)
    with pytest.raises(ResponseTooLargeError) as big:
        s.read(_ref())
    assert str(big.value) == f"get {KEY}: body larger than 100 bytes"
