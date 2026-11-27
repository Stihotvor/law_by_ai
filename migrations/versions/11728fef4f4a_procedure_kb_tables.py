"""procedure knowledge base tables: procedure, procedure_step, procedure_revision

Shared reference data: no ``tenant_id`` and no row level security. Every column
is NOT NULL. The CHECK constraints are a second guard after pydantic; the "date
not in the future" rule stays in pydantic only.

``procedure_revision`` is append-only history. Its foreign key is ON DELETE
RESTRICT, because a cascade would bypass the append-only rule. ``lawbyai_app``
gets explicit grants and never TRUNCATE:

- ``procedure``: SELECT, INSERT, UPDATE (no DELETE).
- ``procedure_step``: SELECT, INSERT, UPDATE, DELETE.
- ``procedure_revision``: SELECT, INSERT.

The downgrade stops, and changes nothing, while ``procedure_revision`` holds rows.

Revision ID: 11728fef4f4a
Revises: c4a91e7f2b58
Create Date: 2026-11-27 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "11728fef4f4a"
down_revision: str | Sequence[str] | None = "c4a91e7f2b58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Frozen literals: this revision must not change if the model changes.
APP_ROLE = "lawbyai_app"
PROCEDURE = "procedure"
STEP = "procedure_step"
REVISION = "procedure_revision"
KEBAB = "'^[a-z0-9]+(-[a-z0-9]+)*$'"
GRANTS = {
    PROCEDURE: "SELECT, INSERT, UPDATE",
    STEP: "SELECT, INSERT, UPDATE, DELETE",
    REVISION: "SELECT, INSERT",
}
REVISION_ROWS_SQL = "SELECT count(*) FROM public.procedure_revision"


def upgrade() -> None:
    """Upgrade schema: the three procedure tables and the app role grants."""
    # Fail fast instead of queueing behind long transactions.
    op.execute("SET LOCAL lock_timeout = '5s'")
    _create_procedure()
    _create_step()
    _create_revision()
    for table, privileges in GRANTS.items():
        op.execute(f"REVOKE ALL ON public.{table} FROM {APP_ROLE}")
        op.execute(f"GRANT {privileges} ON public.{table} TO {APP_ROLE}")


def downgrade() -> None:
    """Downgrade schema: drop the three tables.

    Stops, and changes nothing, when ``procedure_revision`` holds rows.
    """
    op.execute("SET LOCAL lock_timeout = '5s'")
    # Block new revision rows between the count and the drop.
    op.execute(f"LOCK TABLE public.{REVISION} IN ACCESS EXCLUSIVE MODE")
    rows = op.get_bind().execute(sa.text(REVISION_ROWS_SQL)).scalar_one()
    if rows:
        raise RuntimeError(f"{REVISION} holds {rows} rows: export them, then purge, then retry")
    op.drop_table(REVISION)
    op.drop_table(STEP)
    op.drop_table(PROCEDURE)


def _create_procedure() -> None:
    op.create_table(
        PROCEDURE,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("slug", name="uq_procedure_slug"),
        sa.CheckConstraint(f"slug ~ {KEBAB}", name="ck_procedure_slug"),
        sa.CheckConstraint("btrim(title) <> ''", name="ck_procedure_title"),
        sa.CheckConstraint("revision >= 1", name="ck_procedure_revision_min"),
        sa.CheckConstraint("schema_version >= 1", name="ck_procedure_schema_version_min"),
    )


def _create_step() -> None:
    op.create_table(
        STEP,
        sa.Column("procedure_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("last_checked", sa.Date(), nullable=False),
        sa.Column("verify_with_office", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("procedure_id", "position", name="pk_procedure_step"),
        sa.ForeignKeyConstraint(
            ["procedure_id"],
            [f"{PROCEDURE}.id"],
            name="fk_procedure_step_procedure_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("procedure_id", "key", name="uq_procedure_step_procedure_id_key"),
        sa.CheckConstraint("position >= 0", name="ck_procedure_step_position"),
        sa.CheckConstraint(f"key ~ {KEBAB}", name="ck_procedure_step_key"),
        sa.CheckConstraint("btrim(text) <> ''", name="ck_procedure_step_text"),
        sa.CheckConstraint(
            "btrim(verify_with_office) <> ''", name="ck_procedure_step_verify_with_office"
        ),
        sa.CheckConstraint("source_url LIKE 'https://%'", name="ck_procedure_step_source_url"),
    )


def _create_revision() -> None:
    op.create_table(
        REVISION,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("procedure_id", sa.BigInteger(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content", JSONB(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["procedure_id"],
            [f"{PROCEDURE}.id"],
            name="fk_procedure_revision_procedure_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "procedure_id", "revision", name="uq_procedure_revision_procedure_id_revision"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_procedure_revision_revision_min"),
        sa.CheckConstraint(
            "jsonb_typeof(content) = 'object'", name="ck_procedure_revision_content"
        ),
        sa.CheckConstraint("btrim(actor) <> ''", name="ck_procedure_revision_actor"),
    )
