"""User port methods of the PostgreSQL store (T2), with a fake session.

Unit tests: the store builds the query, maps errors and rows without a database.
The real queries run in ``tests/integration/test_store_users.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, OperationalError

from core.security import PrincipalRequiredError, tenant_context
from core.users.errors import UserCreateRefusedError
from plugins.relational_db import user_store
from plugins.relational_db.mappers import user_to_record
from plugins.relational_db.postgres import PostgreSQLStore, User

TENANT = "t-a"
HASH = "$2b$12$h"
RECORD_KEYS = {"id", "tenant_id", "email", "role", "name", "is_active"}


def _user(**overrides: Any) -> User:
    values: dict[str, Any] = {
        "id": "u-1",
        "tenant_id": TENANT,
        "email": "a@x.pl",
        "name": "Admin",
        "role": "admin",
        "password_hash": "$2b$12$hash",
        "is_active": True,
        "session_version": 3,
    }
    return User(**(values | overrides))


def _integrity(sqlstate: str, constraint: str | None) -> IntegrityError:
    orig = SimpleNamespace(sqlstate=sqlstate, diag=SimpleNamespace(constraint_name=constraint))
    return IntegrityError("INSERT INTO users ...", {}, orig)  # type: ignore[arg-type]


class FakeSession:
    """Records statements, added rows and rollbacks; raises *error* on flush."""

    def __init__(self, rows: list[User], error: Exception | None) -> None:
        self.rows, self.error = rows, error
        self.statements: list[Any] = []
        self.added: list[User] = []
        self.flushed = self.committed = self.rolled_back = False

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def begin(self) -> FakeSession:
        return _Tx(self)  # type: ignore[return-value]

    def add(self, row: User) -> None:
        self.added.append(row)

    def flush(self) -> None:
        if self.error is not None:
            raise self.error
        self.flushed = True

    def execute(self, stmt: Any) -> FakeSession:
        if self.error is not None:
            raise self.error
        self.statements.append(stmt)
        return self

    def scalars(self) -> FakeSession:
        return self

    def all(self) -> list[User]:
        return self.rows

    def scalar_one_or_none(self) -> User | None:
        return self.rows[0] if self.rows else None


class _Tx:
    """``session.begin()``: commit on success, roll back on any error."""

    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __enter__(self) -> FakeSession:
        return self.session

    def __exit__(self, exc_type: object, *_: object) -> None:
        if exc_type is None:
            self.session.committed = True
        else:
            self.session.rolled_back = True


MakeStore = Callable[..., tuple[PostgreSQLStore, list[FakeSession]]]


@pytest.fixture
def store_with(monkeypatch: pytest.MonkeyPatch) -> MakeStore:
    def make(
        rows: list[User] | None = None, error: Exception | None = None
    ) -> tuple[PostgreSQLStore, list[FakeSession]]:
        sessions: list[FakeSession] = []

        def session(_engine: object) -> FakeSession:
            sessions.append(FakeSession(rows or [], error))
            return sessions[-1]

        store = PostgreSQLStore()
        monkeypatch.setattr(store, "_ensure_initialized", lambda: None)
        monkeypatch.setattr(user_store, "Session", session)
        return store, sessions

    return make


def _sql(stmt: Any) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


def _params(stmt: Any) -> dict[str, Any]:
    return stmt.compile(dialect=postgresql.dialect()).params


def _insert(store: PostgreSQLStore, email: str = "a@x.pl") -> Any:
    return store.insert_user(email=email, password_hash=HASH, role="user", name="N")


# --- mapper -----------------------------------------------------------------


def test_user_to_record_has_no_hash_or_session_version() -> None:
    record = user_to_record(_user())

    assert set(record) == RECORD_KEYS
    assert record == {
        "id": "u-1",
        "tenant_id": TENANT,
        "email": "a@x.pl",
        "role": "admin",
        "name": "Admin",
        "is_active": True,
    }


# --- insert_user --------------------------------------------------------------


def test_insert_writes_active_user_in_current_tenant(store_with: MakeStore) -> None:
    store, sessions = store_with()

    with tenant_context(TENANT):
        record = _insert(store)

    (row,) = sessions[0].added
    assert row.tenant_id == TENANT
    assert row.is_active is True
    assert row.password_hash == HASH
    assert row.email == "a@x.pl"
    assert sessions[0].committed
    assert set(record) == RECORD_KEYS
    assert record["id"] == row.id
    assert len(row.id) == 36


def test_insert_ids_are_new_each_time(store_with: MakeStore) -> None:
    store, _ = store_with()

    with tenant_context(TENANT):
        ids = {_insert(store)["id"], _insert(store)["id"]}

    assert len(ids) == 2


@pytest.mark.parametrize("tenant", [None, ""])
def test_insert_without_tenant_raises_before_any_sql(
    store_with: MakeStore, tenant: str | None
) -> None:
    """Scenario: No tenant set (insert)."""
    store, sessions = store_with()

    with tenant_context(tenant), pytest.raises(PrincipalRequiredError):
        _insert(store)

    assert sessions == []


def test_insert_duplicate_email_maps_to_refused(store_with: MakeStore) -> None:
    """Scenario: Duplicate email gives the same error in any tenant."""
    store, sessions = store_with(error=_integrity("23505", "uq_users_email"))

    with tenant_context(TENANT), pytest.raises(UserCreateRefusedError) as first:
        _insert(store)
    with tenant_context("t-b"), pytest.raises(UserCreateRefusedError) as second:
        _insert(store)

    assert str(first.value) == str(second.value)
    assert "a@x.pl" not in str(first.value)
    assert all(s.rolled_back and not s.committed for s in sessions)


@pytest.mark.parametrize(
    ("sqlstate", "constraint"),
    [("23505", "users_pkey"), ("23514", "ck_users_email_normalised"), ("23505", None)],
)
def test_insert_other_integrity_errors_are_not_mapped(
    store_with: MakeStore, sqlstate: str, constraint: str | None
) -> None:
    """Scenario: Other integrity errors are not mapped."""
    error = _integrity(sqlstate, constraint)
    store, sessions = store_with(error=error)

    with tenant_context(TENANT), pytest.raises(IntegrityError) as caught:
        _insert(store)

    assert caught.value is error
    assert not isinstance(caught.value, UserCreateRefusedError)
    assert sessions[0].rolled_back


def test_insert_integrity_error_without_driver_details_is_not_mapped(
    store_with: MakeStore,
) -> None:
    error = IntegrityError("INSERT", {}, Exception("boom"))
    store, _ = store_with(error=error)

    with tenant_context(TENANT), pytest.raises(IntegrityError):
        _insert(store)


def test_insert_operational_error_propagates_and_rolls_back(store_with: MakeStore) -> None:
    error = OperationalError("INSERT", {}, Exception("down"))
    store, sessions = store_with(error=error)

    with tenant_context(TENANT), pytest.raises(OperationalError):
        _insert(store)

    assert sessions[0].rolled_back


# --- list_users ---------------------------------------------------------------


def test_list_users_filters_tenant_orders_by_email_and_hides_hash(
    store_with: MakeStore,
) -> None:
    """Scenario: List shows no foreign rows (query shape)."""
    store, sessions = store_with(rows=[_user(id="u-1"), _user(id="u-2", email="b@x.pl")])

    with tenant_context(TENANT):
        records = store.list_users()

    (stmt,) = sessions[0].statements
    sql = _sql(stmt)
    assert "users.tenant_id = %(tenant_id_1)s" in sql
    assert "ORDER BY users.email" in sql
    assert _params(stmt)["tenant_id_1"] == TENANT
    assert [r["email"] for r in records] == ["a@x.pl", "b@x.pl"]
    assert all(set(r) == RECORD_KEYS for r in records)


@pytest.mark.parametrize("tenant", [None, ""])
def test_list_users_without_tenant_returns_empty(store_with: MakeStore, tenant: str | None) -> None:
    """Scenario: No tenant set (list)."""
    store, _ = store_with(rows=[_user()])

    with tenant_context(tenant):
        assert store.list_users() == []


def test_list_users_db_error_propagates(store_with: MakeStore) -> None:
    store, _ = store_with(error=OperationalError("SELECT", {}, Exception("down")))

    with tenant_context(TENANT), pytest.raises(OperationalError):
        store.list_users()


# --- find_active_admin ----------------------------------------------------------


def test_find_active_admin_filters_tenant_role_and_active(store_with: MakeStore) -> None:
    """Scenario: Actor lookup finds only an active admin of the tenant (query shape)."""
    store, sessions = store_with(rows=[_user()])

    with tenant_context(TENANT):
        record = store.find_active_admin("a@x.pl")

    (stmt,) = sessions[0].statements
    sql, params = _sql(stmt), _params(stmt)
    assert "users.tenant_id = %(tenant_id_1)s" in sql
    assert "users.role = %(role_1)s" in sql
    assert "users.is_active" in sql
    assert "users.email = %(email_1)s" in sql
    assert params == {"tenant_id_1": TENANT, "role_1": "admin", "email_1": "a@x.pl"}
    assert record is not None
    assert set(record) == RECORD_KEYS


def test_find_active_admin_compares_email_exactly(store_with: MakeStore) -> None:
    store, sessions = store_with()

    with tenant_context(TENANT):
        assert store.find_active_admin(" A@X.pl ") is None

    assert _params(sessions[0].statements[0])["email_1"] == " A@X.pl "


@pytest.mark.parametrize("tenant", [None, ""])
def test_find_active_admin_without_tenant_runs_no_sql(
    store_with: MakeStore, tenant: str | None
) -> None:
    """Scenario: No tenant set (actor lookup)."""
    store, sessions = store_with(rows=[_user()])

    with tenant_context(tenant):
        assert store.find_active_admin("a@x.pl") is None

    assert sessions == []
