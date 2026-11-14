"""RLS hardening (rls-201): every success metric and edge case, as ``lawbyai_app``.

Marked ``integration``. The data tests use the configured database: the owner
``lawbyai_owner`` writes two tenants and three users inside each tenant context
and deletes them afterwards; the app role ``lawbyai_app`` asserts. Emails and
tenant ids are unique per test, because ``uq_users_email`` is global. The
downgrade round trip runs in a scratch database (``migrls_<hex>``). Skipped if
PostgreSQL is unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from factories.scratch_db import ScratchDb, scratch_database, tenant_sql
from sqlalchemy import Row, create_engine, text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "77985ac8fa22"
AUTH_ROLE = "lawbyai_auth"
AUTH_FUNCTION = "public.auth_lookup_user(text)"
INSERT_TENANT = "INSERT INTO tenants (id, name) VALUES (:id, 'rls test')"
INSERT_USER = (
    "INSERT INTO users (id, tenant_id, email, password_hash, role, name, is_active) "
    "VALUES (:id, :tid, :email, 'h', 'user', '', :active)"
)
LOOKUP = "SELECT tenant_id, email, is_active FROM public.auth_lookup_user(:email)"
FUNCTION_SQL = """
    SELECT p.prosecdef, p.proconfig, p.proowner::regrole::text
    FROM pg_proc p WHERE p.oid = 'public.auth_lookup_user(text)'::regprocedure
"""
AUTH_OWNED_SQL = """
    SELECT (SELECT count(*) FROM pg_proc WHERE proowner = 'lawbyai_auth'::regrole)
         + (SELECT count(*) FROM pg_class WHERE relowner = 'lawbyai_auth'::regrole)
"""
COUNT_SQL = ["SELECT count(*) FROM users", "SELECT count(*) FROM tenants"]
FORCE_SQL = """
    SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relname = ANY(:names)
"""
POLICY_SQL = "SELECT policyname, qual, with_check FROM pg_policies WHERE schemaname = 'public'"
OwnerSql = Callable[..., list[Row[Any]]]
Tup = tuple[Any, ...]


@dataclass(frozen=True)
class Seed:
    """Ids and emails of the rows one test writes."""

    tenant_a: str
    tenant_b: str
    email_a: str
    email_b: str
    email_inactive: str


def _hex() -> str:
    return uuid.uuid4().hex[:12]


def _app_rows(url: str, sql: str, tenant: str | None = None, **params: Any) -> list[Row[Any]]:
    """Run *sql* as the app in one transaction; set the tenant only when given."""
    if tenant is not None:
        return tenant_sql(url, tenant, sql, **params)
    engine = create_engine(url, future=True)
    try:
        with engine.begin() as conn:
            return list(conn.execute(text(sql), params).all())
    finally:
        engine.dispose()


def _app_tuples(url: str, sql: str, tenant: str | None = None, **params: Any) -> list[Tup]:
    """Like ``_app_rows``, with plain tuples."""
    return [tuple(row) for row in _app_rows(url, sql, tenant, **params)]


def _app_scalar(url: str, sql: str, **params: Any) -> Any:
    return _app_rows(url, sql, **params)[0][0]


def _insert_tenant(owner_sql: OwnerSql, tenant: str) -> None:
    owner_sql(tenant, INSERT_TENANT, id=tenant)


def _insert_user(owner_sql: OwnerSql, tenant: str, email: str, *, active: bool = True) -> None:
    owner_sql(tenant, INSERT_USER, id=_hex(), tid=tenant, email=email, active=active)


def _cleanup(owner_sql: OwnerSql, tenant: str) -> None:
    owner_sql(tenant, "DELETE FROM users WHERE tenant_id = :t", t=tenant)
    owner_sql(tenant, "DELETE FROM tenants WHERE id = :t", t=tenant)


@pytest.fixture
def seed(postgres_url: str, owner_sql: OwnerSql) -> Iterator[Seed]:
    """Tenants A and B; user a in A, user b in B, one inactive user in A."""
    tag = _hex()
    data = Seed(
        tenant_a=f"rls-a-{tag}",
        tenant_b=f"rls-b-{tag}",
        email_a=f"a{tag}@x.pl",
        email_b=f"b{tag}@x.pl",
        email_inactive=f"off{tag}@x.pl",
    )
    try:
        for tenant in (data.tenant_a, data.tenant_b):
            _insert_tenant(owner_sql, tenant)
        _insert_user(owner_sql, data.tenant_a, data.email_a)
        _insert_user(owner_sql, data.tenant_b, data.email_b)
        _insert_user(owner_sql, data.tenant_a, data.email_inactive, active=False)
        yield data
    finally:
        for tenant in (data.tenant_a, data.tenant_b):
            _cleanup(owner_sql, tenant)


# --- metrics: fail closed and tenant isolation ---------------------------------


@pytest.mark.parametrize("sql", COUNT_SQL)
def test_no_tenant_shows_zero_rows(postgres_url: str, seed: Seed, sql: str) -> None:
    """Scenario: No tenant shows zero rows (setting never set)."""
    assert _app_scalar(postgres_url, sql) == 0


@pytest.mark.parametrize("sql", COUNT_SQL)
def test_empty_tenant_shows_zero_rows(postgres_url: str, seed: Seed, sql: str) -> None:
    """An empty tenant setting is the same as no tenant: zero rows."""
    rows = _app_tuples(postgres_url, sql, tenant="")
    assert rows[0][0] == 0


def test_tenant_a_sees_only_tenant_a(postgres_url: str, seed: Seed) -> None:
    users = _app_tuples(postgres_url, "SELECT DISTINCT tenant_id FROM users", tenant=seed.tenant_a)
    tenants = _app_tuples(postgres_url, "SELECT id FROM tenants", tenant=seed.tenant_a)
    assert [row[0] for row in users] == [seed.tenant_a]
    assert [row[0] for row in tenants] == [seed.tenant_a]


def test_tenant_a_cannot_insert_tenant_b_user(postgres_url: str, seed: Seed) -> None:
    """Scenario: Tenant A cannot write tenant B (WITH CHECK fails)."""
    params = {"id": _hex(), "tid": seed.tenant_b, "email": f"x{_hex()}@x.pl", "active": True}
    with pytest.raises(DBAPIError, match="row-level security"):
        tenant_sql(postgres_url, seed.tenant_a, INSERT_USER, **params)


def test_tenant_a_cannot_insert_tenant_b_tenant(postgres_url: str, seed: Seed) -> None:
    with pytest.raises(DBAPIError, match="row-level security"):
        tenant_sql(postgres_url, seed.tenant_a, INSERT_TENANT, id=f"rls-x-{_hex()}")


# --- metrics and edge cases: auth_lookup_user ---------------------------------


def test_lookup_normalises_email_across_two_tenants(postgres_url: str, seed: Seed) -> None:
    """Scenario: Lookup normalises the email (' A@x.PL ' style input, no tenant set)."""
    rows = _app_tuples(postgres_url, LOOKUP, email=f" {seed.email_a.upper()} ")
    assert len(rows) == 1
    assert rows[0][0] == seed.tenant_a
    assert rows[0][1] == seed.email_a


def test_lookup_finds_the_other_tenant_too(postgres_url: str, seed: Seed) -> None:
    rows = _app_tuples(postgres_url, LOOKUP, email=seed.email_b)
    assert [(row[0], row[1]) for row in rows] == [(seed.tenant_b, seed.email_b)]


@pytest.mark.parametrize("email", ["%", "", "nobody@unknown.example", "%@x.pl", "_%"])
def test_lookup_returns_nothing_for_bad_input(postgres_url: str, seed: Seed, email: str) -> None:
    """Scenario Outline: Lookup returns nothing for bad input (no pattern match)."""
    assert _app_tuples(postgres_url, LOOKUP, email=email) == []


def test_lookup_returns_inactive_user(postgres_url: str, seed: Seed) -> None:
    """Scenario: Inactive user is returned; the UI keeps its own reject."""
    rows = _app_tuples(postgres_url, LOOKUP, email=seed.email_inactive)
    assert len(rows) == 1
    assert rows[0][2] is False


def test_lookup_ignores_tenant_setting(postgres_url: str, seed: Seed) -> None:
    """The lookup is the one cross-tenant read: tenant A set still finds the B user."""
    rows = _app_tuples(postgres_url, LOOKUP, tenant=seed.tenant_a, email=seed.email_b)
    assert [row[0] for row in rows] == [seed.tenant_b]


# --- metrics: roles and the function definition -------------------------------


def test_app_role_has_no_bypass(postgres_url: str) -> None:
    """Scenario: App role has no bypass."""
    rows = _app_tuples(
        postgres_url,
        "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user",
    )
    assert [tuple(row) for row in rows] == [("lawbyai_app", False, False)]


def test_function_definition(postgres_url: str) -> None:
    """Scenario: Function definition (SECURITY DEFINER, search_path, owner)."""
    secdef, config, owner = _app_tuples(postgres_url, FUNCTION_SQL)[0]
    assert secdef is True
    assert owner == AUTH_ROLE
    settings = [item.replace(" ", "") for item in (config or [])]
    assert settings == ["search_path=pg_catalog,pg_temp"]


def test_no_public_execute(postgres_url: str) -> None:
    sql = "SELECT has_function_privilege(:role, :fn, 'EXECUTE')"
    assert _app_scalar(postgres_url, sql, role="public", fn=AUTH_FUNCTION) is False
    assert _app_scalar(postgres_url, sql, role="lawbyai_app", fn=AUTH_FUNCTION) is True


def test_app_cannot_set_role_auth(postgres_url: str) -> None:
    """Scenario: App cannot take the auth role."""
    with pytest.raises(DBAPIError, match="permission denied"):
        _app_tuples(postgres_url, "SET ROLE lawbyai_auth")


def test_auth_role_owns_exactly_one_object(postgres_url: str) -> None:
    """lawbyai_auth owns auth_lookup_user and nothing else (pg_proc + pg_class)."""
    assert _app_scalar(postgres_url, AUTH_OWNED_SQL) == 1


def _rls_state(url: str) -> dict[str, tuple[bool, bool]]:
    names = ["tenants", "users", "legal_document", "rejected_document"]
    return {row[0]: (row[1], row[2]) for row in _app_tuples(url, FORCE_SQL, names=names)}


def test_force_rls_state_at_head(postgres_url: str) -> None:
    """Scenario: FORCE RLS state at head (RLS on and forced on tenants and users only)."""
    assert _rls_state(postgres_url) == {
        "tenants": (True, True),
        "users": (True, True),
        "legal_document": (False, False),
        "rejected_document": (False, False),
    }


# --- downgrade then upgrade round trip (scratch database) ----------------------


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


@pytest.fixture
def scratch(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[ScratchDb]:
    """Scratch database at head, migrated by the owner; the env URLs point at it."""
    with scratch_database("migrls") as db:
        monkeypatch.setenv("POSTGRES_URL", db.app_url)
        monkeypatch.setenv("POSTGRES_OWNER_URL", db.owner_url)
        command.upgrade(_alembic_config(), "head")
        yield db


def _function_count(url: str) -> int:
    sql = "SELECT count(*) FROM pg_proc WHERE proname = 'auth_lookup_user'"
    return int(_app_scalar(url, sql))


def _policies(url: str) -> dict[str, tuple[str, str]]:
    return {row[0]: (row[1], row[2]) for row in _app_tuples(url, POLICY_SQL)}


def _assert_head_state(db: ScratchDb, email: str) -> None:
    assert _function_count(db.app_url) == 1
    for using, check in _policies(db.app_url).values():
        assert "nullif" in using.lower()
        assert "nullif" in check.lower()
    assert _rls_state(db.app_url)["users"] == (True, True)
    assert _rls_state(db.app_url)["tenants"] == (True, True)
    assert _app_scalar(db.app_url, "SELECT count(*) FROM users") == 0
    assert len(_app_tuples(db.app_url, LOOKUP, email=email)) == 1


def test_downgrade_then_upgrade_round_trip(scratch: ScratchDb) -> None:
    """The downgrade restores the old policies and drops the function; upgrade restores head."""
    email = f"rt{_hex()}@x.pl"
    tenant_sql(scratch.owner_url, "t", INSERT_TENANT, id="t")
    tenant_sql(scratch.owner_url, "t", INSERT_USER, id=_hex(), tid="t", email=email, active=True)
    _assert_head_state(scratch, email)

    cfg = _alembic_config()
    command.downgrade(cfg, PREVIOUS_REVISION)
    assert _function_count(scratch.app_url) == 0
    policies = _policies(scratch.app_url)
    assert set(policies) == {"tenants_isolation", "users_isolation"}
    for using, check in policies.values():
        assert "nullif" not in using.lower()
        assert "''" in using
        assert "''" in check

    command.upgrade(cfg, "head")
    _assert_head_state(scratch, email)
