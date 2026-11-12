"""users session version and normalised emails

Adds ``users.session_version`` and a trigger that bumps it when ``is_active``
or ``password_hash`` changes, so old login cookies stop working. Existing
emails are normalised to ``lower(btrim(email))`` and a CHECK keeps them so;
with it, ``uq_users_email`` is unique without regard to case. The upgrade
fails, and changes nothing, when two emails collide after normalising.

Revision ID: 77985ac8fa22
Revises: 963e40b83003
Create Date: 2026-11-12 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "77985ac8fa22"
down_revision: str | Sequence[str] | None = "963e40b83003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Frozen literals: this revision must not change if the model changes.
CHECK_NAME = "ck_users_email_normalised"
FUNCTION_NAME = "users_bump_session_version"
TRIGGER_NAME = "trg_users_session_version"


def upgrade() -> None:
    """Upgrade schema: session_version, normalised emails, CHECK and trigger."""
    # Fail fast instead of queueing behind long transactions on users.
    op.execute("SET LOCAL lock_timeout = '5s'")
    # Empty tenant setting: the RLS policy shows every users row.
    op.execute("SET LOCAL app.current_tenant = ''")
    # NOT NULL DEFAULT 0 is a fast default (no table rewrite).
    op.add_column(
        "users",
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT lower(btrim(email)) FROM users GROUP BY 1 HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'users emails collide after lower(btrim(email))';
            END IF;
        END
        $$
        """
    )
    op.execute("UPDATE users SET email = lower(btrim(email)) WHERE email <> lower(btrim(email))")
    op.create_check_constraint(CHECK_NAME, "users", "email = lower(btrim(email))")
    op.execute(
        f"""
        CREATE FUNCTION {FUNCTION_NAME}() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.session_version = OLD.session_version + 1;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {TRIGGER_NAME}
        BEFORE UPDATE OF is_active, password_hash ON users
        FOR EACH ROW
        WHEN (OLD.is_active IS DISTINCT FROM NEW.is_active
              OR OLD.password_hash IS DISTINCT FROM NEW.password_hash)
        EXECUTE FUNCTION {FUNCTION_NAME}()
        """
    )


def downgrade() -> None:
    """Downgrade schema: drop the trigger, function, CHECK and column.

    Emails stay lowercase. All session versions reset, so rotate
    ``AUTH_COOKIE_KEY`` after a downgrade.
    """
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(f"DROP TRIGGER {TRIGGER_NAME} ON users")
    op.execute(f"DROP FUNCTION {FUNCTION_NAME}()")
    op.drop_constraint(CHECK_NAME, "users", type_="check")
    op.drop_column("users", "session_version")
