"""Shared ORM models (issue #16).

Holds the SQLAlchemy declarative ``Base``, the ``LegalDocument`` model, the
``RejectedDocument`` audit model (issue #92) and the procedure knowledge base
tables ``Procedure``, ``ProcedureStep`` and ``ProcedureRevision``.
``Base`` is shared with the user/tenant models in
``plugins.relational_db.postgres``, so all tables live on one
``Base.metadata`` that Alembic autogenerates against (``migrations/env.py``).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Identity,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql.elements import conv


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
            name=conv("ck_legal_document_status"),
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


_KEBAB = "'^[a-z0-9]+(-[a-z0-9]+)*$'"


class Procedure(Base):
    """A procedure: shared reference data, no ``tenant_id`` and no RLS.

    ``lawbyai_app`` has SELECT, INSERT and UPDATE; no import deletes a procedure.
    """

    __tablename__ = "procedure"
    __table_args__ = (
        UniqueConstraint("slug", name=conv("uq_procedure_slug")),
        CheckConstraint(f"slug ~ {_KEBAB}", name=conv("ck_procedure_slug")),
        CheckConstraint("btrim(title) <> ''", name=conv("ck_procedure_title")),
        CheckConstraint("revision >= 1", name=conv("ck_procedure_revision_min")),
        CheckConstraint("schema_version >= 1", name=conv("ck_procedure_schema_version_min")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    slug: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    schema_version: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )


class ProcedureStep(Base):
    """One step of a procedure. Steps are replaced on import; history is in revisions."""

    __tablename__ = "procedure_step"
    __table_args__ = (
        PrimaryKeyConstraint("procedure_id", "position", name=conv("pk_procedure_step")),
        UniqueConstraint("procedure_id", "key", name=conv("uq_procedure_step_procedure_id_key")),
        CheckConstraint("position >= 0", name=conv("ck_procedure_step_position")),
        CheckConstraint(f"key ~ {_KEBAB}", name=conv("ck_procedure_step_key")),
        CheckConstraint("btrim(text) <> ''", name=conv("ck_procedure_step_text")),
        CheckConstraint(
            "btrim(verify_with_office) <> ''", name=conv("ck_procedure_step_verify_with_office")
        ),
        CheckConstraint("source_url LIKE 'https://%'", name=conv("ck_procedure_step_source_url")),
    )

    procedure_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("procedure.id", name=conv("fk_procedure_step_procedure_id"), ondelete="CASCADE"),
    )
    position: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    last_checked: Mapped[date] = mapped_column(Date)
    verify_with_office: Mapped[str] = mapped_column(Text)


class ProcedureRevision(Base):
    """Append-only revision row; ``content`` is ``Procedure.model_dump(mode="json")``.

    ON DELETE RESTRICT: a cascade would bypass the append-only rule.
    ``lawbyai_app`` has SELECT and INSERT only.
    """

    __tablename__ = "procedure_revision"
    __table_args__ = (
        UniqueConstraint(
            "procedure_id", "revision", name=conv("uq_procedure_revision_procedure_id_revision")
        ),
        CheckConstraint("revision >= 1", name=conv("ck_procedure_revision_revision_min")),
        CheckConstraint(
            "jsonb_typeof(content) = 'object'", name=conv("ck_procedure_revision_content")
        ),
        CheckConstraint("btrim(actor) <> ''", name=conv("ck_procedure_revision_actor")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    procedure_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "procedure.id", name=conv("fk_procedure_revision_procedure_id"), ondelete="RESTRICT"
        ),
    )
    revision: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    actor: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
