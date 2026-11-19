"""reject audit append only: lawbyai_app loses UPDATE, DELETE, TRUNCATE

``rejected_document`` is an append-only audit log for the app role.
``lawbyai_app`` keeps SELECT, INSERT and the ``rejected_document_id_seq``
grants from ``b7e2d41c9a30``; it loses UPDATE, DELETE and TRUNCATE.

Retention rule: rows are kept forever. Only the owner (``lawbyai_owner``) can
fix or purge a row.

The downgrade grants back UPDATE and DELETE only. ``b7e2d41c9a30`` never
granted TRUNCATE, so the downgrade does not grant it either.

Revision ID: 81dde4a27be7
Revises: b7e2d41c9a30
Create Date: 2026-11-19 09:39:32.345976
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "81dde4a27be7"
down_revision: str | Sequence[str] | None = "b7e2d41c9a30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Literals are frozen so this revision does not change with the models.
APP_ROLE = "lawbyai_app"
AUDIT_TABLE = "public.rejected_document"


def upgrade() -> None:
    """Upgrade schema: revoke UPDATE, DELETE and TRUNCATE on the audit table from the app."""
    # Fail fast instead of queueing behind long transactions on rejected_document.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON {AUDIT_TABLE} FROM {APP_ROLE}")


def downgrade() -> None:
    """Downgrade schema: grant back UPDATE and DELETE (never TRUNCATE) to the app."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(f"GRANT UPDATE, DELETE ON {AUDIT_TABLE} TO {APP_ROLE}")
