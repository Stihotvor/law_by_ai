"""document status column and reject audit table

Adds ``legal_document.status`` (``needs_review`` | ``approved``) and the
``rejected_document`` audit table (issue #92). Existing rows are backfilled to
``approved``; new rows default to ``needs_review``. No RLS on either: review
state is global.

Revision ID: 963e40b83003
Revises: 4439761c5e40
Create Date: 2026-11-09 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP

# revision identifiers, used by Alembic.
revision: str = "963e40b83003"
down_revision: str | Sequence[str] | None = "4439761c5e40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Frozen literals: this revision must not change if ``DocumentStatus`` changes.
CHECK_NAME = "ck_legal_document_status"
CHECK_SQL = "status IN ('needs_review', 'approved')"
INDEX_NAME = "ix_rejected_document_source_url"


def upgrade() -> None:
    """Upgrade schema: status column, CHECK constraint, audit table and index."""
    # Fail fast instead of queueing behind long transactions on legal_document.
    op.execute("SET LOCAL lock_timeout = '5s'")
    # NOT NULL DEFAULT 'approved' is a fast default (no table rewrite) and
    # backfills existing rows to 'approved'. New rows then default to needs_review.
    op.add_column(
        "legal_document",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="approved"),
    )
    op.alter_column("legal_document", "status", server_default="needs_review")
    # NOT VALID then VALIDATE: the scan runs under a weaker lock than ADD CHECK.
    op.execute(
        f"ALTER TABLE legal_document ADD CONSTRAINT {CHECK_NAME} CHECK ({CHECK_SQL}) NOT VALID"
    )
    op.execute(f"ALTER TABLE legal_document VALIDATE CONSTRAINT {CHECK_NAME}")
    op.create_table(
        "rejected_document",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("admin", sa.String(length=256), nullable=False),
        sa.Column("rejected_at", TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index(INDEX_NAME, "rejected_document", ["source_url"], unique=False)


def downgrade() -> None:
    """Downgrade schema: drop the audit table, the CHECK and the status column."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_index(INDEX_NAME, table_name="rejected_document")
    op.drop_table("rejected_document")
    op.drop_constraint(CHECK_NAME, "legal_document", type_="check")
    op.drop_column("legal_document", "status")
