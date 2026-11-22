"""Last-admin trigger and admin audit table (migration ``c4a91e7f2b58``).

Data tests run in the configured database. The owner ``lawbyai_owner`` seeds and
cleans tenants (``tenant_sql`` sets the tenant and the owner skip setting). The
app role ``lawbyai_app`` runs the statements the trigger must refuse. The round
trip runs in a scratch database. Skipped if PostgreSQL is unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from factories.scratch_db import ScratchDb, scratch_database, tenant_sql
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from users_helpers import HASH, OwnerSql, app_store

from core.security import tenant_context

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "81dde4a27be7"
CHECK_VIOLATION = "23514"
INSUFFICIENT_PRIVILEGE = "42501"
CONSTRAINT = "trg_users_last_admin"
INSERT_TENANT = "INSERT INTO tenants (id, name) VALUES (:id, 'last admin test')"
INSERT_USER = (
    "INSERT INTO users (id, tenant_id, email, password_hash, role, name, is_active) "
    "VALUES (:id, :tid, :email, 'h', :role, '', :active)"
)
INSERT_AUDIT = (
    "INSERT INTO admin_action_audit (tenant_id, actor_id, action, target_id) "
    "VALUES (:tid, 'actor-1', :action, 'target-1')"
)
SET_TENANT = "SELECT set_config('app.current_tenant', :tenant, true)"
SKIP_CHECK = "SELECT set_config('app.skip_last_admin_check', 'on', true)"
FUNCTION_ACL_SQL = """
    SELECT count(*) FROM pg_proc p, aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
    WHERE p.proname = 'users_guard_last_admin' AND a.grantee = 0
"""
OWNER_SQL = "SELECT pg_get_userbyid(proowner) FROM pg_proc WHERE proname = 'users_guard_last_admin'"
TRIGGER_COUNT = "SELECT count(*) FROM pg_trigger WHERE tgname = 'trg_users_last_admin'"
TABLE_COUNT = "SELECT count(*) FROM pg_class WHERE relname = 'admin_action_audit'"
RLS_STATE = "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :n"
PRIV_SQL = "SELECT has_table_privilege('lawbyai_app', 'public.admin_action_audit', :priv)"


@dataclass(frozen=True)
class Tenant:
    id: str
    admin1: str
    admin2: str
    user: str


def _hex() -> str:
    return uuid.uuid4().hex[:12]


def _sqlstate(error: DBAPIError) -> str | None:
    orig = error.orig
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


def _constraint(error: DBAPIError) -> str | None:
    return getattr(getattr(error.orig, "diag", None), "constraint_name", None)


def _run(
    url: str, tenant: str | None, sql: str, *, skip: bool = False, **params: Any
) -> list[tuple[Any, ...]]:
    """Run *sql* in one transaction of its own; set the tenant and, on request, the skip setting."""
    engine = create_engine(url, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text(SET_TENANT), {"tenant": tenant or ""})
            if skip:
                conn.execute(text(SKIP_CHECK))
            result = conn.execute(text(sql), params)
            return [tuple(row) for row in result.all()] if result.returns_rows else []
    finally:
        engine.dispose()


def _admins(owner_url: str, tenant: str) -> int:
    sql = "SELECT count(*) FROM users WHERE tenant_id = :t AND role = 'admin' AND is_active"
    return int(_run(owner_url, tenant, sql, t=tenant)[0][0])


def _seed(owner_url: str, tag: str) -> Tenant:
    data = Tenant(f"la-{tag}", f"a1-{tag}", f"a2-{tag}", f"u-{tag}")
    tenant_sql(owner_url, data.id, INSERT_TENANT, id=data.id)
    for user_id, role in ((data.admin1, "admin"), (data.admin2, "admin"), (data.user, "user")):
        tenant_sql(
            owner_url,
            data.id,
            INSERT_USER,
            id=user_id,
            tid=data.id,
            email=f"{user_id}@x.pl",
            role=role,
            active=True,
        )
    return data


@pytest.fixture
def tenant(owner_url: str, postgres_url: str) -> Iterator[Tenant]:
    """A tenant with two active admins and one user; the owner removes it afterwards."""
    data = _seed(owner_url, _hex())
    try:
        yield data
    finally:
        tenant_sql(owner_url, data.id, "DELETE FROM users WHERE tenant_id = :t", t=data.id)
        tenant_sql(owner_url, data.id, "DELETE FROM tenants WHERE id = :t", t=data.id)
        tenant_sql(
            owner_url, data.id, "DELETE FROM admin_action_audit WHERE tenant_id = :t", t=data.id
        )


def _remove_admin2(url: str, tenant: Tenant) -> None:
    """Deactivate the second admin as the app role: allowed while admin1 is active."""
    sql = "UPDATE users SET is_active = false WHERE id = :i"
    _run(url, tenant.id, sql, i=tenant.admin2)


# --- the trigger refuses removing the last active admin -------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE users SET is_active = false WHERE id = :i",
        "UPDATE users SET role = 'user' WHERE id = :i",
        "DELETE FROM users WHERE id = :i",
    ],
)
def test_app_role_cannot_remove_the_last_admin(
    postgres_url: str, owner_url: str, tenant: Tenant, sql: str
) -> None:
    """Scenario: direct SQL on the last active admin is refused with 23514."""
    _remove_admin2(postgres_url, tenant)
    with pytest.raises(DBAPIError) as info:
        _run(postgres_url, tenant.id, sql, i=tenant.admin1)
    assert _sqlstate(info.value) == CHECK_VIOLATION
    assert _constraint(info.value) == CONSTRAINT
    assert _admins(owner_url, tenant.id) == 1


def test_the_first_of_two_admins_can_go(postgres_url: str, owner_url: str, tenant: Tenant) -> None:
    """Scenario: another active admin remains, so the change is allowed."""
    _remove_admin2(postgres_url, tenant)
    assert _admins(owner_url, tenant.id) == 1


def test_users_and_inactive_admins_are_free_to_change(
    postgres_url: str, owner_url: str, tenant: Tenant
) -> None:
    _remove_admin2(postgres_url, tenant)
    sql = "UPDATE users SET is_active = false WHERE id = :i"
    _run(postgres_url, tenant.id, sql, i=tenant.user)
    _run(postgres_url, tenant.id, "DELETE FROM users WHERE id = :i", i=tenant.admin2)
    assert _admins(owner_url, tenant.id) == 1


def test_one_statement_that_removes_every_admin_fails_as_a_whole(
    postgres_url: str, owner_url: str, tenant: Tenant
) -> None:
    """The last row of the statement is refused, so no admin is deactivated."""
    sql = "UPDATE users SET is_active = false WHERE tenant_id = :t AND role = 'admin'"
    with pytest.raises(DBAPIError) as info:
        _run(postgres_url, tenant.id, sql, t=tenant.id)
    assert _sqlstate(info.value) == CHECK_VIOLATION
    assert _admins(owner_url, tenant.id) == 2


def test_other_columns_do_not_fire_the_check(
    postgres_url: str, owner_url: str, tenant: Tenant
) -> None:
    _remove_admin2(postgres_url, tenant)
    _run(postgres_url, tenant.id, "UPDATE users SET name = 'n' WHERE id = :i", i=tenant.admin1)
    assert _admins(owner_url, tenant.id) == 1


# --- owner maintenance ------------------------------------------------------------


def test_owner_without_the_setting_is_refused(owner_url: str, tenant: Tenant) -> None:
    _remove_admin2(owner_url, tenant)
    sql = "UPDATE users SET is_active = false WHERE id = :i"
    with pytest.raises(DBAPIError) as info:
        _run(owner_url, tenant.id, sql, i=tenant.admin1)
    assert _sqlstate(info.value) == CHECK_VIOLATION


def test_owner_with_the_setting_may_remove_the_last_admin(owner_url: str, tenant: Tenant) -> None:
    _remove_admin2(owner_url, tenant)
    sql = "UPDATE users SET is_active = false WHERE id = :i"
    _run(owner_url, tenant.id, sql, skip=True, i=tenant.admin1)
    assert _admins(owner_url, tenant.id) == 0


def test_app_role_cannot_use_the_setting(postgres_url: str, owner_url: str, tenant: Tenant) -> None:
    """Scenario: the skip setting is honoured for lawbyai_owner only."""
    _remove_admin2(postgres_url, tenant)
    sql = "UPDATE users SET is_active = false WHERE id = :i"
    with pytest.raises(DBAPIError) as info:
        _run(postgres_url, tenant.id, sql, skip=True, i=tenant.admin1)
    assert _sqlstate(info.value) == CHECK_VIOLATION
    assert _admins(owner_url, tenant.id) == 1


def test_function_is_owned_by_the_owner_and_has_no_public_execute(postgres_url: str) -> None:
    assert _run(postgres_url, None, OWNER_SQL)[0][0] == "lawbyai_owner"
    assert _run(postgres_url, None, FUNCTION_ACL_SQL)[0][0] == 0


# --- admin_action_audit ----------------------------------------------------------


def test_app_role_can_insert_and_read_its_tenant_rows(postgres_url: str, tenant: Tenant) -> None:
    _run(postgres_url, tenant.id, INSERT_AUDIT, tid=tenant.id, action="create_user")
    rows = _run(
        postgres_url,
        tenant.id,
        "SELECT actor_id, action, target_id, created_at FROM admin_action_audit",
    )
    assert [r[:3] for r in rows] == [("actor-1", "create_user", "target-1")]
    assert rows[0][3] is not None


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE admin_action_audit SET actor_id = 'x'",
        "DELETE FROM admin_action_audit",
        "TRUNCATE admin_action_audit",
    ],
)
def test_app_role_cannot_change_or_delete_audit_rows(
    postgres_url: str, tenant: Tenant, sql: str
) -> None:
    _run(postgres_url, tenant.id, INSERT_AUDIT, tid=tenant.id, action="deactivate_user")
    with pytest.raises(ProgrammingError) as info:
        _run(postgres_url, tenant.id, sql)
    assert _sqlstate(info.value) == INSUFFICIENT_PRIVILEGE
    count = _run(postgres_url, tenant.id, "SELECT count(*) FROM admin_action_audit")[0][0]
    assert count == 1


def test_audit_rows_are_tenant_scoped(postgres_url: str, tenant: Tenant) -> None:
    _run(postgres_url, tenant.id, INSERT_AUDIT, tid=tenant.id, action="create_user")
    assert _run(postgres_url, "other-tenant", "SELECT count(*) FROM admin_action_audit")[0][0] == 0
    assert _run(postgres_url, None, "SELECT count(*) FROM admin_action_audit")[0][0] == 0
    with pytest.raises(DBAPIError):
        _run(postgres_url, "other-tenant", INSERT_AUDIT, tid=tenant.id, action="create_user")


def test_audit_action_is_checked(postgres_url: str, tenant: Tenant) -> None:
    with pytest.raises(DBAPIError) as info:
        _run(postgres_url, tenant.id, INSERT_AUDIT, tid=tenant.id, action="drop_everything")
    assert _sqlstate(info.value) == CHECK_VIOLATION


def test_audit_table_privileges_and_rls_state(postgres_url: str) -> None:
    for priv, expected in (
        ("SELECT", True),
        ("INSERT", True),
        ("UPDATE", False),
        ("DELETE", False),
        ("TRUNCATE", False),
    ):
        assert _run(postgres_url, None, PRIV_SQL, priv=priv)[0][0] is expected
    assert _run(postgres_url, None, RLS_STATE, n="admin_action_audit")[0] == (True, True)


# --- upgrade and downgrade (scratch database) --------------------------------------


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


@pytest.fixture
def scratch(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[ScratchDb]:
    """Scratch database at head, migrated by the owner; the env URLs point at it."""
    with scratch_database("migla") as db:
        monkeypatch.setenv("POSTGRES_URL", db.app_url)
        monkeypatch.setenv("POSTGRES_OWNER_URL", db.owner_url)
        command.upgrade(_alembic_config(), "head")
        yield db


def _count(url: str, sql: str) -> int:
    return int(_run(url, None, sql)[0][0])


def test_downgrade_and_upgrade_round_trip(scratch: ScratchDb) -> None:
    cfg = _alembic_config()
    assert _count(scratch.app_url, TRIGGER_COUNT) == 1
    command.downgrade(cfg, PREVIOUS_REVISION)
    assert _count(scratch.app_url, TRIGGER_COUNT) == 0
    assert _count(scratch.app_url, TABLE_COUNT) == 0
    command.upgrade(cfg, "head")
    assert _count(scratch.app_url, TRIGGER_COUNT) == 1
    assert _count(scratch.app_url, TABLE_COUNT) == 1


def test_downgrade_stops_while_the_audit_table_holds_rows(scratch: ScratchDb) -> None:
    cfg = _alembic_config()
    tenant_sql(scratch.owner_url, "t", INSERT_AUDIT, tid="t", action="create_user")
    with pytest.raises(RuntimeError, match="holds 1 rows"):
        command.downgrade(cfg, PREVIOUS_REVISION)
    # The failed downgrade changed nothing.
    assert _count(scratch.app_url, TRIGGER_COUNT) == 1
    assert _count(scratch.app_url, TABLE_COUNT) == 1
    assert _run(scratch.app_url, None, RLS_STATE, n="admin_action_audit")[0] == (True, True)
    tenant_sql(scratch.owner_url, "t", "DELETE FROM admin_action_audit")
    command.downgrade(cfg, PREVIOUS_REVISION)
    assert _count(scratch.app_url, TABLE_COUNT) == 0


# --- the store writes the audit rows ------------------------------------------------


def test_store_audits_create_and_deactivate(
    owner_url: str, owner_sql: OwnerSql, tenant: Tenant
) -> None:
    """Scenario: create and deactivate each append one row for the actor, atomically."""
    with app_store(owner_sql, ()) as store, tenant_context(tenant.id):
        created = store.insert_user(
            email=f"new-{tenant.user}@x.pl",
            password_hash=HASH,
            role="user",
            name="N",
            actor_id=tenant.admin1,
        )
        assert store.deactivate_user(tenant.user, actor_id=tenant.admin1) is True
        assert store.deactivate_user(tenant.user, actor_id=tenant.admin1) is False
    sql = "SELECT tenant_id, actor_id, action, target_id FROM admin_action_audit ORDER BY id"
    rows = [tuple(r) for r in tenant_sql(owner_url, tenant.id, sql)]
    assert rows == [
        (tenant.id, tenant.admin1, "create_user", created["id"]),
        (tenant.id, tenant.admin1, "deactivate_user", tenant.user),
    ]
