"""``PostgreSQLStore.deactivate_user`` (T3) with a scripted fake session.

Unit tests: check order, lock shape and transaction handling without a database.
The real queries, the trigger and the two-session race run in
``tests/integration/test_store_deactivate.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError

from core.security import PrincipalRequiredError, tenant_context
from core.users.errors import LastAdminError, SelfDeactivationError, UserNotFoundError
from plugins.relational_db import user_store
from plugins.relational_db.postgres import PostgreSQLStore

TENANT = "t-a"
ACTOR = "admin-1"


class _Result:
    """One scripted result: a list of scalars (role, ids)."""

    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def one_or_none(self) -> Any:
        return self.rows[0] if self.rows else None

    def scalar_one_or_none(self) -> Any:
        return self.rows[0] if self.rows else None

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[Any]:
        return self.rows


class FakeSession:
    """Returns the scripted results in order; records statements and the outcome."""

    def __init__(self, results: list[list[Any]], error: Exception | None) -> None:
        self.results, self.error = list(results), error
        self.statements: list[Any] = []
        self.committed = self.rolled_back = False

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def begin(self) -> _Tx:
        return _Tx(self)

    def execute(self, stmt: Any) -> _Result:
        if self.error is not None:
            raise self.error
        self.statements.append(stmt)
        return _Result(self.results.pop(0) if self.results else [])


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
        results: list[list[Any]] | None = None, error: Exception | None = None
    ) -> tuple[PostgreSQLStore, list[FakeSession]]:
        sessions: list[FakeSession] = []

        def session(_engine: object) -> FakeSession:
            sessions.append(FakeSession(results or [], error))
            return sessions[-1]

        store = PostgreSQLStore()
        monkeypatch.setattr(store, "_ensure_initialized", lambda: None)
        monkeypatch.setattr(user_store, "Session", session)
        return store, sessions

    return make


def _sql(stmt: Any) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


def _params(stmt: Any) -> dict[str, Any]:
    return dict(stmt.compile(dialect=postgresql.dialect()).params)


def _deactivate(store: PostgreSQLStore, user_id: str, actor_id: str = ACTOR) -> bool:
    with tenant_context(TENANT):
        return store.deactivate_user(user_id, actor_id=actor_id)


# --- check order ----------------------------------------------------------------


@pytest.mark.parametrize("tenant", [None, ""])
def test_no_tenant_raises_before_any_sql(store_with: MakeStore, tenant: str | None) -> None:
    """Scenario: No tenant set."""
    store, sessions = store_with()

    with tenant_context(tenant), pytest.raises(PrincipalRequiredError):
        store.deactivate_user("u-2", actor_id=ACTOR)

    assert sessions == []


def test_missing_or_foreign_target_raises_not_found(store_with: MakeStore) -> None:
    """Scenario: Foreign or unknown id (the tenant predicate hides foreign rows)."""
    store, sessions = store_with(results=[[]])

    with pytest.raises(UserNotFoundError):
        _deactivate(store, "u-foreign")

    (read,) = sessions[0].statements
    sql = _sql(read)
    assert "users.tenant_id = %(tenant_id_1)s" in sql
    assert "FOR UPDATE" not in sql
    assert _params(read) == {"id_1": "u-foreign", "tenant_id_1": TENANT}
    assert sessions[0].rolled_back
    assert not sessions[0].committed


def test_self_raises_before_any_lock(store_with: MakeStore) -> None:
    """Scenario: Self and last admin (self is checked first, inside the transaction)."""
    store, sessions = store_with(results=[["admin"], [ACTOR]])

    with pytest.raises(SelfDeactivationError):
        _deactivate(store, ACTOR)

    assert len(sessions[0].statements) == 1
    assert sessions[0].rolled_back


# --- admin target -------------------------------------------------------------


def test_admin_target_locks_admin_set_first_without_limit(store_with: MakeStore) -> None:
    store, sessions = store_with(results=[["admin"], ["u-2", ACTOR], ["u-2"]])

    assert _deactivate(store, "u-2") is True

    _read, lock, _upd, _audit = sessions[0].statements
    sql = _sql(lock)
    assert sql.rstrip().endswith("FOR UPDATE")
    assert "ORDER BY users.id" in sql
    assert "LIMIT" not in sql
    assert "SKIP LOCKED" not in sql
    assert "users.is_active" in sql
    assert _params(lock) == {"tenant_id_1": TENANT, "role_1": "admin"}
    assert sessions[0].committed


def test_sole_admin_target_raises_last_admin(store_with: MakeStore) -> None:
    """Scenario: Self and last admin (another admin is the sole active admin)."""
    store, sessions = store_with(results=[["admin"], ["u-2"]])

    with pytest.raises(LastAdminError):
        _deactivate(store, "u-2", actor_id="not-an-admin")

    assert len(sessions[0].statements) == 2
    assert sessions[0].rolled_back
    assert not sessions[0].committed


def test_admin_set_without_target_is_a_noop(store_with: MakeStore) -> None:
    """A racing session deactivated the target after the read: the lock skips it, 0 rows."""
    store, _ = store_with(results=[["admin"], [], []])

    assert _deactivate(store, "u-2") is False


def test_inactive_admin_target_is_a_noop(store_with: MakeStore) -> None:
    """Scenario: Already inactive target (one other admin is left; no LastAdminError)."""
    store, sessions = store_with(results=[["admin"], [ACTOR], []])

    assert _deactivate(store, "u-2") is False

    assert len(sessions[0].statements) == 3
    assert sessions[0].committed


@pytest.mark.parametrize("locked", [[], [ACTOR], ["admin-9"]])
def test_inactive_admin_target_never_raises_last_admin(
    store_with: MakeStore, locked: list[str]
) -> None:
    """An inactive admin target is outside the locked set: ``False`` even with one row or fewer."""
    store, sessions = store_with(results=[["admin"], locked, []])

    assert _deactivate(store, "u-inactive") is False

    assert sessions[0].committed
    assert not sessions[0].rolled_back


# --- user target --------------------------------------------------------------


def test_user_target_locks_only_target(store_with: MakeStore) -> None:
    store, sessions = store_with(results=[["user"], ["u-3"], ["u-3"]])

    assert _deactivate(store, "u-3") is True

    _read, lock, _upd, _audit = sessions[0].statements
    sql = _sql(lock)
    assert sql.rstrip().endswith("FOR UPDATE")
    assert "role" not in sql.split("WHERE", 1)[1]
    assert _params(lock) == {"id_1": "u-3", "tenant_id_1": TENANT}


# --- update -------------------------------------------------------------------


def test_update_is_tenant_scoped_and_only_flips_is_active(store_with: MakeStore) -> None:
    """Scenario: Old cookie fails (the DB trigger bumps session_version, not the store)."""
    store, sessions = store_with(results=[["user"], ["u-3"], ["u-3"]])

    _deactivate(store, "u-3")

    upd = sessions[0].statements[2]
    sql = _sql(upd)
    assert sql.startswith("UPDATE users SET is_active=")
    assert "session_version" not in sql
    assert "users.tenant_id = %(tenant_id_1)s" in sql
    assert "users.is_active" in sql.split("WHERE", 1)[1]
    assert "RETURNING users.id" in sql
    params = _params(upd)
    assert params["id_1"] == "u-3"
    assert params["tenant_id_1"] == TENANT
    assert params["is_active"] is False


def test_update_of_zero_rows_returns_false(store_with: MakeStore) -> None:
    """Scenario: Already inactive target."""
    store, sessions = store_with(results=[["user"], [], []])

    assert _deactivate(store, "u-3") is False
    assert sessions[0].committed


def test_db_error_propagates_and_rolls_back(store_with: MakeStore) -> None:
    error = OperationalError("SELECT", {}, Exception("down"))
    store, sessions = store_with(error=error)

    with pytest.raises(OperationalError) as caught:
        _deactivate(store, "u-2")

    assert caught.value is error
    assert sessions[0].rolled_back


# --- audit --------------------------------------------------------------------


def test_changed_row_appends_one_audit_row_in_the_same_transaction(store_with: MakeStore) -> None:
    store, sessions = store_with(results=[["user"], ["u-3"], ["u-3"]])

    assert _deactivate(store, "u-3") is True

    audit = sessions[0].statements[-1]
    assert _sql(audit).startswith("INSERT INTO admin_action_audit")
    assert _params(audit) == {
        "tenant_id": TENANT,
        "actor_id": ACTOR,
        "action": "deactivate_user",
        "target_id": "u-3",
    }
    assert sessions[0].committed


def test_noop_writes_no_audit_row(store_with: MakeStore) -> None:
    store, sessions = store_with(results=[["user"], ["u-3"], []])

    assert _deactivate(store, "u-3") is False

    assert len(sessions[0].statements) == 3
    assert all("admin_action_audit" not in _sql(s) for s in sessions[0].statements)


def test_refusal_writes_no_audit_row(store_with: MakeStore) -> None:
    store, sessions = store_with(results=[["admin"], ["u-2"]])

    with pytest.raises(LastAdminError):
        _deactivate(store, "u-2", actor_id="other")

    assert all("admin_action_audit" not in _sql(s) for s in sessions[0].statements)
