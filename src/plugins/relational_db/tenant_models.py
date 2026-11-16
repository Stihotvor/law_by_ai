"""ORM models for the RLS-scoped ``tenants`` and ``users`` tables (ADR-0013)."""

from __future__ import annotations

from sqlalchemy import String, text
from sqlalchemy.orm import Mapped, mapped_column

from data.models import Base

__all__ = ["Tenant", "User"]


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
