"""Unit tests for the init program (fakes for the store and the S3 client)."""

from __future__ import annotations

import runpy
from dataclasses import replace
from unittest.mock import MagicMock

import pytest
import urllib3
from factories.bootstrap import STRONG, FakeBucket, FakeSettings, FakeStore, integrity_error
from minio import Minio
from minio.error import S3Error, ServerError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from bootstrap import init_stack
from bootstrap.init_stack import db_revision, run, validate_config
from core.security import ADMIN, USER

STEPS = ("schema", "bucket", "tenant", "admin")


def pg_down() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("connection refused"))


def s3_error(code: str) -> S3Error:
    return S3Error(MagicMock(), code, "msg", "res", "req", "host")


def go(
    store: FakeStore,
    client: FakeBucket,
    settings: FakeSettings | None = None,
    sleeps: list[float] | None = None,
) -> int:
    sleep = (sleeps if sleeps is not None else []).append
    return run(
        settings or FakeSettings(), store, client, revision=store.current_revision, sleep=sleep
    )


def test_first_run_creates_everything(caplog: pytest.LogCaptureFixture) -> None:
    store, client = FakeStore(), FakeBucket()
    assert go(store, client) == 0
    assert store.tenants == {"platform": "Platform"}
    user = store.users["admin@example.com"]
    assert (user["role"], user["tenant_id"], user["name"]) == (ADMIN, "platform", "Admin")
    assert client.buckets == {"legal-documents"}
    for step in STEPS:
        assert f"step={step} result=created" in caplog.messages


def test_second_run_is_a_noop(caplog: pytest.LogCaptureFixture) -> None:
    store, client = FakeStore(), FakeBucket()
    assert go(store, client) == 0
    store.calls.clear()
    client.calls.clear()
    caplog.clear()
    assert go(store, client) == 0
    assert caplog.messages == [f"step={step} result=exists" for step in STEPS]
    assert "create_tenant" not in store.calls
    assert "create_user" not in store.calls
    assert client.calls == ["bucket_exists"]


def test_valid_config_has_no_problems() -> None:
    assert validate_config(FakeSettings()) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("init_admin_email", "admin.example.com"),
        ("init_admin_password", "short-pw"),
        ("init_admin_password", "ą" * 37),
        ("init_admin_password", "change-me-admin-password"),
        ("postgres_password", "change-me-postgres"),
        ("minio_secret_key", "Change-Me-s3-secret"),
        ("minio_access_key", ""),
        ("minio_secret_key", ""),
        ("minio_endpoint", ""),
        ("minio_bucket", ""),
        ("init_tenant_id", ""),
        ("init_tenant_name", ""),
    ],
)
def test_bad_config_exits_2_before_any_call(
    field: str, value: str, caplog: pytest.LogCaptureFixture
) -> None:
    store, client = FakeStore(), FakeBucket()
    settings = replace(FakeSettings(), **{field: value})
    assert len(validate_config(settings)) == 1
    assert go(store, client, settings) == 2
    assert store.calls == []
    assert client.calls == []
    assert caplog.messages[0].startswith("step=config result=failed problems=")
    assert field.upper() in caplog.text
    if value:
        assert value not in caplog.text


def test_password_of_exactly_twelve_and_72_bytes_is_accepted() -> None:
    assert validate_config(replace(FakeSettings(), init_admin_password="x" * 12)) == []
    assert validate_config(replace(FakeSettings(), init_admin_password="ą" * 36)) == []


def test_postgres_unreachable_exits_3_after_backoff(caplog: pytest.LogCaptureFixture) -> None:
    store, client, sleeps = (
        FakeStore(revision_errors=[pg_down() for _ in range(5)]),
        FakeBucket(),
        [],
    )
    assert go(store, client, sleeps=sleeps) == 3
    assert sleeps == [1.0, 2.0, 4.0, 8.0]
    assert "initialize" not in store.calls
    assert client.calls == []
    assert "step=schema result=failed reason=unreachable error=OperationalError" in caplog.text


@pytest.mark.parametrize(
    "error",
    [
        urllib3.exceptions.MaxRetryError(MagicMock(), "/", None),
        ServerError("unavailable", 503),
    ],
)
def test_s3_unreachable_exits_3(error: Exception, caplog: pytest.LogCaptureFixture) -> None:
    store, client, sleeps = FakeStore(), FakeBucket(exists_errors=[error] * 5), []
    assert go(store, client, sleeps=sleeps) == 3
    assert sleeps == [1.0, 2.0, 4.0, 8.0]
    assert "step=bucket result=failed reason=unreachable" in caplog.text
    assert "list_tenants" not in store.calls


def test_retry_recovers_after_short_gap() -> None:
    store = FakeStore(revision_errors=[pg_down(), pg_down()])
    client, sleeps = FakeBucket(exists_errors=[ServerError("busy", 503)]), []
    assert go(store, client, sleeps=sleeps) == 0
    assert sleeps == [1.0, 2.0, 1.0]
    assert client.buckets == {"legal-documents"}


def test_other_probe_error_is_not_retried() -> None:
    store, sleeps = FakeStore(revision_errors=[RuntimeError("bad")]), []
    assert go(store, FakeBucket(), sleeps=sleeps) == 4
    assert sleeps == []


@pytest.mark.parametrize(
    ("step", "store", "client"),
    [
        ("schema", FakeStore(fail={"initialize": RuntimeError("migration")}), FakeBucket()),
        ("bucket", FakeStore(), FakeBucket(make_error=s3_error("AccessDenied"))),
        ("tenant", FakeStore(fail={"create_tenant": RuntimeError("db")}), FakeBucket()),
        ("admin", FakeStore(fail={"create_user": RuntimeError("db")}), FakeBucket()),
    ],
)
def test_failed_step_exits_4_and_names_the_step(
    step: str, store: FakeStore, client: FakeBucket, caplog: pytest.LogCaptureFixture
) -> None:
    assert go(store, client) == 4
    assert caplog.messages[-1].startswith(f"step={step} result=failed error=")
    assert len(caplog.messages) == STEPS.index(step) + 1


def test_bucket_already_owned_counts_as_exists(caplog: pytest.LogCaptureFixture) -> None:
    client = FakeBucket(make_error=s3_error("BucketAlreadyOwnedByYou"))
    assert go(FakeStore(), client) == 0
    assert "step=bucket result=exists" in caplog.messages


@pytest.mark.parametrize(
    ("method", "step"), [("create_tenant", "tenant"), ("create_user", "admin")]
)
def test_integrity_error_race_counts_as_exists(
    method: str, step: str, caplog: pytest.LogCaptureFixture
) -> None:
    assert go(FakeStore(fail={method: integrity_error()}), FakeBucket()) == 0
    assert f"step={step} result=exists" in caplog.messages


@pytest.mark.parametrize(("role", "active"), [(USER, True), (ADMIN, False)])
def test_existing_user_is_never_changed(
    role: str, active: bool, caplog: pytest.LogCaptureFixture
) -> None:
    user = {"email": "admin@example.com", "role": role, "is_active": active, "password": "old"}
    store = FakeStore(users={"admin@example.com": dict(user)})
    assert go(store, FakeBucket()) == 0
    assert store.users["admin@example.com"] == user
    assert "create_user" not in store.calls
    assert any(r.levelname == "WARNING" and "not changed" in r.message for r in caplog.records)
    assert "step=admin result=exists" in caplog.messages


def test_existing_active_admin_logs_no_warning(caplog: pytest.LogCaptureFixture) -> None:
    store = FakeStore(users={"admin@example.com": {"role": ADMIN, "is_active": True}})
    assert go(store, FakeBucket()) == 0
    assert all(r.levelname == "INFO" for r in caplog.records)


def test_secrets_never_appear_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    settings = FakeSettings()
    go(FakeStore(), FakeBucket(), settings)
    go(FakeStore(fail={"create_user": RuntimeError(STRONG)}), FakeBucket(), settings)
    go(FakeStore(), FakeBucket(), replace(settings, init_admin_password=STRONG + "x" * 72))
    assert caplog.messages
    for secret in (STRONG, settings.minio_secret_key, settings.postgres_password):
        assert secret not in caplog.text


def test_db_revision_reads_alembic_version(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'db.sqlite'}"
    assert db_revision(url) is None
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version VALUES ('abc123')"))
    engine.dispose()
    assert db_revision(url) == "abc123"


def test_s3_client_is_built_from_settings() -> None:
    client = init_stack.s3_client(FakeSettings())
    assert isinstance(client, Minio)


def test_module_entry_point_exits_2_on_bad_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INIT_ADMIN_EMAIL", "no-at-sign")
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("bootstrap", run_name="__main__")
    assert exit_info.value.code == 2
