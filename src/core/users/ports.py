"""Port between the user service and the user store."""

from typing import Protocol, TypedDict


class UserRecord(TypedDict):
    """Public view of a user row. Never holds a password hash or session version."""

    id: str
    tenant_id: str
    email: str
    role: str
    name: str
    is_active: bool


class UserRepository(Protocol):
    """Tenant-scoped user store. Every method reads the tenant from the context."""

    def find_active_admin(self, email: str) -> UserRecord | None:
        """Return the active admin with this exact email, else ``None``.

        Returns ``None`` with no tenant set. Raises no domain error.
        """
        ...

    def insert_user(self, *, email: str, password_hash: str, role: str, name: str) -> UserRecord:
        """Insert an active user in the current tenant and return it.

        Raises:
            PrincipalRequiredError: no tenant is set (before any SQL).
            UserCreateRefusedError: the email is taken (``uq_users_email``).
        Other DB errors are re-raised unmapped.
        """
        ...

    def list_users(self) -> list[UserRecord]:
        """Return the users of the current tenant ordered by email.

        Returns ``[]`` with no tenant set. DB errors propagate unmapped.
        """
        ...

    def deactivate_user(self, user_id: str, *, actor_id: str) -> bool:
        """Deactivate a user; ``True`` if a row changed, ``False`` if already inactive.

        Raises, in check order:
            PrincipalRequiredError: no tenant is set (before any SQL).
            UserNotFoundError: the id is missing or in another tenant.
            SelfDeactivationError: ``user_id == actor_id``.
            LastAdminError: the locked admin set has one row or fewer.
        """
        ...
