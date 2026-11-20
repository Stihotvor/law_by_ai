"""User/tenant methods of the PostgreSQL store (issue #52, ADR-0013).

:class:`UserStoreMixin` holds the ``users`` and ``tenants`` queries.
:class:`~plugins.relational_db.postgres.PostgreSQLStore` inherits it and provides
``_engine`` and ``_ensure_initialized``. Row-level security scopes these queries to
the current tenant (see :func:`plugins.relational_db.postgres.apply_tenant_rls`).
Login, which runs before a tenant is known, calls the ``auth_lookup_user`` function.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Engine, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.security import PrincipalRequiredError, get_current_tenant, hash_password
from core.security.login_throttle import normalise_email
from core.users.errors import (
    LastAdminError,
    SelfDeactivationError,
    UserCreateRefusedError,
    UserNotFoundError,
)
from core.users.ports import UserRecord
from plugins.relational_db.mappers import tenant_to_dict as _tenant_to_dict
from plugins.relational_db.mappers import user_to_dict as _user_to_dict
from plugins.relational_db.mappers import user_to_record as _user_to_record
from plugins.relational_db.tenant_models import AdminActionAudit, Tenant, User

__all__ = ["UserStoreMixin"]

# Login lookup (SECURITY DEFINER): the login columns of one user in any tenant.
_AUTH_LOOKUP_SQL = text("SELECT * FROM public.auth_lookup_user(:email)")
_LOGIN_KEYS = (
    "id",
    "tenant_id",
    "email",
    "role",
    "name",
    "is_active",
    "password_hash",
    "session_version",
)
# Only this (SQLSTATE, constraint) pair maps to UserCreateRefusedError.
_DUPLICATE_EMAIL = ("23505", "uq_users_email")


def _is_duplicate_email(exc: IntegrityError) -> bool:
    """True only for a unique violation (23505) on ``uq_users_email``."""
    diag = getattr(exc.orig, "diag", None)
    found = (getattr(exc.orig, "sqlstate", None), getattr(diag, "constraint_name", None))
    return found == _DUPLICATE_EMAIL


def _require_tenant() -> str:
    """Current tenant; ``PrincipalRequiredError`` when none is set (before any SQL)."""
    tenant = get_current_tenant()
    if not tenant:
        raise PrincipalRequiredError("A tenant is required.")
    return tenant


def _read_target_role(session: Session, user_id: str, tenant: str) -> str:
    """Target role by a non-locking read under RLS; missing or foreign -> ``UserNotFoundError``."""
    stmt = select(User.role).where(User.id == user_id, User.tenant_id == tenant)
    role = session.execute(stmt).scalar_one_or_none()
    if role is None:
        raise UserNotFoundError("The user was not found.")
    return role


def _lock_admins_or_refuse(session: Session, user_id: str, tenant: str) -> None:
    """Lock the tenant's active admins in id order; refuse removing the last one.

    No ``LIMIT`` and no ``SKIP LOCKED``: two racing sessions queue on the same set.
    """
    stmt = (
        select(User.id)
        .where(User.tenant_id == tenant, User.role == "admin", User.is_active)
        .order_by(User.id)
        .with_for_update()
    )
    locked = list(session.execute(stmt).scalars().all())
    if len(locked) <= 1 and user_id in locked:
        raise LastAdminError("The last active admin cannot be deactivated.")


def _lock_target(session: Session, user_id: str, tenant: str) -> None:
    """Lock only the target row (role ``user``)."""
    stmt = select(User.id).where(User.id == user_id, User.tenant_id == tenant).with_for_update()
    session.execute(stmt)


def _set_inactive(session: Session, user_id: str, tenant: str) -> bool:
    """Flip ``is_active`` off; True when one row changed (the trigger bumps session_version)."""
    stmt = (
        update(User)
        .where(User.id == user_id, User.tenant_id == tenant, User.is_active)
        .values(is_active=False)
        .returning(User.id)
        .execution_options(synchronize_session=False)
    )
    return session.execute(stmt).scalar_one_or_none() is not None


def _record_action(
    session: Session, *, tenant: str, actor_id: str, action: str, target_id: str
) -> None:
    """Append one ``admin_action_audit`` row in the caller's transaction (append-only table)."""
    session.execute(
        insert(AdminActionAudit).values(
            tenant_id=tenant, actor_id=actor_id, action=action, target_id=target_id
        )
    )


class UserStoreMixin:
    """User and tenant queries; the host class supplies the engine and lazy init."""

    _engine: Engine | None

    if TYPE_CHECKING:

        def _ensure_initialized(self) -> None: ...

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
                email=normalise_email(email),
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
        stmt = select(User).where(User.email == normalise_email(email))
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

    def insert_user(
        self, *, email: str, password_hash: str, role: str, name: str, actor_id: str
    ) -> UserRecord:
        """Insert an active user in the current tenant; the email is stored as given.

        Appends a ``create_user`` audit row for *actor_id* in the same transaction.

        Raises ``PrincipalRequiredError`` with no tenant (before any SQL), and
        ``UserCreateRefusedError`` only for 23505 on ``uq_users_email``. Other errors
        are re-raised unmapped. The transaction rolls back on every error.
        """
        tenant = _require_tenant()
        self._ensure_initialized()
        user = User(id=str(uuid.uuid4()), tenant_id=tenant, email=email, role=role, name=name)
        user.password_hash = password_hash
        user.is_active = True
        try:
            with Session(self._engine) as session, session.begin():
                session.add(user)
                session.flush()
                _record_action(
                    session,
                    tenant=tenant,
                    actor_id=actor_id,
                    action="create_user",
                    target_id=user.id,
                )
                record = _user_to_record(user)
        except IntegrityError as exc:
            if _is_duplicate_email(exc):
                raise UserCreateRefusedError("The user cannot be created.") from exc
            raise
        return record

    def list_users(self) -> list[UserRecord]:
        """Users of the current tenant ordered by email; ``[]`` with no tenant set."""
        # Reads return empty (no raise): with no tenant, RLS would show no rows anyway.
        tenant = get_current_tenant()
        if not tenant:
            return []
        self._ensure_initialized()
        stmt = select(User).where(User.tenant_id == tenant).order_by(User.email)
        with Session(self._engine) as session:
            return [_user_to_record(r) for r in session.execute(stmt).scalars().all()]

    def find_active_admin(self, email: str) -> UserRecord | None:
        """Active admin of the current tenant with exactly *email*, else ``None``.

        Returns ``None`` with no tenant set and runs no SQL.
        """
        # Reads return empty (no raise): with no tenant, RLS would show no rows anyway.
        tenant = get_current_tenant()
        if not tenant:
            return None
        self._ensure_initialized()
        stmt = select(User).where(
            User.tenant_id == tenant, User.role == "admin", User.is_active, User.email == email
        )
        with Session(self._engine) as session:
            row = session.execute(stmt).scalar_one_or_none()
            return _user_to_record(row) if row is not None else None

    def deactivate_user(self, user_id: str, *, actor_id: str) -> bool:
        """Deactivate *user_id* in the current tenant in one transaction.

        Check order: ``PrincipalRequiredError`` with no tenant (before any SQL),
        ``UserNotFoundError`` for a missing or foreign id, ``SelfDeactivationError``
        when ``user_id == actor_id``, ``LastAdminError`` when the locked active-admin
        set has one row or fewer and holds the target. Returns ``True`` when one row
        changed and ``False`` for an already inactive target. Rolls back on every error.
        A changed row appends a ``deactivate_user`` audit row in the same transaction.
        """
        tenant = _require_tenant()
        self._ensure_initialized()
        with Session(self._engine) as session, session.begin():
            role = _read_target_role(session, user_id, tenant)
            if user_id == actor_id:
                raise SelfDeactivationError("You cannot deactivate your own account.")
            if role == "admin":
                _lock_admins_or_refuse(session, user_id, tenant)
            else:
                _lock_target(session, user_id, tenant)
            changed = _set_inactive(session, user_id, tenant)
            if changed:
                _record_action(
                    session,
                    tenant=tenant,
                    actor_id=actor_id,
                    action="deactivate_user",
                    target_id=user_id,
                )
            return changed

    def list_tenants(self) -> list[dict[str, Any]]:
        """Tenants visible under RLS: the current tenant only, none with no tenant set."""
        self._ensure_initialized()
        with Session(self._engine) as session:
            rows = session.execute(select(Tenant).order_by(Tenant.name)).scalars().all()
            return [_tenant_to_dict(r) for r in rows]
