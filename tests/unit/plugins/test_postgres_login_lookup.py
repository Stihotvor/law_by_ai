"""Email lookups of the PostgreSQL store, with a fake session.

Unit tests: the store builds the query and maps the row without a database.
The real query runs in the integration tests.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from sqlalchemy.exc import OperationalError

from core.security import get_current_tenant, set_current_tenant
from plugins.relational_db import postgres
from plugins.relational_db.postgres import PostgreSQLStore, User

BCRYPT_HASH = "$2b$12$hash"

ROW = User(
    id="u-1",
    tenant_id="t-1",
    email="admin@example.com",
    name="Admin",
    role="admin",
    password_hash=BCRYPT_HASH,
    is_active=True,
    session_version=2,
)


class FakeSession:
    """Records the statement and the tenant seen inside the session."""

    seen: ClassVar[dict[str, Any]] = {}

    def __init__(self, _engine: object, row: User | None) -> None:
        self._row = row

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, stmt: Any) -> FakeSession:
        FakeSession.seen["stmt"] = stmt
        FakeSession.seen["tenant"] = get_current_tenant()
        return self

    def commit(self) -> None:
        FakeSession.seen["committed"] = True

    def scalar_one_or_none(self) -> User | None:
        return self._row


def _email() -> str:
    return FakeSession.seen["stmt"].compile().params["email_1"]


@pytest.fixture
def store_with(monkeypatch: pytest.MonkeyPatch):
    def make(row: User | None) -> PostgreSQLStore:
        store = PostgreSQLStore()
        monkeypatch.setattr(store, "_ensure_initialized", lambda: None)
        monkeypatch.setattr(postgres, "Session", lambda engine: FakeSession(engine, row))
        FakeSession.seen = {}
        return store

    return make


LOGIN_ROW = {
    "id": "u-1",
    "tenant_id": "t-1",
    "email": "a@x.pl",
    "role": "admin",
    "name": "Admin",
    "is_active": True,
    "password_hash": BCRYPT_HASH,
    "session_version": 2,
}
LOGIN_KEYS = {
    "id",
    "tenant_id",
    "email",
    "role",
    "name",
    "is_active",
    "password_hash",
    "session_version",
}


class FakeLoginSession(FakeSession):
    """Records the SQL and parameters of the ``auth_lookup_user`` call."""

    def __init__(self, engine: object, row: dict[str, Any] | None, error: Exception | None) -> None:
        super().__init__(engine, None)
        self._login_row, self._error = row, error

    def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> FakeLoginSession:
        if self._error is not None:
            raise self._error
        FakeSession.seen |= {"stmt": stmt, "params": params, "tenant": get_current_tenant()}
        return self

    def mappings(self) -> FakeLoginSession:
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self._login_row


@pytest.fixture
def login_store_with(monkeypatch: pytest.MonkeyPatch):
    def make(row: dict[str, Any] | None, error: Exception | None = None) -> PostgreSQLStore:
        def session(engine: object) -> FakeLoginSession:
            return FakeLoginSession(engine, row, error)

        store = PostgreSQLStore()
        monkeypatch.setattr(store, "_ensure_initialized", lambda: None)
        monkeypatch.setattr(postgres, "Session", session)
        FakeSession.seen = {}
        return store

    return make


def test_get_login_user_calls_auth_lookup_user(login_store_with) -> None:
    """Scenario: Login lookup uses the function."""
    result = login_store_with(LOGIN_ROW).get_login_user(" A@x.PL ")

    assert "auth_lookup_user(:email)" in str(FakeSession.seen["stmt"])
    assert FakeSession.seen["params"] == {"email": "a@x.pl"}
    assert result is not None
    assert set(result) == LOGIN_KEYS
    assert result == LOGIN_ROW


def test_get_login_user_ignores_extra_columns(login_store_with) -> None:
    """A column the function adds later does not break the lookup or leak into the dict."""
    result = login_store_with(LOGIN_ROW | {"created_at": "2026-01-01"}).get_login_user("a@x.pl")

    assert result == LOGIN_ROW


def test_get_login_user_keeps_the_current_tenant(login_store_with) -> None:
    """The lookup no longer clears the tenant; the function itself ignores RLS."""
    store = login_store_with(LOGIN_ROW)
    set_current_tenant("t-other")
    try:
        assert store.get_login_user("a@x.pl") is not None
    finally:
        set_current_tenant(None)
    assert FakeSession.seen["tenant"] == "t-other"


def test_get_login_user_returns_none_for_unknown_email(login_store_with) -> None:
    """Scenario: Unknown email."""
    assert login_store_with(None).get_login_user("nobody@example.com") is None


def test_get_login_user_propagates_operational_error(login_store_with) -> None:
    """Scenario: Database down."""
    store = login_store_with(None, OperationalError("SELECT", {}, Exception("down")))
    with pytest.raises(OperationalError):
        store.get_login_user("a@x.pl")


def test_get_user_by_email_docstring_states_none_without_tenant() -> None:
    """Scenario: Docstrings are fixed."""
    doc = " ".join((PostgreSQLStore.get_user_by_email.__doc__ or "").split())
    assert "None" in doc
    assert "no tenant set" in doc


def test_module_docstring_and_list_tenants_are_fail_closed() -> None:
    """The module docstring no longer says an empty setting shows every row."""
    doc = " ".join((postgres.__doc__ or "").split())
    assert "fully visible" not in doc
    assert "no rows" in doc
    tenants_doc = " ".join((PostgreSQLStore.list_tenants.__doc__ or "").split())
    assert "current tenant only" in tenants_doc


def test_get_user_by_email_normalises_email(store_with) -> None:
    store = store_with(ROW)
    result = store.get_user_by_email(" ADMIN@example.com")

    assert _email() == "admin@example.com"
    assert result is not None
    assert "password_hash" not in result


def test_get_user_by_email_returns_none_for_unknown_email(store_with) -> None:
    assert store_with(None).get_user_by_email("nobody@example.com") is None


def test_bump_session_version_updates_one_user_under_current_tenant(store_with) -> None:
    store = store_with(None)
    set_current_tenant("t-1")
    try:
        store.bump_session_version("u-1")
    finally:
        set_current_tenant(None)

    sql = str(FakeSession.seen["stmt"].compile())
    assert sql.startswith("UPDATE users SET session_version=(users.session_version +")
    assert FakeSession.seen["stmt"].compile().params == {"id_1": "u-1", "session_version_1": 1}
    assert FakeSession.seen["tenant"] == "t-1"
    assert FakeSession.seen["committed"] is True
