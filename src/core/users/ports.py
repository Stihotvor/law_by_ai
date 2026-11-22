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

    def insert_user(
        self, *, email: str, password_hash: str, role: str, name: str, actor_id: str
    ) -> UserRecord:
        """Insert an active user in the current tenant and return it.

        The store re-checks *actor_id* as an active admin in the same transaction and
        appends a ``create_user`` audit row for it.

        Raises, in check order:
            PrincipalRequiredError: no tenant is set (before any SQL), or the actor
                is not an active admin of the tenant (nothing is inserted).
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
            PrincipalRequiredError: the actor is not an active admin of the tenant.
            LastAdminError: the target is an admin and the locked active-admin set
                holds the target and has one row or fewer.
        An already inactive target is not in the locked set, so it returns ``False``.
        """
        ...


class CreateRateLimiter(Protocol):
    """Counts user-create attempts per acting admin."""

    def hit(self, actor_id: str) -> bool:
        """Count one attempt of *actor_id*; return ``False`` when the count is above the limit.

        May raise ``RedisError`` (the limiter store is unreachable).
        """
        ...
