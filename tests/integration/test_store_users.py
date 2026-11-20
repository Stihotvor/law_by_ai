"""User port of the PostgreSQL store (T2): insert, list and actor lookup.

Marked ``integration``: runs against a live PostgreSQL as ``lawbyai_app``. Rows
live in two test tenants with unique emails; the owner ``lawbyai_owner`` deletes
them afterwards. Skipped if PostgreSQL is unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from core.security import PrincipalRequiredError, tenant_context
from core.users.errors import UserCreateRefusedError
from plugins.relational_db.postgres import PostgreSQLStore

pytestmark = pytest.mark.integration

TENANT_A = "store-users-a"
TENANT_B = "store-users-b"
HASH = "$2b$12$abcdefghijklmnopqrstuuMlUrPIN6lFpvSu7Nvt3d3PZ7QvYb9W2"
RECORD_KEYS = {"id", "tenant_id", "email", "role", "name", "is_active"}
OwnerSql = Callable[..., list[Any]]


@pytest.fixture
def store(postgres_url: str, owner_sql: OwnerSql) -> Iterator[PostgreSQLStore]:
    """Real store as the app role; the owner deletes the rows of both test tenants."""
    s = PostgreSQLStore()
    s.initialize()
    yield s
    s.close()
    for tenant in (TENANT_A, TENANT_B):
        owner_sql(tenant, "DELETE FROM users WHERE tenant_id = :t", t=tenant)


def _email(prefix: str = "u") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@x.pl"


def _insert(
    store: PostgreSQLStore, tenant: str | None, email: str, role: str = "user"
) -> dict[str, Any]:
    with tenant_context(tenant):
        record = store.insert_user(email=email, password_hash=HASH, role=role, name="N")
    return dict(record)


def _count(owner_sql: OwnerSql, tenant: str, email: str) -> int:
    rows = owner_sql(tenant, "SELECT count(*) FROM users WHERE email = :e", e=email)
    return int(rows[0][0])


# --- insert -------------------------------------------------------------------


def test_insert_creates_active_user_with_hash(store: PostgreSQLStore, owner_sql: OwnerSql) -> None:
    email = _email()

    record = _insert(store, TENANT_A, email)

    assert set(record) == RECORD_KEYS
    assert record["tenant_id"] == TENANT_A
    assert record["is_active"] is True
    rows = owner_sql(TENANT_A, "SELECT password_hash FROM users WHERE id = :i", i=record["id"])
    assert rows[0][0] == HASH


def test_insert_duplicate_email_same_error_in_any_tenant(
    store: PostgreSQLStore, owner_sql: OwnerSql
) -> None:
    """Scenario: Duplicate email gives the same error in any tenant."""
    email = _email("dup")
    _insert(store, TENANT_A, email)

    with pytest.raises(UserCreateRefusedError) as in_a:
        _insert(store, TENANT_A, email)
    with pytest.raises(UserCreateRefusedError) as in_b:
        _insert(store, TENANT_B, email)

    assert str(in_a.value) == str(in_b.value)
    assert _count(owner_sql, TENANT_A, email) == 1
    assert _count(owner_sql, TENANT_B, email) == 0


def test_insert_other_integrity_error_is_not_mapped(store: PostgreSQLStore) -> None:
    """Scenario: Other integrity errors are not mapped (``ck_users_email_normalised``)."""
    with pytest.raises(IntegrityError) as caught:
        _insert(store, TENANT_A, f"UPPER-{uuid.uuid4().hex[:8]}@X.pl")

    assert not isinstance(caught.value, UserCreateRefusedError)
    assert "ck_users_email_normalised" in str(caught.value)


def test_insert_store_usable_after_refused_insert(store: PostgreSQLStore) -> None:
    email = _email("dup")
    _insert(store, TENANT_A, email)
    with pytest.raises(UserCreateRefusedError):
        _insert(store, TENANT_A, email)

    assert _insert(store, TENANT_A, _email())["tenant_id"] == TENANT_A


# --- list ---------------------------------------------------------------------


def test_list_shows_no_foreign_rows(store: PostgreSQLStore) -> None:
    """Scenario: List shows no foreign rows."""
    own = [_insert(store, TENANT_A, _email(p))["email"] for p in ("zz", "aa", "mm")]
    foreign = _insert(store, TENANT_B, _email("bb"))["email"]

    with tenant_context(TENANT_A):
        records = store.list_users()

    emails = [r["email"] for r in records]
    assert all(r["tenant_id"] == TENANT_A for r in records)
    assert emails == sorted(emails)
    assert set(own) <= set(emails)
    assert foreign not in emails
    assert all(set(r) == RECORD_KEYS for r in records)


# --- find_active_admin ----------------------------------------------------------


def test_actor_lookup_finds_only_active_admin_of_tenant(
    store: PostgreSQLStore, owner_sql: OwnerSql
) -> None:
    """Scenario: Actor lookup finds only an active admin of the tenant."""
    admin = _insert(store, TENANT_A, _email("admin"), role="admin")
    inactive = _insert(store, TENANT_A, _email("inactive"), role="admin")
    owner_sql(TENANT_A, "UPDATE users SET is_active = false WHERE id = :i", i=inactive["id"])
    user = _insert(store, TENANT_A, _email("user"))
    foreign = _insert(store, TENANT_B, _email("foreign"), role="admin")

    with tenant_context(TENANT_A):
        found = store.find_active_admin(admin["email"])
        others = [store.find_active_admin(r["email"]) for r in (inactive, user, foreign)]

    assert found is not None
    assert found["id"] == admin["id"]
    assert set(found) == RECORD_KEYS
    assert others == [None, None, None]


# --- leak: no tenant set ---------------------------------------------------------


def test_leak_no_tenant_set(store: PostgreSQLStore, owner_sql: OwnerSql) -> None:
    """Scenario: No tenant set."""
    admin = _insert(store, TENANT_A, _email("admin"), role="admin")
    email = _email("ghost")

    with tenant_context(None):
        listed = store.list_users()
        with pytest.raises(PrincipalRequiredError):
            store.insert_user(email=email, password_hash=HASH, role="user", name="N")
        found = store.find_active_admin(admin["email"])

    assert listed == []
    assert found is None
    for tenant in (TENANT_A, TENANT_B):
        assert _count(owner_sql, tenant, email) == 0
