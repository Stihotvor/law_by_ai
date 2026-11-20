"""``PostgreSQLStore.deactivate_user`` (T3) against a live PostgreSQL.

Marked ``integration``: runs as ``lawbyai_app``. Rows live in two test tenants
with unique emails; the owner ``lawbyai_owner`` deletes them afterwards. Skipped
if PostgreSQL is unreachable.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from core.security import PrincipalRequiredError, tenant_context
from core.users.errors import LastAdminError, SelfDeactivationError, UserNotFoundError
from plugins.relational_db.postgres import PostgreSQLStore

pytestmark = pytest.mark.integration

TENANT_A = "store-deact-a"
TENANT_B = "store-deact-b"
HASH = "$2b$12$abcdefghijklmnopqrstuuMlUrPIN6lFpvSu7Nvt3d3PZ7QvYb9W2"
MISSING_ID = "00000000-0000-4000-8000-000000000000"
OwnerSql = Callable[..., list[Any]]


@pytest.fixture
def store(postgres_url: str, owner_sql: OwnerSql) -> Iterator[PostgreSQLStore]:
    """Real store as the app role; the owner deletes the rows of both test tenants."""
    for tenant in (TENANT_A, TENANT_B):
        owner_sql(tenant, "DELETE FROM users WHERE tenant_id = :t", t=tenant)
    s = PostgreSQLStore()
    s.initialize()
    yield s
    s.close()
    for tenant in (TENANT_A, TENANT_B):
        owner_sql(tenant, "DELETE FROM users WHERE tenant_id = :t", t=tenant)


def _insert(store: PostgreSQLStore, tenant: str, role: str = "user") -> str:
    email = f"{role}-{uuid.uuid4().hex[:12]}@x.pl"
    with tenant_context(tenant):
        return store.insert_user(email=email, password_hash=HASH, role=role, name="N")["id"]


def _state(owner_sql: OwnerSql, tenant: str, user_id: str) -> tuple[bool, int]:
    sql = "SELECT is_active, session_version FROM users WHERE id = :i"
    rows = owner_sql(tenant, sql, i=user_id)
    return bool(rows[0][0]), int(rows[0][1])


def _active_admins(owner_sql: OwnerSql, tenant: str) -> int:
    sql = "SELECT count(*) FROM users WHERE tenant_id = :t AND role = 'admin' AND is_active"
    return int(owner_sql(tenant, sql, t=tenant)[0][0])


def _deactivate(store: PostgreSQLStore, tenant: str | None, user_id: str, actor_id: str) -> bool:
    with tenant_context(tenant):
        return store.deactivate_user(user_id, actor_id=actor_id)


def test_foreign_or_unknown_id_is_not_found(store: PostgreSQLStore, owner_sql: OwnerSql) -> None:
    """Scenario: Foreign or unknown id (QA-022, QA-023)."""
    admin = _insert(store, TENANT_A, "admin")
    foreign = _insert(store, TENANT_B, "user")
    before = _state(owner_sql, TENANT_B, foreign)

    with pytest.raises(UserNotFoundError) as foreign_err:
        _deactivate(store, TENANT_A, foreign, admin)
    with pytest.raises(UserNotFoundError) as missing_err:
        _deactivate(store, TENANT_A, MISSING_ID, admin)

    assert str(foreign_err.value) == str(missing_err.value)
    assert _state(owner_sql, TENANT_B, foreign) == before


def test_already_inactive_is_noop_without_bump(store: PostgreSQLStore, owner_sql: OwnerSql) -> None:
    """Scenario: Already inactive target (QA-021)."""
    admin = _insert(store, TENANT_A, "admin")
    user = _insert(store, TENANT_A, "user")
    assert _deactivate(store, TENANT_A, user, admin) is True
    _, version = _state(owner_sql, TENANT_A, user)

    assert _deactivate(store, TENANT_A, user, admin) is False

    assert _state(owner_sql, TENANT_A, user) == (False, version)


def test_deactivate_changes_session_version(store: PostgreSQLStore, owner_sql: OwnerSql) -> None:
    """Scenario: Old cookie fails."""
    admin = _insert(store, TENANT_A, "admin")
    user = _insert(store, TENANT_A, "user")
    _, version = _state(owner_sql, TENANT_A, user)

    assert _deactivate(store, TENANT_A, user, admin) is True

    is_active, new_version = _state(owner_sql, TENANT_A, user)
    assert is_active is False
    assert new_version != version


def test_self_then_last_admin(store: PostgreSQLStore, owner_sql: OwnerSql) -> None:
    """Scenario: Self and last admin (QA-024, QA-026, QA-027)."""
    admin1 = _insert(store, TENANT_A, "admin")

    with pytest.raises(SelfDeactivationError):
        _deactivate(store, TENANT_A, admin1, admin1)
    assert _state(owner_sql, TENANT_A, admin1)[0] is True

    admin2 = _insert(store, TENANT_A, "admin")
    assert _deactivate(store, TENANT_A, admin2, admin1) is True
    with pytest.raises(LastAdminError):
        _deactivate(store, TENANT_A, admin1, admin2)

    assert _active_admins(owner_sql, TENANT_A) == 1
    assert _state(owner_sql, TENANT_A, admin1)[0] is True


def test_two_sessions_race_keeps_one_admin(store: PostgreSQLStore, owner_sql: OwnerSql) -> None:
    """Scenario: Two sessions race (QA-025, QA-028)."""
    admin1 = _insert(store, TENANT_A, "admin")
    admin2 = _insert(store, TENANT_A, "admin")
    barrier = threading.Barrier(2)
    outcomes: list[object] = []

    def _worker(target: str, actor: str) -> None:
        # A new thread does not inherit context variables: enter the tenant here.
        barrier.wait()
        try:
            outcomes.append(_deactivate(store, TENANT_A, target, actor))
        except Exception as exc:
            outcomes.append(exc)

    threads = [
        threading.Thread(target=_worker, args=(admin2, admin1)),
        threading.Thread(target=_worker, args=(admin1, admin2)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(type(o).__name__ for o in outcomes) == ["LastAdminError", "bool"]
    assert True in outcomes
    assert _active_admins(owner_sql, TENANT_A) == 1


def test_no_tenant_changes_nothing(store: PostgreSQLStore, owner_sql: OwnerSql) -> None:
    """Scenario: No tenant set."""
    admin = _insert(store, TENANT_A, "admin")
    user = _insert(store, TENANT_A, "user")
    before = _state(owner_sql, TENANT_A, user)

    for tenant in (None, ""):
        with pytest.raises(PrincipalRequiredError):
            _deactivate(store, tenant, user, admin)

    assert _state(owner_sql, TENANT_A, user) == before
