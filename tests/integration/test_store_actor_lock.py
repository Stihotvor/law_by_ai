"""The acting admin is verified and locked inside the write transaction (issue 245).

Marked ``integration``: the store runs as ``lawbyai_app``; a holder transaction as the
owner role forces the overlap, and a monitor polls ``pg_stat_activity`` until the worker
waits on a lock, so the tests do not depend on timing. Skipped if PostgreSQL is
unreachable.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from threading import Thread
from typing import Any

import pytest
from factories.scratch_db import TENANT_SQL
from sqlalchemy import create_engine, text
from users_helpers import HASH, OwnerSql, app_store, count_email, insert_id, unique_email

from core.security import PrincipalRequiredError, tenant_context
from plugins.relational_db.postgres import PostgreSQLStore

pytestmark = pytest.mark.integration

TENANT_A = "actor-lock-a"
TENANT_B = "actor-lock-b"
_DEACTIVATE_SQL = "UPDATE users SET is_active = false WHERE id = :i"
_LOCK_ADMINS_SQL = (
    "SELECT id FROM users WHERE tenant_id = :t AND role = 'admin' AND is_active "
    "ORDER BY id FOR UPDATE"
)
_BLOCKED_SQL = (
    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
    "AND pid <> pg_backend_pid() AND wait_event_type = 'Lock' "
    "AND query ILIKE :lock AND query ILIKE '%users%'"
)
_BLOCK_TIMEOUT_S = 10.0
_BLOCK_POLL_S = 0.05


@pytest.fixture
def store(postgres_url: str, owner_sql: OwnerSql) -> Iterator[PostgreSQLStore]:
    with app_store(owner_sql, (TENANT_A, TENANT_B)) as s:
        yield s


def _insert(store: PostgreSQLStore, actor_id: str, email: str, tenant: str = TENANT_A) -> Any:
    with tenant_context(tenant):
        return store.insert_user(
            email=email, password_hash=HASH, role="user", name="N", actor_id=actor_id
        )


def _deactivate(store: PostgreSQLStore, user_id: str, actor_id: str) -> bool:
    with tenant_context(TENANT_A):
        return store.deactivate_user(user_id, actor_id=actor_id)


def _start(call: Any, *args: Any) -> tuple[Thread, list[object]]:
    """Run ``call(*args)`` in a thread; its return value or error lands in the list."""
    outcomes: list[object] = []

    def _worker() -> None:
        try:
            outcomes.append(call(*args))
        except Exception as exc:
            outcomes.append(exc)

    thread = Thread(target=_worker, daemon=True)
    thread.start()
    return thread, outcomes


def _wait_until_blocked(postgres_url: str, lock: str, sessions: int = 1) -> None:
    """Poll as the app role until *sessions* others wait on a lock in a *lock* query."""
    engine = create_engine(postgres_url, future=True, isolation_level="AUTOCOMMIT")
    try:
        deadline = time.monotonic() + _BLOCK_TIMEOUT_S
        with engine.connect() as monitor:
            while time.monotonic() < deadline:
                waiting = monitor.execute(text(_BLOCKED_SQL), {"lock": f"%{lock}%"}).scalar_one()
                if waiting == sessions:
                    return
                time.sleep(_BLOCK_POLL_S)
    finally:
        engine.dispose()
    pytest.fail(
        f"{sessions} session(s) did not block on a {lock} query within {_BLOCK_TIMEOUT_S} s"
    )


def _is_active(owner_sql: OwnerSql, user_id: str) -> bool:
    rows = owner_sql(TENANT_A, "SELECT is_active FROM users WHERE id = :i", i=user_id)
    return bool(rows[0][0])


# --- sequential: the actor is not an active admin of the tenant ----------------


def test_insert_with_inactive_actor_is_refused(store: PostgreSQLStore, owner_sql: OwnerSql) -> None:
    actor = insert_id(store, TENANT_A, "admin")
    owner_sql(TENANT_A, _DEACTIVATE_SQL, i=actor)
    email = unique_email("late")

    with pytest.raises(PrincipalRequiredError):
        _insert(store, actor, email)

    assert count_email(owner_sql, TENANT_A, email) == 0


@pytest.mark.parametrize("kind", ["user_role", "other_tenant", "unknown"])
def test_insert_with_an_actor_that_is_not_an_admin_of_the_tenant_is_refused(
    store: PostgreSQLStore, owner_sql: OwnerSql, kind: str
) -> None:
    actor = {
        "user_role": lambda: insert_id(store, TENANT_A, "user"),
        "other_tenant": lambda: insert_id(store, TENANT_B, "admin"),
        "unknown": lambda: "00000000-0000-4000-8000-000000000000",
    }[kind]()
    email = unique_email("nope")

    with pytest.raises(PrincipalRequiredError):
        _insert(store, actor, email)

    assert count_email(owner_sql, TENANT_A, email) == 0


def test_deactivate_user_with_inactive_actor_is_refused(
    store: PostgreSQLStore, owner_sql: OwnerSql
) -> None:
    actor = insert_id(store, TENANT_A, "admin")
    target = insert_id(store, TENANT_A, "user")
    owner_sql(TENANT_A, _DEACTIVATE_SQL, i=actor)

    with pytest.raises(PrincipalRequiredError):
        _deactivate(store, target, actor)

    assert _is_active(owner_sql, target)


def test_deactivate_admin_with_inactive_actor_is_refused(
    store: PostgreSQLStore, owner_sql: OwnerSql
) -> None:
    actor = insert_id(store, TENANT_A, "admin")
    target = insert_id(store, TENANT_A, "admin")
    insert_id(store, TENANT_A, "admin")
    owner_sql(TENANT_A, _DEACTIVATE_SQL, i=actor)

    with pytest.raises(PrincipalRequiredError):
        _deactivate(store, target, actor)

    assert _is_active(owner_sql, target)


# --- two sessions: the actor is deactivated between the check and the write ----


def _race(
    owner_url: str,
    postgres_url: str,
    actor: str,
    start_worker: Any,
    lock: str,
    *,
    commit: bool,
) -> list[object]:
    """Hold an uncommitted deactivation of *actor*, start the write, then end the holder."""
    engine = create_engine(owner_url, future=True)
    try:
        with engine.connect() as conn, conn.begin() as holder:
            conn.execute(text(TENANT_SQL), {"tenant": TENANT_A})
            conn.execute(text(_DEACTIVATE_SQL), {"i": actor})
            thread, outcomes = start_worker()
            _wait_until_blocked(postgres_url, lock)
            if commit:
                holder.commit()
            else:
                holder.rollback()
        thread.join(timeout=30)
    finally:
        engine.dispose()
    assert not thread.is_alive()
    assert len(outcomes) == 1
    return outcomes


def test_insert_waits_for_a_deactivating_actor_then_is_refused(
    store: PostgreSQLStore, owner_sql: OwnerSql, owner_url: str, postgres_url: str
) -> None:
    """The actor deactivation is uncommitted: the insert waits on ``FOR SHARE``, then fails."""
    actor = insert_id(store, TENANT_A, "admin")
    email = unique_email("race")

    (outcome,) = _race(
        owner_url,
        postgres_url,
        actor,
        lambda: _start(_insert, store, actor, email),
        "FOR SHARE",
        commit=True,
    )

    assert isinstance(outcome, PrincipalRequiredError)
    assert count_email(owner_sql, TENANT_A, email) == 0


def test_insert_proceeds_when_the_actor_deactivation_rolls_back(
    store: PostgreSQLStore, owner_sql: OwnerSql, owner_url: str, postgres_url: str
) -> None:
    actor = insert_id(store, TENANT_A, "admin")
    email = unique_email("rollback")

    (outcome,) = _race(
        owner_url,
        postgres_url,
        actor,
        lambda: _start(_insert, store, actor, email),
        "FOR SHARE",
        commit=False,
    )

    assert not isinstance(outcome, Exception)
    assert count_email(owner_sql, TENANT_A, email) == 1


def test_deactivate_user_waits_for_a_deactivating_actor_then_is_refused(
    store: PostgreSQLStore, owner_sql: OwnerSql, owner_url: str, postgres_url: str
) -> None:
    actor = insert_id(store, TENANT_A, "admin")
    target = insert_id(store, TENANT_A, "user")

    (outcome,) = _race(
        owner_url,
        postgres_url,
        actor,
        lambda: _start(_deactivate, store, target, actor),
        "FOR SHARE",
        commit=True,
    )

    assert isinstance(outcome, PrincipalRequiredError)
    assert _is_active(owner_sql, target)


def test_crossed_admin_deactivations_do_not_deadlock(
    store: PostgreSQLStore, owner_sql: OwnerSql, owner_url: str, postgres_url: str
) -> None:
    """A removes B while B removes A: the ordered admin lock queues both, one wins."""
    admin_a = insert_id(store, TENANT_A, "admin")
    admin_b = insert_id(store, TENANT_A, "admin")
    engine = create_engine(owner_url, future=True)
    try:
        with engine.connect() as conn, conn.begin() as holder:
            conn.execute(text(TENANT_SQL), {"tenant": TENANT_A})
            locked = conn.execute(text(_LOCK_ADMINS_SQL), {"t": TENANT_A}).scalars().all()
            assert sorted(locked) == sorted([admin_a, admin_b])
            first, first_out = _start(_deactivate, store, admin_b, admin_a)
            second, second_out = _start(_deactivate, store, admin_a, admin_b)
            _wait_until_blocked(postgres_url, "FOR UPDATE", sessions=2)
            holder.rollback()
        first.join(timeout=30)
        second.join(timeout=30)
    finally:
        engine.dispose()

    assert not first.is_alive()
    assert not second.is_alive()
    outcomes = first_out + second_out
    assert len(outcomes) == 2
    assert sorted(type(o).__name__ for o in outcomes) == ["PrincipalRequiredError", "bool"]
    assert [o for o in outcomes if o is True] == [True]
    active = owner_sql(
        TENANT_A, "SELECT count(*) FROM users WHERE tenant_id = :t AND is_active", t=TENANT_A
    )
    assert int(active[0][0]) == 1
