"""last-admin trigger and the admin action audit table

``trg_users_last_admin`` refuses any UPDATE of ``is_active``, ``role`` or
``tenant_id`` and any DELETE that leaves a tenant with no active admin (SQLSTATE
23514, constraint name ``trg_users_last_admin``). The function runs as the caller,
so row level security shows it the admins of the tenant the caller can change. It
locks the other admins of that tenant with ``FOR NO KEY UPDATE`` in id order.

Owner maintenance (tenant purge, test cleanup) can skip the check with the
transaction setting ``app.skip_last_admin_check = 'on'``. The function honours it
only when ``current_user`` is ``lawbyai_owner``.

``admin_action_audit`` is an append-only log of admin user actions. RLS is
enabled and forced with a tenant-only policy. ``lawbyai_app`` gets SELECT and
INSERT only. Rows are kept forever. The downgrade stops if the table holds rows.

Revision ID: c4a91e7f2b58
Revises: 81dde4a27be7
Create Date: 2026-11-20 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4a91e7f2b58"
down_revision: str | Sequence[str] | None = "81dde4a27be7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Frozen literals: this revision must not change if the model changes.
OWNER_ROLE = "lawbyai_owner"
APP_ROLE = "lawbyai_app"
FUNCTION = "public.users_guard_last_admin"
TRIGGER = "trg_users_last_admin"
AUDIT_TABLE = "admin_action_audit"
AUDIT_POLICY = "admin_action_audit_isolation"
ACTIONS = ("create_user", "deactivate_user")
CHECK_NAME = "ck_admin_action_audit_action"
TENANT = "nullif(current_setting('app.current_tenant', true), '')"
CHECKED_TABLES = ("users", "tenants")
TABLE_OWNERS_SQL = """
    SELECT c.relname, pg_get_userbyid(c.relowner)
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND c.relname = ANY(:names)
"""
AUDIT_ROWS_SQL = "SELECT count(*) FROM public.admin_action_audit"
FUNCTION_SQL = f"""
    CREATE FUNCTION {FUNCTION}() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, pg_temp
    AS $$
    BEGIN
        IF pg_catalog.current_setting('app.skip_last_admin_check', true) = 'on'
           AND current_user = '{OWNER_ROLE}' THEN
            RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
        END IF;
        IF OLD.role = 'admin' AND OLD.is_active
           AND (TG_OP = 'DELETE'
                OR NEW.role IS DISTINCT FROM 'admin'
                OR NEW.is_active IS NOT TRUE
                OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id) THEN
            PERFORM 1 FROM public.users u
            WHERE u.tenant_id = OLD.tenant_id AND u.role = 'admin'
              AND u.is_active AND u.id <> OLD.id
            ORDER BY u.id
            FOR NO KEY UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'a tenant must keep one active admin'
                    USING ERRCODE = '23514', CONSTRAINT = '{TRIGGER}';
            END IF;
        END IF;
        RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
    END
    $$
"""
TRIGGER_SQL = f"""
    CREATE TRIGGER {TRIGGER}
    BEFORE UPDATE OF is_active, role, tenant_id OR DELETE ON public.users
    FOR EACH ROW EXECUTE FUNCTION {FUNCTION}()
"""


def upgrade() -> None:
    """Upgrade schema: audit table with RLS and grants, then the last-admin trigger."""
    # Fail fast instead of queueing behind long transactions on users.
    op.execute("SET LOCAL lock_timeout = '5s'")
    _check_owners()
    _create_audit_table()
    op.execute(FUNCTION_SQL)
    op.execute(f"REVOKE EXECUTE ON FUNCTION {FUNCTION}() FROM PUBLIC")
    op.execute(TRIGGER_SQL)


def downgrade() -> None:
    """Downgrade schema: drop the trigger, the function and the audit table.

    Stops, and changes nothing, when the audit table holds rows.
    """
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(f"DROP TRIGGER {TRIGGER} ON public.users")
    op.execute(f"DROP FUNCTION {FUNCTION}()")
    # FORCE binds the owner too: lift it so the owner counts every row.
    op.execute(f"ALTER TABLE public.{AUDIT_TABLE} NO FORCE ROW LEVEL SECURITY")
    rows = op.get_bind().execute(sa.text(AUDIT_ROWS_SQL)).scalar_one()
    if rows:
        raise RuntimeError(f"{AUDIT_TABLE} holds {rows} rows: export them, then purge, then retry")
    op.drop_table(AUDIT_TABLE)


def _check_owners() -> None:
    """Raise RuntimeError when users or tenants is missing or not owned by lawbyai_owner."""
    rows = op.get_bind().execute(sa.text(TABLE_OWNERS_SQL), {"names": list(CHECKED_TABLES)}).all()
    owners = {row[0]: row[1] for row in rows}
    problems = [
        f"table {name} is owned by {owners.get(name)}, not {OWNER_ROLE}"
        for name in CHECKED_TABLES
        if owners.get(name) != OWNER_ROLE
    ]
    if problems:
        raise RuntimeError("last-admin prerequisites not met: " + "; ".join(problems))


def _create_audit_table() -> None:
    """Create the append-only audit table: forced tenant RLS, SELECT and INSERT for the app."""
    op.create_table(
        AUDIT_TABLE,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "action IN (" + ", ".join(f"'{a}'" for a in ACTIONS) + ")", name=CHECK_NAME
        ),
    )
    op.create_index(
        f"ix_{AUDIT_TABLE}_tenant_id_created_at", AUDIT_TABLE, ["tenant_id", "created_at"]
    )
    op.execute(f"ALTER TABLE public.{AUDIT_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{AUDIT_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {AUDIT_POLICY} ON public.{AUDIT_TABLE} "
        f"USING (tenant_id = {TENANT}) WITH CHECK (tenant_id = {TENANT})"
    )
    op.execute(f"GRANT SELECT, INSERT ON public.{AUDIT_TABLE} TO {APP_ROLE}")
