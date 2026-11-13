"""harden RLS: role checks, tenant-only policies, auth_lookup_user, grants

Checks that the three rls-201 roles exist and that ``lawbyai_owner`` owns the
tables and the ``users_bump_session_version`` function; if not, it stops and
names each problem before it changes anything. The ``tenants`` and ``users``
policies then match only the tenant in ``app.current_tenant``, so no tenant
set means zero rows. Every data read of this revision runs inside a
NO FORCE / FORCE window on ``tenants`` and ``users``, in one transaction.

The only cross-tenant read is ``public.auth_lookup_user``, a SECURITY DEFINER
function owned by ``lawbyai_auth`` (BYPASSRLS) that only ``lawbyai_app`` may run.
``lawbyai_app`` gets DML on the four data tables, the ``rejected_document`` id
sequence and SELECT on ``alembic_version``. The downgrade undoes all of this and
keeps ``ck_users_email_normalised`` (it belongs to ``77985ac8fa22``).

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
APP_ROLE = "lawbyai_app"
AUTH_ROLE = "lawbyai_auth"
APP_TABLES = ("tenants", "users", "legal_document", "rejected_document")
APP_SEQUENCE = "rejected_document_id_seq"
AUTH_FUNCTION = "public.auth_lookup_user(text)"
# Exactly the columns auth_lookup_user returns; lawbyai_auth may SELECT only these.
AUTH_COLUMN_LIST = "id, tenant_id, email, role, name, is_active, password_hash, session_version"
# Column types as 4439761c5e40 / 77985ac8fa22 created the users table.
AUTH_FUNCTION_SQL = """
    CREATE FUNCTION public.auth_lookup_user(p_email text)
    RETURNS TABLE (
        id varchar, tenant_id varchar, email varchar, role varchar, name varchar,
        is_active boolean, password_hash varchar, session_version integer
    )
    LANGUAGE sql STABLE STRICT SECURITY DEFINER
    SET search_path = pg_catalog, pg_temp
    AS $$
        SELECT u.id, u.tenant_id, u.email, u.role, u.name,
               u.is_active, u.password_hash, u.session_version
        FROM public.users u WHERE u.email = lower(btrim(p_email))
    $$
"""

ROLE_ATTRIBUTES = ("rolsuper", "rolbypassrls", "rolcanlogin")
# (rolsuper, rolbypassrls, rolcanlogin) each role must have, as the init script creates it.
EXPECTED_ATTRIBUTES = {
    OWNER_ROLE: (False, False, True),
    APP_ROLE: (False, False, True),
    AUTH_ROLE: (False, True, False),
}
ROLES_SQL = (
    "SELECT rolname, rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = ANY(:names)"
)
# pg_has_role follows indirect membership chains too. It raises on an unknown
# role, so call it only when both roles exist.
MEMBERSHIP_SQL = "SELECT pg_has_role(:member, :role, 'MEMBER')"
# ALTER FUNCTION ... OWNER TO lawbyai_auth needs CREATE on the schema for the new owner.
AUTH_SCHEMA_CREATE_SQL = "SELECT has_schema_privilege(:role, 'public', 'CREATE')"
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
    # Any data read of this revision must run here, inside the NO FORCE window.
    _tenant_only_policies()
    _set_force_rls(force=True)
    _create_auth_lookup_user()
    _grant_app()


def downgrade() -> None:
    """Downgrade schema: undo grants and function, restore the 4439761c5e40 policies."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    _revoke_app()
    _drop_auth_lookup_user()
    _restore_old_policies()


def _check_prerequisites() -> None:
    """Raise RuntimeError naming each missing or wrong role, missing object or wrong owner."""
    bind = op.get_bind()
    rows = bind.execute(sa.text(ROLES_SQL), {"names": list(REQUIRED_ROLES)}).all()
    attributes = {row[0]: tuple(bool(v) for v in row[1:]) for row in rows}
    roles = set(attributes)
    tables = _owners(bind, TABLE_OWNERS_SQL, OWNED_TABLES)
    functions = _owners(bind, FUNCTION_OWNERS_SQL, OWNED_FUNCTIONS)
    problems = _missing_roles(roles) + _attribute_problems(attributes)
    problems += _membership_problems(bind, roles)
    problems += _owner_problems("table", OWNED_TABLES, tables)
    problems += _owner_problems("function", OWNED_FUNCTIONS, functions)
    problems += _auth_schema_problems(bind, roles)
    if problems:
        raise RuntimeError("rls-201 prerequisites not met: " + "; ".join(problems))


def _owners(bind: sa.Connection, sql: str, names: Sequence[str]) -> dict[str, str]:
    """Return {object name: owner role} for the named objects in schema public."""
    rows = bind.execute(sa.text(sql), {"names": list(names)}).all()
    return {row[0]: row[1] for row in rows}


def _missing_roles(found: set[str]) -> list[str]:
    """Return one message per required role that does not exist."""
    return [f"role {name} does not exist" for name in REQUIRED_ROLES if name not in found]


def _attribute_problems(found: dict[str, tuple[bool, ...]]) -> list[str]:
    """Return one message per role attribute that differs from EXPECTED_ATTRIBUTES."""
    problems: list[str] = []
    for role, expected in EXPECTED_ATTRIBUTES.items():
        actual = found.get(role)
        if actual is None:
            continue
        for name, want, got in zip(ROLE_ATTRIBUTES, expected, actual, strict=True):
            if want != got:
                problems.append(
                    f"role {role} has {name} {str(got).lower()}, expected {str(want).lower()}"
                )
    return problems


def _membership_problems(bind: sa.Connection, roles: set[str]) -> list[str]:
    """Return a message if lawbyai_app is a direct or indirect member of lawbyai_auth.

    Skip when either role is missing: pg_has_role raises on an unknown role.
    """
    if not {APP_ROLE, AUTH_ROLE} <= roles:
        return []
    params = {"role": AUTH_ROLE, "member": APP_ROLE}
    if not bind.execute(sa.text(MEMBERSHIP_SQL), params).scalar_one():
        return []
    return [f"role {APP_ROLE} is a member of {AUTH_ROLE} (it must not reach BYPASSRLS)"]


def _auth_schema_problems(bind: sa.Connection, roles: set[str]) -> list[str]:
    """Return a message if lawbyai_auth lacks CREATE on schema public (skip if it is missing)."""
    if AUTH_ROLE not in roles:
        return []
    if bind.execute(sa.text(AUTH_SCHEMA_CREATE_SQL), {"role": AUTH_ROLE}).scalar_one():
        return []
    return [f"role {AUTH_ROLE} has no CREATE on schema public (needed to own auth_lookup_user)"]


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


def _create_auth_lookup_user() -> None:
    """Step 5: the login lookup across tenants, owned by lawbyai_auth.

    REVOKE and GRANT run before ALTER OWNER: lawbyai_owner does not inherit
    lawbyai_auth, so after the owner change it could not edit the ACL. The ACL
    moves to the new owner together with the ownership.
    """
    op.execute(f"GRANT SELECT ({AUTH_COLUMN_LIST}) ON public.users TO {AUTH_ROLE}")
    op.execute(AUTH_FUNCTION_SQL)
    op.execute(f"REVOKE EXECUTE ON FUNCTION {AUTH_FUNCTION} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {AUTH_FUNCTION} TO {APP_ROLE}")
    op.execute(f"ALTER FUNCTION {AUTH_FUNCTION} OWNER TO {AUTH_ROLE}")


def _grant_app() -> None:
    """Step 6: table, sequence and revision grants for lawbyai_app; no PUBLIC EXECUTE."""
    for table in APP_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.{table} TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE public.{APP_SEQUENCE} TO {APP_ROLE}")
    op.execute(f"GRANT SELECT ON public.alembic_version TO {APP_ROLE}")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER_ROLE} REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"
    )


def _revoke_app() -> None:
    """Undo step 6 in reverse order."""
    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER_ROLE} GRANT EXECUTE ON FUNCTIONS TO PUBLIC"
    )
    op.execute("REVOKE SELECT ON public.alembic_version FROM lawbyai_app")
    op.execute("REVOKE USAGE, SELECT ON SEQUENCE public.rejected_document_id_seq FROM lawbyai_app")
    for table in reversed(APP_TABLES):
        op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON public.{table} FROM {APP_ROLE}")


def _drop_auth_lookup_user() -> None:
    """Undo step 5. Only the owner may drop the function, so drop it as lawbyai_auth."""
    op.execute(f"SET LOCAL ROLE {AUTH_ROLE}")
    op.execute(f"DROP FUNCTION IF EXISTS {AUTH_FUNCTION}")
    op.execute("RESET ROLE")
    op.execute(
        "REVOKE SELECT (id, tenant_id, email, role, name, is_active, password_hash, "
        "session_version) ON public.users FROM lawbyai_auth"
    )
