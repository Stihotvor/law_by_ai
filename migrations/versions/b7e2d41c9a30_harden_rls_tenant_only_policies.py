"""harden RLS: role checks, NO FORCE window, tenant-only policies

Checks that the three rls-201 roles exist and that ``lawbyai_owner`` owns the
tables and the ``users_bump_session_version`` function; if not, it stops and
names each problem before it changes anything. The ``tenants`` and ``users``
policies then match only the tenant in ``app.current_tenant``, so no tenant
set means zero rows. Every data read of this revision runs inside a
NO FORCE / FORCE window on ``tenants`` and ``users``, in one transaction.

Revision ID: b7e2d41c9a30
Revises: 77985ac8fa22
Create Date: 2026-11-13 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e2d41c9a30"
down_revision: str | Sequence[str] | None = "77985ac8fa22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Frozen literals: this revision must not change if the model changes.
TENANT_SETTING = "app.current_tenant"
OWNER_ROLE = "lawbyai_owner"
REQUIRED_ROLES = (OWNER_ROLE, "lawbyai_app", "lawbyai_auth")
OWNED_TABLES = ("tenants", "users", "legal_document", "rejected_document", "alembic_version")
OWNED_FUNCTIONS = ("users_bump_session_version",)
# FORCE stays as 4439761c5e40 set it: tenants and users only.
FORCED_TABLES = ("tenants", "users")
# (table, policy name kept from 4439761c5e40, tenant column)
POLICIES = (("tenants", "tenants_isolation", "id"), ("users", "users_isolation", "tenant_id"))

ROLES_SQL = "SELECT rolname FROM pg_roles WHERE rolname = ANY(:names)"
TABLE_OWNERS_SQL = """
    SELECT c.relname, pg_get_userbyid(c.relowner)
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND c.relname = ANY(:names)
"""
FUNCTION_OWNERS_SQL = """
    SELECT p.proname, pg_get_userbyid(p.proowner)
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname = ANY(:names)
"""

# Policy expressions exactly as 4439761c5e40 created them (used by the downgrade).
_SETTING = f"current_setting('{TENANT_SETTING}', true)"
OLD_POLICIES = {
    "tenants_isolation": (
        f"{_SETTING} = '' OR id = {_SETTING}",
        f"{_SETTING} = '' OR id = {_SETTING}",
    ),
    "users_isolation": (
        f"{_SETTING} = '' OR tenant_id IS NULL OR tenant_id = {_SETTING}",
        f"{_SETTING} = '' OR tenant_id = {_SETTING}",
    ),
}


def upgrade() -> None:
    """Upgrade schema: check roles and owners, then tenant-only policies."""
    # Fail fast instead of queueing behind long transactions (ACCESS EXCLUSIVE below).
    op.execute("SET LOCAL lock_timeout = '5s'")
    _check_prerequisites()
    _set_force_rls(force=False)
    # The data reads of this revision (added in T4) run here, inside the NO FORCE window.
    _tenant_only_policies()
    _set_force_rls(force=True)


def downgrade() -> None:
    """Downgrade schema: restore the 4439761c5e40 policies."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    _restore_old_policies()


def _check_prerequisites() -> None:
    """Raise RuntimeError naming each missing role, missing object or wrong owner."""
    bind = op.get_bind()
    roles = {
        row[0] for row in bind.execute(sa.text(ROLES_SQL), {"names": list(REQUIRED_ROLES)}).all()
    }
    tables = _owners(bind, TABLE_OWNERS_SQL, OWNED_TABLES)
    functions = _owners(bind, FUNCTION_OWNERS_SQL, OWNED_FUNCTIONS)
    problems = _missing_roles(roles) + _owner_problems("table", OWNED_TABLES, tables)
    problems += _owner_problems("function", OWNED_FUNCTIONS, functions)
    if problems:
        raise RuntimeError("rls-201 prerequisites not met: " + "; ".join(problems))


def _owners(bind: sa.Connection, sql: str, names: Sequence[str]) -> dict[str, str]:
    """Return {object name: owner role} for the named objects in schema public."""
    rows = bind.execute(sa.text(sql), {"names": list(names)}).all()
    return {row[0]: row[1] for row in rows}


def _missing_roles(found: set[str]) -> list[str]:
    """Return one message per required role that does not exist."""
    return [f"role {name} does not exist" for name in REQUIRED_ROLES if name not in found]


def _owner_problems(kind: str, names: Sequence[str], owners: dict[str, str]) -> list[str]:
    """Return one message per object that is missing or not owned by OWNER_ROLE."""
    problems: list[str] = []
    for name in names:
        owner = owners.get(name)
        if owner is None:
            problems.append(f"{kind} {name} does not exist")
        elif owner != OWNER_ROLE:
            problems.append(f"{kind} {name} is owned by {owner}, not {OWNER_ROLE}")
    return problems


def _set_force_rls(*, force: bool) -> None:
    """Turn FORCE ROW LEVEL SECURITY on or off for FORCED_TABLES."""
    mode = "FORCE" if force else "NO FORCE"
    for table in FORCED_TABLES:
        op.execute(f"ALTER TABLE public.{table} {mode} ROW LEVEL SECURITY")


def _tenant_only_policies() -> None:
    """Make each policy match only the current tenant; an empty setting matches nothing."""
    tenant = f"nullif({_SETTING}, '')"
    for table, policy, column in POLICIES:
        op.execute(
            f"ALTER POLICY {policy} ON public.{table} "
            f"USING ({column} = {tenant}) WITH CHECK ({column} = {tenant})"
        )


def _restore_old_policies() -> None:
    """Put back the policy expressions of 4439761c5e40."""
    for table, policy, _column in POLICIES:
        using, check = OLD_POLICIES[policy]
        op.execute(f"ALTER POLICY {policy} ON public.{table} USING ({using}) WITH CHECK ({check})")
