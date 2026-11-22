"""ORM models for the RLS-scoped ``tenants`` and ``users`` tables (ADR-0013)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import TIMESTAMP, BigInteger, Identity, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from data.models import Base

__all__ = ["AdminActionAudit", "Tenant", "User"]


class Tenant(Base):
    """A tenant (workspace) row. ``id`` doubles as the tenant key everywhere."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))


class User(Base):
    """A platform user row (ADR-0013). Email is unique across tenants."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    email: Mapped[str] = mapped_column(String(256), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(256), default="")
    is_active: Mapped[bool] = mapped_column(default=True)
    session_version: Mapped[int] = mapped_column(server_default=text("0"))


class AdminActionAudit(Base):
    """Append-only audit row of an admin user action (migration ``c4a91e7f2b58``).

    No foreign keys: a row outlives the users it names. ``lawbyai_app`` has only
    SELECT and INSERT. Row level security scopes reads and writes to the tenant.
    """

    __tablename__ = "admin_action_audit"
    __table_args__ = (
        Index("ix_admin_action_audit_tenant_id_created_at", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
