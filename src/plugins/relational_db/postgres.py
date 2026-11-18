"""PostgreSQL data store: legal-document CRUD + user/tenant models with RLS
(ADR-0003, ADR-0013, ADR-0014).

Direct PostgreSQL integration using SQLAlchemy 2.0 ORM (no plugin indirection,
ADR-0014). Schema is managed by Alembic migrations (issue #9) — see
``migrations/`` and ``docs/migrations.md``. Migrations run as the owner role;
:meth:`PostgreSQLStore.initialize` only checks that the database is at head.

- Document CRUD (issue #9): shared ``legal_document`` table, no RLS — the corpus
  is shared, access is scoped by ``tenant_id`` at the query layer.
- Document reject (issue #92): delete the row and write a ``rejected_document``
  audit row in one transaction, then notify an optional deletion hook.
- User/tenant management (issue #52 / ADR-0013): ``users`` and ``tenants`` tables
  with PostgreSQL row-level security keyed on the current tenant.

RLS model: queries are scoped to the tenant stored in the ``app.current_tenant``
session setting (see :func:`apply_tenant_rls`), which is populated from the
``core.security.tenant`` contextvar when a transaction begins. The policies fail
closed: when the setting is empty, tenant-owned tables return no rows. Login,
which runs before a tenant is known, calls the ``auth_lookup_user`` function.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, create_engine, delete, event, exists, or_, select, text, update
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.sql import ColumnElement

from config.settings import PoolConfig, get_settings
from core.security import get_current_tenant, hash_password
from core.security.login_throttle import normalise_email
from data.models import Base, DocumentStatus, LegalDocument, RejectedDocument
from plugins.relational_db.mappers import apply_update as _apply_update
from plugins.relational_db.mappers import doc_to_dict as _doc_to_dict
from plugins.relational_db.mappers import login_user_to_dict as _login_user_to_dict  # noqa: F401 (re-export)
from plugins.relational_db.mappers import parse_dt as _parse_dt
from plugins.relational_db.mappers import tenant_to_dict as _tenant_to_dict
from plugins.relational_db.mappers import user_to_dict as _user_to_dict
from plugins.relational_db.schema_check import SchemaNotAtHeadError
from plugins.relational_db.schema_check import check_schema_head as _check_schema_head
from plugins.relational_db.tenant_models import Tenant, User

# ``Base`` and ``LegalDocument`` live in ``data.models`` (issue #16); re-exported
# here so existing imports (e.g. ``migrations/env.py``) keep working.
__all__ = [
    "TENANT_SETTING",
    "Base",
    "LegalDocument",
    "PostgreSQLStore",
    "SchemaNotAtHeadError",
    "StoreDocumentNotFoundError",
    "Tenant",
    "User",
    "apply_tenant_rls",
]

# Session setting used by the RLS policies. Empty string == no rows (fail closed).
TENANT_SETTING = "app.current_tenant"
# Seconds a caller waits for a free pool connection before the pool raises.
POOL_TIMEOUT_SECONDS = 30
# Login lookup (SECURITY DEFINER): the login columns of one user in any tenant.
_AUTH_LOOKUP_SQL = text("SELECT * FROM public.auth_lookup_user(:email)")
_LOGIN_KEYS = ("id", "tenant_id", "email", "role", "name", "is_active")
_LOGIN_KEYS += ("password_hash", "session_version")
_log = logging.getLogger(__name__)


class StoreDocumentNotFoundError(KeyError):
    """No ``legal_document`` row the caller can write has the given id.

    A ``KeyError`` (so a ``LookupError``) with a plain ``str``, no quotes.
    """

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else ""


def _not_found(document_id: str) -> StoreDocumentNotFoundError:
    return StoreDocumentNotFoundError(f"Document not found: {document_id}")


def _resolve_tenant(tenant_id: str | None) -> str | None:
    """Caller tenant: the argument, else the context; ``""`` counts as ``None``."""
    return tenant_id or get_current_tenant() or None


def _require_writable(
    row: LegalDocument | None, document_id: str, tenant: str | None
) -> LegalDocument:
    """Return *row* when *tenant* owns it (``NULL == NULL``); else raise not found."""
    if row is None or row.tenant_id != tenant:
        raise _not_found(document_id)
    return row


def _readable_by(tenant: str | None) -> ColumnElement[bool]:
    """Read predicate: own and shared rows for a tenant, only shared rows for none."""
    if tenant is None:
        return LegalDocument.tenant_id.is_(None)
    return or_(LegalDocument.tenant_id == tenant, LegalDocument.tenant_id.is_(None))


def _owned_by(tenant: str | None) -> ColumnElement[bool]:
    """Write predicate: the row tenant is *tenant* (``NULL`` equals ``NULL``)."""
    return LegalDocument.tenant_id.is_not_distinct_from(tenant)


def _owned_row_for_update(document_id: str, tenant: str | None) -> Select[LegalDocument]:
    """``SELECT ... FOR UPDATE`` of *document_id* only when *tenant* owns it (NULL-safe)."""
    return (
        select(LegalDocument)
        .where(LegalDocument.id == document_id, _owned_by(tenant))
        .with_for_update()
    )


def _commit(session: Session, document_id: str) -> None:
    """Commit (which flushes); a ``StaleDataError`` from it rolls back and raises not found."""
    try:
        session.commit()
    except StaleDataError as exc:
        session.rollback()
        raise _not_found(document_id) from exc


def _new_document(doc_id: str, document: dict[str, Any], tenant: str | None) -> LegalDocument:
    """Build an insert row; ``status`` and payload ``tenant_id`` are not read."""
    return LegalDocument(
        id=doc_id,
        title=document["title"],
        content=document["content"],
        source=document["source"],
        source_url=document["source_url"],
        last_updated=_parse_dt(document.get("last_updated"), default=datetime.now(UTC)),
        metadata_=document.get("metadata"),
        is_processed=bool(document.get("is_processed", False)),
        tenant_id=tenant,
        status=DocumentStatus.NEEDS_REVIEW.value,
    )


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


def _warn_dropped(operation: str, keys: list[str]) -> None:
    """Log one warning naming the operation and dropped keys; no values, no document id."""
    if keys:
        _log.warning("%s ignored keys: %r", operation, keys)


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

    def __init__(
        self,
        on_document_deleted: Callable[[str], None] | None = None,
        *,
        pool: PoolConfig | None = None,
    ) -> None:
        self._engine = None
        self._initialized = False
        # Called once with the document id after a reject commits (issue #92).
        # Errors it raises are logged, not re-raised.
        self._on_document_deleted = on_document_deleted
        # None means the app pool, read from the settings in initialize().
        self._pool = pool

    # --- lifecycle ----------------------------------------------------------

    def initialize(self) -> None:
        """Connect and check the Alembic head; raise SchemaNotAtHeadError if not at head.

        A bad app pool setting raises ``ValueError`` before any engine exists.
        """
        if self._initialized:
            return
        settings = get_settings()
        cfg = self._pool or settings.app_pool_config()
        engine = create_engine(
            settings.postgres_url,
            future=True,
            pool_size=cfg.size,
            max_overflow=cfg.max_overflow,
            pool_pre_ping=True,
            pool_timeout=POOL_TIMEOUT_SECONDS,
        )
        try:
            _check_schema_head(engine)
        except Exception:
            engine.dispose()
            raise
        apply_tenant_rls(engine)
        self._engine = engine
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

        The caller tenant is the ``tenant_id`` argument, else the context
        tenant (``""`` counts as not given); a payload ``tenant_id`` never
        picks it. If *document* has no ``id``, a new one is generated and
        written back into the dict. A new row gets the caller tenant and
        ``needs_review``. An existing row is updated only when the caller
        tenant owns it (a shared row only with no tenant); it keeps its
        ``status``, ``tenant_id`` and ``id``. Otherwise
        :class:`StoreDocumentNotFoundError` is raised, nothing is written and
        *document* is not changed. Dropped key names (never values) are logged
        as one warning. Guard limit: a caller with no tenant can write every
        shared row; caller RBAC (``admin``) is the only guard until RLS exists.
        """
        self._ensure_initialized()
        tenant = _resolve_tenant(tenant_id)
        doc_id = document.get("id") or str(uuid.uuid4())
        with Session(self._engine) as session:
            row = session.get(LegalDocument, doc_id, with_for_update=True)
            if row is None:
                document["id"] = doc_id
                session.add(_new_document(doc_id, document, tenant))
                dropped = sorted(k for k in ("status", "tenant_id") if k in document)
            else:
                dropped = _apply_update(_require_writable(row, doc_id, tenant), document)
            _commit(session, doc_id)
        _warn_dropped("save_document", dropped)
        return doc_id

    def get_document(self, document_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
        """Return a row the caller tenant can read as a dict; ``None`` if missing or foreign.

        Tenant as in :meth:`save_document`: own and shared rows, or shared only with no tenant.
        """
        self._ensure_initialized()
        stmt = select(LegalDocument).where(
            LegalDocument.id == document_id, _readable_by(_resolve_tenant(tenant_id))
        )
        with Session(self._engine) as session:
            row = session.execute(stmt).scalar_one_or_none()
            return _doc_to_dict(row) if row is not None else None

    def search_documents(
        self, query: str, *, limit: int = 10, tenant_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Case-insensitive LIKE search over title and content, newest first.

        Only rows the caller can read (see :meth:`get_document`), filtered before *limit*.
        """
        self._ensure_initialized()
        pattern = f"%{query}%"
        stmt = (
            select(LegalDocument)
            .where(
                LegalDocument.title.ilike(pattern) | LegalDocument.content.ilike(pattern),
                _readable_by(_resolve_tenant(tenant_id)),
            )
            .order_by(LegalDocument.last_updated.desc())
            .limit(limit)
        )
        with Session(self._engine) as session:
            rows = session.execute(stmt).scalars().all()
            return [_doc_to_dict(r) for r in rows]

    def get_recent_changes(
        self, *, since: str | None = None, tenant_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Rows the caller tenant can read (see :meth:`get_document`), newest first."""
        self._ensure_initialized()
        stmt = (
            select(LegalDocument)
            .where(_readable_by(_resolve_tenant(tenant_id)))
            .order_by(LegalDocument.last_updated.desc())
        )
        if since:
            stmt = stmt.where(LegalDocument.last_updated > _parse_dt(since))
        with Session(self._engine) as session:
            rows = session.execute(stmt).scalars().all()
            return [_doc_to_dict(r) for r in rows]

    def delete_document(self, document_id: str, tenant_id: str | None = None) -> None:
        """Delete a row the caller tenant owns (write rule) in one ``DELETE`` statement.

        A missing, foreign or (for a tenant) shared id deletes nothing, with no
        error. Guard limit: a caller with no tenant can delete every shared row;
        caller RBAC (``admin``) is the only guard until RLS exists.
        """
        self._ensure_initialized()
        stmt = (
            delete(LegalDocument)
            .where(LegalDocument.id == document_id, _owned_by(_resolve_tenant(tenant_id)))
            .execution_options(synchronize_session=False)
        )
        with Session(self._engine) as session:
            session.execute(stmt)
            session.commit()

    def update_document(
        self, document_id: str, document: dict[str, Any], tenant_id: str | None = None
    ) -> None:
        """Merge editable ``document`` fields into a row the caller tenant owns.

        The caller tenant is resolved as in :meth:`save_document`. Raises
        :class:`StoreDocumentNotFoundError` (a ``KeyError``) with the same text
        for a missing row and a row of another tenant; nothing is written.
        ``status``, ``tenant_id`` and unknown keys are dropped; their names
        (never values) are logged as one warning. Guard limit: a caller with no
        tenant can write every shared row; caller RBAC is the only guard.
        Only a row the caller owns is locked, so a foreign update never waits
        on the owner's lock.
        """
        self._ensure_initialized()
        tenant = _resolve_tenant(tenant_id)
        with Session(self._engine) as session:
            row = session.execute(_owned_row_for_update(document_id, tenant)).scalar_one_or_none()
            if row is None:
                raise _not_found(document_id)
            dropped = _apply_update(row, document)
            _commit(session, document_id)
        _warn_dropped("update_document", dropped)

    # --- reject (issue #92) -------------------------------------------------

    def reject(self, document_id: str, admin: str) -> None:
        """Delete a document and record the reject in ``rejected_document``.

        ``DELETE ... RETURNING`` and the audit insert share one transaction, so
        of two concurrent rejects only one deletes the row and writes the audit
        row. After commit the ``on_document_deleted`` hook (if set) is called
        once. Raises :class:`StoreDocumentNotFoundError` for an unknown id;
        nothing is written and the hook is not called. Review state is global:
        there is no tenant check.
        """
        self._ensure_initialized()
        stmt = (
            delete(LegalDocument)
            .where(LegalDocument.id == document_id)
            .returning(LegalDocument.source_url)
            .execution_options(synchronize_session=False)
        )
        with Session(self._engine) as session, session.begin():
            source_url = session.execute(stmt).scalar_one_or_none()
            if source_url is None:
                raise StoreDocumentNotFoundError(f"Document not found: {document_id}")
            session.add(
                RejectedDocument(
                    document_id=document_id,
                    source_url=source_url,
                    admin=admin,
                    rejected_at=datetime.now(UTC),
                )
            )
        self._notify_document_deleted(document_id)

    def _notify_document_deleted(self, document_id: str) -> None:
        """Call the deletion hook; log and swallow its errors (the reject is done)."""
        if self._on_document_deleted is None:
            return
        try:
            self._on_document_deleted(document_id)
        except Exception:
            _log.exception("on_document_deleted hook failed for document %s", document_id)

    def is_rejected(self, source_url: str) -> bool:
        """True when a document with *source_url* has been rejected."""
        self._ensure_initialized()
        stmt = select(exists().where(RejectedDocument.source_url == source_url))
        with Session(self._engine) as session:
            return bool(session.execute(stmt).scalar())

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
                email=email.strip().lower(),
                password_hash=hash_password(password),
                role=role,
                name=name,
                is_active=True,
            )
            session.add(user)
            session.commit()
            return _user_to_dict(user)

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        """Return the user for *email* in the current tenant; ``None`` with no tenant set."""
        self._ensure_initialized()
        stmt = select(User).where(User.email == email.strip().lower())
        with Session(self._engine) as session:
            row = session.execute(stmt).scalar_one_or_none()
            return _user_to_dict(row) if row is not None else None

    def get_login_user(self, email: str) -> dict[str, Any] | None:
        """Return the login row for *email* across all tenants, or ``None``.

        Calls ``auth_lookup_user`` (needs no tenant). Raises ``OperationalError`` when down.
        """
        self._ensure_initialized()
        with Session(self._engine) as session:
            result = session.execute(_AUTH_LOOKUP_SQL, {"email": normalise_email(email)})
            row = result.mappings().one_or_none()
            return {key: row[key] for key in _LOGIN_KEYS} if row is not None else None

    def bump_session_version(self, user_id: str) -> None:
        """Add one to the user's ``session_version`` under the current tenant.

        Every cookie signed with the old version stops working (server-side logout).
        """
        self._ensure_initialized()
        stmt = (
            update(User).where(User.id == user_id).values(session_version=User.session_version + 1)
        )
        with Session(self._engine) as session:
            session.execute(stmt)
            session.commit()

    def list_users(self) -> list[dict[str, Any]]:
        """All users visible under the current tenant scoping."""
        self._ensure_initialized()
        with Session(self._engine) as session:
            rows = session.execute(select(User).order_by(User.email)).scalars().all()
            return [_user_to_dict(r) for r in rows]

    def list_tenants(self) -> list[dict[str, Any]]:
        """Tenants visible under RLS: the current tenant only, none with no tenant set."""
        self._ensure_initialized()
        with Session(self._engine) as session:
            rows = session.execute(select(Tenant).order_by(Tenant.name)).scalars().all()
            return [_tenant_to_dict(r) for r in rows]
