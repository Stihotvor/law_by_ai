"""User port of the PostgreSQL store (T2): insert, list and actor lookup.

Marked ``integration``: runs against a live PostgreSQL as ``lawbyai_app``. Rows
live in two test tenants with unique emails; the owner ``lawbyai_owner`` deletes
them afterwards. Skipped if PostgreSQL is unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy.exc import IntegrityError
from users_helpers import (
    HASH,
    OwnerSql,
    app_store,
    count_email,
    insert_record,
    unique_email,
)

from core.security import PrincipalRequiredError, tenant_context
from core.users.errors import UserCreateRefusedError
from plugins.relational_db.postgres import PostgreSQLStore

pytestmark = pytest.mark.integration

TENANT_A = "store-users-a"
TENANT_B = "store-users-b"
RECORD_KEYS = {"id", "tenant_id", "email", "role", "name", "is_active"}


@pytest.fixture
def store(postgres_url: str, owner_sql: OwnerSql) -> Iterator[PostgreSQLStore]:
    """Real store as the app role; the owner deletes the rows of both test tenants."""
    with app_store(owner_sql, (TENANT_A, TENANT_B)) as s:
        yield s


# --- insert -------------------------------------------------------------------


def test_insert_creates_active_user_with_hash(store: PostgreSQLStore, owner_sql: OwnerSql) -> None:
    email = unique_email()

    record = insert_record(store, TENANT_A, email)

    assert set(record) == RECORD_KEYS
    assert record["tenant_id"] == TENANT_A
    assert record["is_active"] is True
    rows = owner_sql(TENANT_A, "SELECT password_hash FROM users WHERE id = :i", i=record["id"])
    assert rows[0][0] == HASH


def test_insert_duplicate_email_same_error_in_any_tenant(
    store: PostgreSQLStore, owner_sql: OwnerSql
) -> None:
    """Scenario: Duplicate email gives the same error in any tenant."""
    email = unique_email("dup")
    insert_record(store, TENANT_A, email)

    with pytest.raises(UserCreateRefusedError) as in_a:
        insert_record(store, TENANT_A, email)
    with pytest.raises(UserCreateRefusedError) as in_b:
        insert_record(store, TENANT_B, email)

    assert str(in_a.value) == str(in_b.value)
    assert count_email(owner_sql, TENANT_A, email) == 1
    assert count_email(owner_sql, TENANT_B, email) == 0


def test_insert_other_integrity_error_is_not_mapped(store: PostgreSQLStore) -> None:
    """Scenario: Other integrity errors are not mapped (``ck_users_email_normalised``)."""
    with pytest.raises(IntegrityError) as caught:
        insert_record(store, TENANT_A, f"UPPER-{uuid.uuid4().hex[:8]}@X.pl")

    assert not isinstance(caught.value, UserCreateRefusedError)
    assert "ck_users_email_normalised" in str(caught.value)


def test_insert_store_usable_after_refusedinsert_record(store: PostgreSQLStore) -> None:
    email = unique_email("dup")
    insert_record(store, TENANT_A, email)
    with pytest.raises(UserCreateRefusedError):
        insert_record(store, TENANT_A, email)

    assert insert_record(store, TENANT_A, unique_email())["tenant_id"] == TENANT_A


# --- list ---------------------------------------------------------------------


def test_list_shows_no_foreign_rows(store: PostgreSQLStore) -> None:
    """Scenario: List shows no foreign rows."""
    own = [insert_record(store, TENANT_A, unique_email(p))["email"] for p in ("zz", "aa", "mm")]
    foreign = insert_record(store, TENANT_B, unique_email("bb"))["email"]

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
    admin = insert_record(store, TENANT_A, unique_email("admin"), role="admin")
    inactive = insert_record(store, TENANT_A, unique_email("inactive"), role="admin")
    owner_sql(TENANT_A, "UPDATE users SET is_active = false WHERE id = :i", i=inactive["id"])
    user = insert_record(store, TENANT_A, unique_email("user"))
    foreign = insert_record(store, TENANT_B, unique_email("foreign"), role="admin")

    with tenant_context(TENANT_A):
        found = store.find_active_admin(admin["email"])
        others = [store.find_active_admin(r["email"]) for r in (inactive, user, foreign)]

    assert found is not None
    assert found["id"] == admin["id"]
    assert set(found) == RECORD_KEYS
    assert others == [None, None, None]


# --- leak: no tenant set ---------------------------------------------------------


@pytest.mark.parametrize("tenant", [None, ""])
def test_no_tenant_list_is_empty(store: PostgreSQLStore, tenant: str | None) -> None:
    """Scenario: No tenant set (list)."""
    insert_record(store, TENANT_A, unique_email("admin"), role="admin")

    with tenant_context(tenant):
        assert store.list_users() == []


@pytest.mark.parametrize("tenant", [None, ""])
def test_no_tenant_insert_is_refused(
    store: PostgreSQLStore, owner_sql: OwnerSql, tenant: str | None
) -> None:
    """Scenario: No tenant set (insert)."""
    email = unique_email("ghost")

    with tenant_context(tenant), pytest.raises(PrincipalRequiredError):
        store.insert_user(email=email, password_hash=HASH, role="user", name="N")

    for owner_tenant in (TENANT_A, TENANT_B):
        assert count_email(owner_sql, owner_tenant, email) == 0


@pytest.mark.parametrize("tenant", [None, ""])
def test_no_tenant_actor_lookup_finds_nothing(store: PostgreSQLStore, tenant: str | None) -> None:
    """Scenario: No tenant set (actor lookup)."""
    admin = insert_record(store, TENANT_A, unique_email("admin"), role="admin")

    with tenant_context(tenant):
        assert store.find_active_admin(admin["email"]) is None
