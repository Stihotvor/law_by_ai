"""Shared ORM models (issue #16).

Holds the SQLAlchemy declarative ``Base`` and the ``LegalDocument`` model.
``Base`` is shared with the user/tenant models in
``plugins.relational_db.postgres``, so all tables live on one
``Base.metadata`` that Alembic autogenerates against (``migrations/env.py``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class LegalDocument(Base):
    """Legal document model."""

    __tablename__ = "legal_document"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(512))
    content: Mapped[str] = mapped_column(String())
    source: Mapped[str] = mapped_column(String(256))
    source_url: Mapped[str] = mapped_column(String(1024))
    last_updated: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(JSONB, name="metadata")
    is_processed: Mapped[bool]
    tenant_id: Mapped[str | None] = mapped_column(String(64), default=None)
