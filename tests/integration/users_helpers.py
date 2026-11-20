"""Shared helpers for the user store and user service integration tests.

Not a test module. Callers keep the ``postgres_url`` and ``owner_sql`` fixtures
in their own ``store`` fixture, so the tests still skip when PostgreSQL is
unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from typing import Any

from core.security import tenant_context
from plugins.relational_db.postgres import PostgreSQLStore

SEED_PLAIN = "seed-password-123"
HASH = "$2b$12$abcdefghijklmnopqrstuuMlUrPIN6lFpvSu7Nvt3d3PZ7QvYb9W2"
OwnerSql = Callable[..., list[Any]]


def clean_tenants(owner_sql: OwnerSql, tenants: Iterable[str]) -> None:
    """Delete every user of *tenants* as the owner."""
    for tenant in tenants:
        owner_sql(tenant, "DELETE FROM users WHERE tenant_id = :t", t=tenant)


@contextmanager
def app_store(owner_sql: OwnerSql, tenants: Iterable[str]) -> Iterator[PostgreSQLStore]:
    """Yield a real store as the app role; empty *tenants* before and after."""
    tenants = tuple(tenants)
    clean_tenants(owner_sql, tenants)
    store = PostgreSQLStore()
    store.initialize()
    try:
        yield store
    finally:
        store.close()
        clean_tenants(owner_sql, tenants)


def unique_email(prefix: str = "u", domain: str = "x.pl") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@{domain}"


def count_email(owner_sql: OwnerSql, tenant: str, email: str) -> int:
    """Number of rows with *email* that the owner sees in *tenant*."""
    rows = owner_sql(tenant, "SELECT count(*) FROM users WHERE email = :e", e=email)
    return int(rows[0][0])


def seed_user(store: PostgreSQLStore, tenant: str, email: str, role: str = "user") -> str:
    """Seed a user with ``create_user`` (seed-only: no acting admin); return its id."""
    with tenant_context(tenant):
        record = store.create_user(
            email=email, password=SEED_PLAIN, role=role, tenant_id=tenant, name="N"
        )
    return str(record["id"])


def insert_record(
    store: PostgreSQLStore, tenant: str, email: str, role: str = "user"
) -> dict[str, Any]:
    """Insert a user through the port under *tenant*, acting as a freshly seeded admin."""
    actor_id = seed_user(store, tenant, unique_email("actor"), "admin")
    with tenant_context(tenant):
        record = store.insert_user(
            email=email, password_hash=HASH, role=role, name="N", actor_id=actor_id
        )
    return dict(record)


def insert_id(store: PostgreSQLStore, tenant: str, role: str = "user") -> str:
    """Seed a user with a unique email under *tenant*; return its id."""
    return seed_user(store, tenant, unique_email(role), role)
