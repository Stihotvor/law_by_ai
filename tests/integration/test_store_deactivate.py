"""``PostgreSQLStore.deactivate_user`` (T3) against a live PostgreSQL.

Marked ``integration``: runs as ``lawbyai_app``. Rows live in two test tenants
with unique emails; the owner ``lawbyai_owner`` deletes them afterwards. Skipped
if PostgreSQL is unreachable.
"""

from __future__ import annotations

from collections.abc import Iterator
from threading import Thread

import pytest
from factories.scratch_db import TENANT_SQL
from sqlalchemy import create_engine, text
from users_helpers import OwnerSql, app_store, insert_id

from core.security import PrincipalRequiredError, tenant_context
from core.users.errors import LastAdminError, SelfDeactivationError, UserNotFoundError
from plugins.relational_db.postgres import PostgreSQLStore

pytestmark = pytest.mark.integration

TENANT_A = "store-deact-a"
TENANT_B = "store-deact-b"
MISSING_ID = "00000000-0000-4000-8000-000000000000"
_LOCK_ADMINS_SQL = (
    "SELECT id FROM users WHERE tenant_id = :t AND role = 'admin' AND is_active "
    "ORDER BY id FOR UPDATE"
)
_DEACTIVATE_SQL = "UPDATE users SET is_active = false WHERE id = :i"


@pytest.fixture
def store(postgres_url: str, owner_sql: OwnerSql) -> Iterator[PostgreSQLStore]:
    """Real store as the app role; the owner deletes the rows of both test tenants."""
    with app_store(owner_sql, (TENANT_A, TENANT_B)) as s:
        yield s


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
    admin = insert_id(store, TENANT_A, "admin")
    foreign = insert_id(store, TENANT_B, "user")
    before = _state(owner_sql, TENANT_B, foreign)

    with pytest.raises(UserNotFoundError) as foreign_err:
        _deactivate(store, TENANT_A, foreign, admin)
    with pytest.raises(UserNotFoundError) as missing_err:
        _deactivate(store, TENANT_A, MISSING_ID, admin)

    assert str(foreign_err.value) == str(missing_err.value)
    assert _state(owner_sql, TENANT_B, foreign) == before


def test_already_inactive_is_noop_without_bump(store: PostgreSQLStore, owner_sql: OwnerSql) -> None:
    """Scenario: Already inactive target (QA-021)."""
    admin = insert_id(store, TENANT_A, "admin")
    user = insert_id(store, TENANT_A, "user")
    assert _deactivate(store, TENANT_A, user, admin) is True
    _, version = _state(owner_sql, TENANT_A, user)

    assert _deactivate(store, TENANT_A, user, admin) is False

    assert _state(owner_sql, TENANT_A, user) == (False, version)


def test_deactivate_changes_session_version(store: PostgreSQLStore, owner_sql: OwnerSql) -> None:
    """Scenario: Old cookie fails."""
    admin = insert_id(store, TENANT_A, "admin")
    user = insert_id(store, TENANT_A, "user")
    _, version = _state(owner_sql, TENANT_A, user)

    assert _deactivate(store, TENANT_A, user, admin) is True

    is_active, new_version = _state(owner_sql, TENANT_A, user)
    assert is_active is False
    assert new_version != version


def test_self_deactivation_is_refused(store: PostgreSQLStore, owner_sql: OwnerSql) -> None:
    """Scenario: Self and last admin, self part (QA-024, QA-026): self is checked first."""
    admin = insert_id(store, TENANT_A, "admin")

    with pytest.raises(SelfDeactivationError):
        _deactivate(store, TENANT_A, admin, admin)

    assert _state(owner_sql, TENANT_A, admin)[0] is True


def test_last_admin_is_refused(store: PostgreSQLStore, owner_sql: OwnerSql) -> None:
    """Scenario: Self and last admin, last admin part (QA-027)."""
    admin1 = insert_id(store, TENANT_A, "admin")
    admin2 = insert_id(store, TENANT_A, "admin")
    assert _deactivate(store, TENANT_A, admin2, admin1) is True

    with pytest.raises(LastAdminError):
        _deactivate(store, TENANT_A, admin1, admin2)

    assert _active_admins(owner_sql, TENANT_A) == 1
    assert _state(owner_sql, TENANT_A, admin1)[0] is True


def _start_deactivate(
    store: PostgreSQLStore, target: str, actor: str
) -> tuple[Thread, list[object]]:
    """Run ``deactivate_user`` in a thread; its return value or error lands in the list."""
    outcomes: list[object] = []

    def _worker() -> None:
        # A new thread does not inherit context variables: _deactivate enters the tenant.
        try:
            outcomes.append(_deactivate(store, TENANT_A, target, actor))
        except Exception as exc:
            outcomes.append(exc)

    thread = Thread(target=_worker, daemon=True)
    thread.start()
    return thread, outcomes


def test_two_sessions_race_keeps_one_admin(
    store: PostgreSQLStore, owner_sql: OwnerSql, owner_url: str
) -> None:
    """Scenario: Two sessions race (QA-025, QA-028), forced overlap.

    A holder transaction (owner role, tenant set like the store does) locks the
    tenant's active admins, so ``deactivate_user(A1)`` must wait on its
    ``FOR UPDATE``. The holder then deactivates A2 and commits. PostgreSQL rechecks
    the locked rows: the store's locked set is [A1], one row holding the target,
    so it raises ``LastAdminError``.

    Without ``.with_for_update()`` in ``_lock_admins_or_refuse`` the store reads
    [A1, A2] from its snapshot without waiting, and its UPDATE of A1 only waits on
    the holder's row lock; after the commit it deactivates A1 and returns True.
    The test then fails: no ``LastAdminError`` and zero active admins.
    """
    admin1 = insert_id(store, TENANT_A, "admin")
    admin2 = insert_id(store, TENANT_A, "admin")
    engine = create_engine(owner_url, future=True)
    try:
        with engine.connect() as conn, conn.begin() as holder:
            conn.execute(text(TENANT_SQL), {"tenant": TENANT_A})
            locked = conn.execute(text(_LOCK_ADMINS_SQL), {"t": TENANT_A}).scalars().all()
            assert sorted(locked) == sorted([admin1, admin2])

            thread, outcomes = _start_deactivate(store, admin1, admin2)
            thread.join(timeout=1)
            assert thread.is_alive(), "deactivate_user did not wait for the admin row locks"

            conn.execute(text(_DEACTIVATE_SQL), {"i": admin2})
            holder.commit()
        thread.join(timeout=30)
    finally:
        engine.dispose()

    assert not thread.is_alive()
    assert len(outcomes) == 1
    assert isinstance(outcomes[0], LastAdminError)
    assert _active_admins(owner_sql, TENANT_A) == 1
    assert _state(owner_sql, TENANT_A, admin1)[0] is True


@pytest.mark.parametrize("tenant", [None, ""])
def test_no_tenant_changes_nothing(
    store: PostgreSQLStore, owner_sql: OwnerSql, tenant: str | None
) -> None:
    """Scenario: No tenant set."""
    admin = insert_id(store, TENANT_A, "admin")
    user = insert_id(store, TENANT_A, "user")
    before = _state(owner_sql, TENANT_A, user)

    with pytest.raises(PrincipalRequiredError):
        _deactivate(store, tenant, user, admin)

    assert _state(owner_sql, TENANT_A, user) == before
