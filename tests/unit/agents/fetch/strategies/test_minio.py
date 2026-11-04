from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import urllib3
from minio.error import MinioException, S3Error

from agents.fetch.contracts import DocumentFilter, DocumentRef
from agents.fetch.errors import (
    DocumentNotFoundError,
    FetchTransportError,
    InvalidReferenceError,
    ResponseTooLargeError,
    SourceConfigError,
)
from agents.fetch.strategies import STRATEGIES
from agents.fetch.strategies.base import FetchStrategy
from agents.fetch.strategies.minio import MinioStrategy

BASE = "https://m.local/gov_pl"
CANARY = "test-secret-value"
T0 = datetime(2024, 1, 10, tzinfo=UTC)
pytestmark = pytest.mark.usefixtures("settings_env")
KEY = "gov_pl/2024/act-12.pdf"


def _obj(
    name: str,
    *,
    when: datetime | None = T0,
    is_dir: bool = False,
    size: int = 5,
) -> SimpleNamespace:
    return SimpleNamespace(
        object_name=name,
        last_modified=when,
        is_dir=is_dir,
        size=size,
        etag="etag1",
        content_type="application/pdf",
    )


def _s3(code: str) -> S3Error:
    return S3Error(MagicMock(), code, "msg", "res", "req", "host")


def _make(objects: list[SimpleNamespace] | None = None) -> tuple[MinioStrategy, MagicMock]:
    client = MagicMock()
    client.list_objects.return_value = iter(objects or [])
    return MinioStrategy(BASE, client=client), client


def _ref(eid: str = "2024/act-12.pdf") -> DocumentRef:
    return DocumentRef.model_construct(source="gov", external_id=eid, url="https://evil/x")


def test_default_client_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = MagicMock()
    monkeypatch.setattr("agents.fetch.strategies.minio.Minio", fake)
    MinioStrategy(BASE)
    fake.assert_called_once()
    args, kwargs = fake.call_args
    assert args == ("minio.test:9000",)
    assert kwargs["access_key"] == "test-access"
    assert kwargs["secret_key"] == CANARY
    assert kwargs["secure"] is True
    http = kwargs["http_client"]
    assert isinstance(http, urllib3.PoolManager)
    assert http.connection_pool_kw["timeout"].connect_timeout == 3.5
    assert http.connection_pool_kw["timeout"].read_timeout == 3.5
    assert http.connection_pool_kw["retries"].total == 0


def test_secure_false_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = MagicMock()
    monkeypatch.setattr("agents.fetch.strategies.minio.Minio", fake)
    monkeypatch.setenv("MINIO_SECURE", "false")
    MinioStrategy(BASE)
    assert fake.call_args.kwargs["secure"] is False


@pytest.mark.parametrize("var", ["MINIO_ACCESS_KEY", "MINIO_SECRET_KEY"])
def test_missing_credentials(monkeypatch: pytest.MonkeyPatch, var: str) -> None:
    monkeypatch.setenv(var, "")
    with pytest.raises(SourceConfigError) as info:
        MinioStrategy(BASE)
    assert str(info.value) == "MinIO credentials are not set"
    assert CANARY not in str(info.value)


@pytest.mark.parametrize("url", ["https://m.local", "https://m.local/", "https://m.local/a/../b"])
def test_bad_prefix(url: str) -> None:
    with pytest.raises(SourceConfigError):
        MinioStrategy(url, client=MagicMock())


def test_prefix_derivation() -> None:
    for url in ("https://m.local/gov_pl", "https://m.local/gov_pl/", "https://m.local//gov_pl//"):
        s, c = _make()
        s2 = MinioStrategy(url, client=c)
        s2.list_refs("gov", DocumentFilter())
        assert c.list_objects.call_args.kwargs["prefix"] == "gov_pl/"
        assert s is not s2


def test_list_refs_call_and_mapping() -> None:
    s, c = _make(
        [
            _obj("gov_pl/2024/a.pdf"),
            _obj("gov_pl/2024/", is_dir=True),
            _obj("gov_pl/sub/", is_dir=False),
            _obj("gov_pl/b.pdf"),
        ]
    )
    page = s.list_refs("gov", DocumentFilter())
    c.list_objects.assert_called_once_with(
        "test-bucket", prefix="gov_pl/", recursive=True, start_after=None
    )
    assert [r.external_id for r in page.items] == ["2024/a.pdf", "b.pdf"]
    assert page.items[0].url == "https://m.local/gov_pl/2024/a.pdf"
    assert page.items[0].source == "gov"
    assert page.next_cursor is None


def test_dir_flag_skipped_even_without_slash() -> None:
    s, _ = _make([_obj("gov_pl/x", is_dir=True), _obj("gov_pl/y")])
    assert [r.external_id for r in s.list_refs("gov", DocumentFilter()).items] == ["y"]


def test_limit_and_cursor() -> None:
    objs = [_obj(f"gov_pl/{i}.pdf") for i in range(3)]
    s, c = _make(objs)
    page = s.list_refs("gov", DocumentFilter(limit=2))
    assert [r.external_id for r in page.items] == ["0.pdf", "1.pdf"]
    assert page.next_cursor == "gov_pl/1.pdf"

    s, c = _make(objs[:2])
    page = s.list_refs("gov", DocumentFilter(limit=2))
    assert len(page.items) == 2
    assert page.next_cursor is None

    s, c = _make([])
    s.list_refs("gov", DocumentFilter(cursor="gov_pl/1.pdf"))
    assert c.list_objects.call_args.kwargs["start_after"] == "gov_pl/1.pdf"


def test_cursor_outside_prefix() -> None:
    s, c = _make()
    with pytest.raises(InvalidReferenceError):
        s.list_refs("gov", DocumentFilter(cursor="other/1.pdf"))
    c.list_objects.assert_not_called()


def test_filters_date_inclusive_keyword_and_doc_type() -> None:
    objs = [
        _obj("gov_pl/old-Act.pdf", when=T0 - timedelta(days=2)),
        _obj("gov_pl/edge-from-act.pdf", when=T0),
        _obj("gov_pl/mid-act.pdf", when=T0 + timedelta(days=1)),
        _obj("gov_pl/edge-to-act.pdf", when=T0 + timedelta(days=2)),
        _obj("gov_pl/late-act.pdf", when=T0 + timedelta(days=3)),
        _obj("gov_pl/mid-other.pdf", when=T0 + timedelta(days=1)),
    ]
    flt = DocumentFilter(
        date_from=T0,
        date_to=T0 + timedelta(days=2),
        keyword="ACT",
        doc_type="ignored",
    )
    s, _ = _make(objs)
    ids = [r.external_id for r in s.list_refs("gov", flt).items]
    assert ids == ["edge-from-act.pdf", "mid-act.pdf", "edge-to-act.pdf"]


def test_filters_single_sided_and_naive_and_missing_date() -> None:
    naive = datetime(2024, 1, 10)
    objs = [_obj("gov_pl/a", when=naive), _obj("gov_pl/b", when=None)]
    s, _ = _make(objs)
    assert [r.external_id for r in s.list_refs("gov", DocumentFilter(date_from=T0)).items] == ["a"]
    s, _ = _make(objs)
    assert [r.external_id for r in s.list_refs("gov", DocumentFilter(date_to=T0)).items] == ["a"]
    s, _ = _make(objs)
    assert len(s.list_refs("gov", DocumentFilter()).items) == 2


def test_keyword_matches_relative_key_only() -> None:
    s, _ = _make([_obj("gov_pl/a.pdf")])
    assert s.list_refs("gov", DocumentFilter(keyword="gov_pl")).items == ()


def test_list_transport_error() -> None:
    s, c = _make()
    c.list_objects.side_effect = _s3("AccessDenied")
    with pytest.raises(FetchTransportError) as info:
        s.list_refs("gov", DocumentFilter())
    assert "AccessDenied" in str(info.value)


def test_get_meta_fields() -> None:
    s, c = _make()
    c.stat_object.return_value = _obj("gov_pl/2024/act-12.pdf", when=datetime(2024, 1, 10))
    meta = s.get_meta(_ref())
    c.stat_object.assert_called_once_with("test-bucket", "gov_pl/2024/act-12.pdf")
    assert meta.ref == _ref()
    assert meta.title == "act-12.pdf"
    assert meta.doc_type is None
    assert meta.language is None
    assert meta.published_at == datetime(2024, 1, 10, tzinfo=UTC)
    assert meta.extra == {"content_type": "application/pdf", "size": 5, "etag": "etag1"}


def test_get_meta_no_date_and_aware_kept() -> None:
    s, c = _make()
    c.stat_object.return_value = _obj("k", when=None)
    assert s.get_meta(_ref()).published_at is None
    local = datetime(2024, 1, 10, 5, tzinfo=UTC) + timedelta(0)
    c.stat_object.return_value = _obj("k", when=local)
    assert s.get_meta(_ref()).published_at == local


def test_get_meta_errors() -> None:
    s, c = _make()
    c.stat_object.side_effect = _s3("NoSuchKey")
    with pytest.raises(DocumentNotFoundError):
        s.get_meta(_ref())
    c.stat_object.side_effect = urllib3.exceptions.HTTPError("down")
    with pytest.raises(FetchTransportError):
        s.get_meta(_ref())


def _response(data: bytes = b"data") -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = data
    return resp


def test_read_ok_and_cleanup() -> None:
    s, c = _make()
    resp = _response()
    c.get_object.return_value = resp
    assert s.read(_ref()) == b"data"
    c.get_object.assert_called_once_with("test-bucket", "gov_pl/2024/act-12.pdf")
    resp.read.assert_called_once_with(101)
    resp.close.assert_called_once()
    resp.release_conn.assert_called_once()


def test_read_cleanup_on_error() -> None:
    s, c = _make()
    resp = _response()
    resp.read.side_effect = urllib3.exceptions.ProtocolError("cut")
    c.get_object.return_value = resp
    with pytest.raises(FetchTransportError):
        s.read(_ref())
    resp.close.assert_called_once()
    resp.release_conn.assert_called_once()


@pytest.mark.parametrize("eid", ["", "/abs", "../x", "a/../b", "a//b", "a\\b", "a\nb", "./a", "a/"])
def test_unsafe_ids(eid: str) -> None:
    s, c = _make()
    with pytest.raises(InvalidReferenceError):
        s.read(_ref(eid))
    with pytest.raises(InvalidReferenceError):
        s.get_meta(_ref(eid))
    c.get_object.assert_not_called()
    c.stat_object.assert_not_called()


def test_dotted_names_allowed() -> None:
    s, c = _make()
    c.get_object.return_value = _response()
    s.read(_ref("..a/b.c"))
    assert c.get_object.call_args.args[1] == "gov_pl/..a/b.c"


def test_ref_url_ignored() -> None:
    s, c = _make()
    c.get_object.return_value = _response()
    s.read(_ref("x.pdf"))
    assert c.get_object.call_args.args == ("test-bucket", "gov_pl/x.pdf")


def test_over_limit_body() -> None:
    s, c = _make()
    c.get_object.return_value = _response(b"x" * 101)
    with pytest.raises(ResponseTooLargeError):
        s.read(_ref())
    c.get_object.return_value = _response(b"x" * 100)
    assert len(s.read(_ref())) == 100


def test_read_errors() -> None:
    s, c = _make()
    c.get_object.side_effect = _s3("NoSuchKey")
    with pytest.raises(DocumentNotFoundError):
        s.read(_ref())
    for exc in (
        _s3("InternalError"),
        MinioException("boom"),
        urllib3.exceptions.MaxRetryError(MagicMock(), "/x"),
    ):
        c.get_object.side_effect = exc
        with pytest.raises(FetchTransportError) as info:
            s.read(_ref())
        assert CANARY not in str(info.value)
        assert "test-access" not in str(info.value)
    c.get_object.side_effect = _s3("InternalError")
    with pytest.raises(FetchTransportError, match=r"get gov_pl/2024/act-12\.pdf: InternalError"):
        s.read(_ref())


def test_transport_error_without_code_uses_type_name() -> None:
    s, c = _make()
    c.get_object.side_effect = MinioException("boom")
    with pytest.raises(FetchTransportError, match="MinioException"):
        s.read(_ref())


def test_registered_protocol_and_repr() -> None:
    assert STRATEGIES.get("minio") is MinioStrategy
    s, _ = _make()
    assert isinstance(s, FetchStrategy)
    text = repr(s)
    assert CANARY not in text
    assert "test-access" not in text
    assert all(CANARY not in str(v) for v in vars(s).values() if not isinstance(v, MagicMock))


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
    assert got is not None
    assert got.utcoffset() == timedelta(hours=2)
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


def test_release_conn_runs_when_close_raises() -> None:
    s, c = _make()
    resp = MagicMock()
    resp.read.return_value = b"x"
    resp.close.side_effect = RuntimeError("boom")
    c.get_object.return_value = resp
    with pytest.raises(RuntimeError):
        s.read(_ref())
    resp.release_conn.assert_called_once()


@pytest.mark.parametrize("url", ["https://m.local/a//b", "https://m.local/a\\b"])
def test_prefix_rejects_double_slash_and_backslash(url: str) -> None:
    with pytest.raises(SourceConfigError):
        MinioStrategy(url, client=MagicMock())


@pytest.mark.parametrize("cursor", ["gov_pl/../x", "gov_pl//x", "gov_pl/a\\b", "gov_pl/"])
def test_cursor_remainder_must_be_safe(cursor: str) -> None:
    s, c = _make()
    with pytest.raises(InvalidReferenceError):
        s.list_refs("gov", DocumentFilter(cursor=cursor))
    c.list_objects.assert_not_called()


def test_prefix_rejects_dot_segment() -> None:
    with pytest.raises(SourceConfigError):
        MinioStrategy("https://m.local/a/./b", client=MagicMock())


def test_client_value_error_is_transport_error() -> None:
    s, c = _make()
    c.stat_object.side_effect = ValueError("bad bucket")
    with pytest.raises(FetchTransportError):
        s.get_meta(_ref())


def test_close_clears_own_pool_only(monkeypatch: pytest.MonkeyPatch) -> None:
    s, client = _make()
    s.close()
    assert not client._http.clear.called
    monkeypatch.setattr("agents.fetch.strategies.minio.Minio", MagicMock())
    own = MinioStrategy(BASE)
    assert own._pool is not None
    cleared: list[bool] = []
    monkeypatch.setattr(own._pool, "clear", lambda: cleared.append(True))
    own.close()
    assert cleared == [True]
