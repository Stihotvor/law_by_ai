"""Shared ORM models (issue #16).

Holds the SQLAlchemy declarative ``Base``, the ``LegalDocument`` model and the
``RejectedDocument`` audit model (issue #92).
``Base`` is shared with the user/tenant models in
``plugins.relational_db.postgres``, so all tables live on one
``Base.metadata`` that Alembic autogenerates against (``migrations/env.py``).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, String
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class DocumentStatus(StrEnum):
    """Review state of a document (issue #92).

    Review state is global (one admin control for every tenant). A rejected
    document is deleted, so there is no ``rejected`` value; the reject is
    recorded in ``rejected_document``.
    """

    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"


_STATUS_SQL_VALUES = ", ".join(f"'{s.value}'" for s in DocumentStatus)


class Base(DeclarativeBase):
    pass


class LegalDocument(Base):
    """Legal document model."""

    __tablename__ = "legal_document"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_STATUS_SQL_VALUES})",
            name="ck_legal_document_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(512))
    content: Mapped[str] = mapped_column(String())
    source: Mapped[str] = mapped_column(String(256))
    source_url: Mapped[str] = mapped_column(String(1024))
    last_updated: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(JSONB, name="metadata")
    is_processed: Mapped[bool]
    tenant_id: Mapped[str | None] = mapped_column(String(64), default=None)
    status: Mapped[str] = mapped_column(
        String(32),
        default=DocumentStatus.NEEDS_REVIEW.value,
        server_default=DocumentStatus.NEEDS_REVIEW.value,
    )


class RejectedDocument(Base):
    """Audit row for a rejected (deleted) document (issue #92).

    No foreign key to ``legal_document``: the document row is deleted on reject.
    No ``tenant_id``: review state is global. ``source_url`` is indexed for
    :meth:`PostgreSQLStore.is_rejected`.
    """

    __tablename__ = "rejected_document"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String(64))
    source_url: Mapped[str] = mapped_column(String(1024), index=True)
    admin: Mapped[str] = mapped_column(String(256))
    rejected_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
