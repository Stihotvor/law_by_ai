"""initial schema: legal_document, users, tenants

Revision ID: 4439761c5e40
Revises:
Create Date: 2026-08-12 21:48:22.947412
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

# revision identifiers, used by Alembic.
revision: str = "4439761c5e40"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_SETTING = "app.current_tenant"


def upgrade() -> None:
    """Upgrade schema: core tables + tenant RLS policies."""
    op.create_table(
        "legal_document",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("source", sa.String(length=256), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("last_updated", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("is_processed", sa.Boolean(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
    )
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=256), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=256), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"], unique=False)
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    op.execute(
        f"""
        ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
        ALTER TABLE tenants FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenants_isolation ON tenants
        USING (current_setting('{TENANT_SETTING}', true) = ''
               OR id = current_setting('{TENANT_SETTING}', true))
        WITH CHECK (current_setting('{TENANT_SETTING}', true) = ''
                    OR id = current_setting('{TENANT_SETTING}', true));
        """
    )
    op.execute(
        f"""
        ALTER TABLE users ENABLE ROW LEVEL SECURITY;
        ALTER TABLE users FORCE ROW LEVEL SECURITY;
        CREATE POLICY users_isolation ON users
        USING (current_setting('{TENANT_SETTING}', true) = ''
               OR tenant_id IS NULL
               OR tenant_id = current_setting('{TENANT_SETTING}', true))
        WITH CHECK (current_setting('{TENANT_SETTING}', true) = ''
                    OR tenant_id = current_setting('{TENANT_SETTING}', true));
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS users_isolation ON users;")
    op.execute("DROP POLICY IF EXISTS tenants_isolation ON tenants;")
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE tenants DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_table("users")
    op.drop_table("tenants")
    op.drop_table("legal_document")
