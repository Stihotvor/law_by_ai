"""PostgreSQL data store: legal-document CRUD + user/tenant models with RLS
(ADR-0003, ADR-0013, ADR-0014).

Direct PostgreSQL integration using SQLAlchemy 2.0 ORM (no plugin indirection,
ADR-0014). Schema is managed by Alembic migrations (issue #9) — see
``migrations/`` and ``docs/migrations.md``.

- Document CRUD (issue #9): shared ``legal_document`` table, no RLS — the corpus
  is shared, access is scoped by ``tenant_id`` at the query layer.
- User/tenant management (issue #52 / ADR-0013): ``users`` and ``tenants`` tables
  with PostgreSQL row-level security keyed on the current tenant.

RLS model: queries are scoped to the tenant stored in the ``app.current_tenant``
session setting (see :func:`apply_tenant_rls`), which is populated from the
``core.security.tenant`` contextvar when a transaction begins. When the setting
is empty (platform-level operations), tenant-owned tables are fully visible.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import String, create_engine, event, select, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from config.settings import get_settings
from core.security import get_current_tenant, hash_password

# Session setting used by the RLS policies. Empty string == no tenant scoping.
TENANT_SETTING = "app.current_tenant"

# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# RLS helpers
# ---------------------------------------------------------------------------


def apply_tenant_rls(engine) -> None:
    """Register a transaction hook that scopes every query to the current tenant.

    On each transaction begin the hook copies the current ``tenant_id`` from the
    ``core.security.tenant`` contextvar into the transaction-local
    ``app.current_tenant`` setting, which the RLS policies inspect. Call this on
    every engine that must honor tenant isolation (including test engines).
    """
    event.listen(engine, "begin", _set_tenant_setting)


def _set_tenant_setting(conn) -> None:
    tenant_id = get_current_tenant()
    conn.execute(
        text("SELECT set_config(:key, :value, true)"),
        {"key": TENANT_SETTING, "value": tenant_id or ""},
    )


def _upgrade_schema() -> None:
    """Run Alembic migrations to bring the schema up to date (issue #9).

    Locates the repo's ``alembic.ini`` and ``migrations/`` directory relative to
    this file and applies ``head``. The migration environment reads the DB URL
    from ``config.settings``, so it stays consistent with this module's engine.
    """
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    repo_root = Path(__file__).resolve().parents[3]
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "migrations"))
    command.upgrade(cfg, "head")


# ---------------------------------------------------------------------------
# Data store class
# ---------------------------------------------------------------------------


class PostgreSQLStore:
    """Direct PostgreSQL data store (ADR-0014, replaces the old plugin).

    Supports:
    - Legal-document CRUD (issue #9)
    - User/tenant management (issue #52, ADR-0013)
    - PostgreSQL row-level security (ADR-0003)
    """

    def __init__(self) -> None:
        self._engine = None
        self._initialized = False

    # --- lifecycle ----------------------------------------------------------

    def initialize(self) -> None:
        """Connect and bring the schema up to date via Alembic migrations."""
        if self._initialized:
            return
        self._engine = create_engine(get_settings().postgres_url, future=True)
        apply_tenant_rls(self._engine)
        _upgrade_schema()
        self._initialized = True

    def close(self) -> None:
        """Release the engine's connection pool."""
        if self._engine is None:
            return
        self._engine.dispose()
        self._engine = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    # --- documents (issue #9) -----------------------------------------------

    def save_document(self, document: dict[str, Any], tenant_id: str | None = None) -> str:
        """Insert or update a document row; returns its id.

        If *document* has no ``id``, a new one is generated and written back
        into the dict, so re-saving the same dict upserts the same row.
        """
        self._ensure_initialized()
        doc_id = document.get("id") or str(uuid.uuid4())
        document["id"] = doc_id
        tenant = tenant_id or document.get("tenant_id") or get_current_tenant()
        with Session(self._engine) as session:
            row = session.get(LegalDocument, doc_id)
            if row is None:
                session.add(
                    LegalDocument(
                        id=doc_id,
                        title=document["title"],
                        content=document["content"],
                        source=document["source"],
                        source_url=document["source_url"],
                        last_updated=_parse_dt(
                            document.get("last_updated"),
                            default=datetime.now(UTC),
                        ),
                        metadata_=document.get("metadata"),
                        is_processed=bool(document.get("is_processed", False)),
                        tenant_id=tenant,
                    )
                )
            else:
                self.update_document(doc_id, document, tenant_id=tenant)
            session.commit()
        return doc_id

    def get_document(self, document_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
        """Return a document row as a dict, or ``None`` if missing."""
        self._ensure_initialized()
        with Session(self._engine) as session:
            row = session.get(LegalDocument, document_id)
            return _doc_to_dict(row) if row is not None else None

    def search_documents(
        self, query: str, *, limit: int = 10, tenant_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Case-insensitive LIKE search over title and content."""
        self._ensure_initialized()
        pattern = f"%{query}%"
        with Session(self._engine) as session:
            rows = (
                session.execute(
                    select(LegalDocument)
                    .where(
                        LegalDocument.title.ilike(pattern) | LegalDocument.content.ilike(pattern)
                    )
                    .order_by(LegalDocument.last_updated.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [_doc_to_dict(r) for r in rows]

    def get_recent_changes(
        self, *, since: str | None = None, tenant_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Most recently updated documents, newest first."""
        self._ensure_initialized()
        stmt = select(LegalDocument).order_by(LegalDocument.last_updated.desc())
        if since:
            stmt = stmt.where(LegalDocument.last_updated > _parse_dt(since))
        with Session(self._engine) as session:
            rows = session.execute(stmt).scalars().all()
            return [_doc_to_dict(r) for r in rows]

    def delete_document(self, document_id: str, tenant_id: str | None = None) -> None:
        """Delete a document row; missing ids are a no-op."""
        self._ensure_initialized()
        with Session(self._engine) as session:
            row = session.get(LegalDocument, document_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def update_document(
        self, document_id: str, document: dict[str, Any], tenant_id: str | None = None
    ) -> None:
        """Merge ``document`` fields into the row; raises ``KeyError`` if missing."""
        self._ensure_initialized()
        with Session(self._engine) as session:
            row = session.get(LegalDocument, document_id)
            if row is None:
                raise KeyError(f"Document not found: {document_id}")
            for key, value in document.items():
                if key == "metadata":
                    row.metadata_ = value
                elif key == "last_updated":
                    row.last_updated = _parse_dt(value)
                elif key != "id" and hasattr(row, key):
                    setattr(row, key, value)
            session.commit()

    # --- users / tenants (issue #52, ADR-0013) ------------------------------

    def create_tenant(self, name: str, tenant_id: str | None = None) -> dict[str, Any]:
        """Create a tenant; returns its record dict."""
        self._ensure_initialized()
        with Session(self._engine) as session:
            tenant = Tenant(id=tenant_id or str(uuid.uuid4()), name=name)
            session.add(tenant)
            session.commit()
            return _tenant_to_dict(tenant)

    def create_user(
        self,
        *,
        email: str,
        password: str,
        role: str,
        tenant_id: str,
        name: str = "",
    ) -> dict[str, Any]:
        """Create a user with a bcrypt-hashed password; returns its record dict."""
        self._ensure_initialized()
        with Session(self._engine) as session:
            user = User(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                email=email,
                password_hash=hash_password(password),
                role=role,
                name=name,
                is_active=True,
            )
            session.add(user)
            session.commit()
            return _user_to_dict(user)

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        """Return the user record for *email*, or ``None`` if not found."""
        self._ensure_initialized()
        with Session(self._engine) as session:
            row = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
            return _user_to_dict(row) if row is not None else None

    def list_users(self) -> list[dict[str, Any]]:
        """All users visible under the current tenant scoping."""
        self._ensure_initialized()
        with Session(self._engine) as session:
            rows = session.execute(select(User).order_by(User.email)).scalars().all()
            return [_user_to_dict(r) for r in rows]

    def list_tenants(self) -> list[dict[str, Any]]:
        """All tenants visible under the current tenant scoping."""
        self._ensure_initialized()
        with Session(self._engine) as session:
            rows = session.execute(select(Tenant).order_by(Tenant.name)).scalars().all()
            return [_tenant_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _parse_dt(value: Any, *, default: datetime | None = None) -> datetime:
    if value is None:
        return default or datetime.now(UTC)
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _doc_to_dict(row: LegalDocument) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "content": row.content,
        "source": row.source,
        "source_url": row.source_url,
        "last_updated": row.last_updated.isoformat(),
        "metadata": row.metadata_,
        "is_processed": row.is_processed,
        "tenant_id": row.tenant_id,
    }


def _user_to_dict(row: User) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "email": row.email,
        "role": row.role,
        "name": row.name,
        "is_active": row.is_active,
    }


def _tenant_to_dict(row: Tenant) -> dict[str, Any]:
    return {"id": row.id, "name": row.name}
