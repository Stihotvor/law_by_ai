from datetime import UTC, datetime, timedelta
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
SECRET = "test-secret-value"
T0 = datetime(2024, 1, 10, tzinfo=UTC)
pytestmark = pytest.mark.usefixtures("settings_env")


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
    assert kwargs["secret_key"] == SECRET
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
    assert SECRET not in str(info.value)


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
        assert SECRET not in str(info.value)
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
    assert SECRET not in text and "test-access" not in text
    assert all(SECRET not in str(v) for v in vars(s).values() if not isinstance(v, MagicMock))
