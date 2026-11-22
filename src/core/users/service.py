"""User service: principal binding, input checks, hashing and audit.

Uses only the ``UserRepository`` and ``CreateRateLimiter`` ports. The tenant
comes from the context and is never an argument. Logs never hold a password or a password hash.
"""

from __future__ import annotations

import logging
from types import TracebackType

from core.security import (
    PrincipalRequiredError,
    get_current_tenant,
    hash_password,
    require_admin_principal,
    valid_role,
)
from core.security.emails import normalise_email
from core.security.passwords import MAX_PASSWORD_BYTES, MIN_PASSWORD_CHARS

from .errors import (
    LastAdminError,
    SelfDeactivationError,
    UserCreateRefusedError,
    UserCreateThrottledError,
    UserNotFoundError,
)
from .ports import CreateRateLimiter, UserRecord, UserRepository

_log = logging.getLogger(__name__)

MAX_EMAIL_CHARS = 256
MAX_NAME_CHARS = 256
PASSWORD_RULE = (
    f"password needs {MIN_PASSWORD_CHARS} or more characters "
    f"and {MAX_PASSWORD_BYTES} or fewer bytes"
)
# Known refusals: logged at WARNING with the actor id, the action and the class name.
_REFUSALS: tuple[type[Exception], ...] = (
    PrincipalRequiredError,
    LastAdminError,
    SelfDeactivationError,
    UserCreateRefusedError,
    UserCreateThrottledError,
    UserNotFoundError,
)


def _check_email(email: str) -> None:
    if not email or email.count("@") != 1 or len(email) > MAX_EMAIL_CHARS:
        raise UserCreateRefusedError("email must hold one @ and at most 256 characters")


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_CHARS or len(password.encode()) > MAX_PASSWORD_BYTES:
        raise UserCreateRefusedError(PASSWORD_RULE)


def _check_input(email: str, password: str, role: str, name: str) -> None:
    _check_email(email)
    if len(name) > MAX_NAME_CHARS:
        raise UserCreateRefusedError("name must hold at most 256 characters")
    if not valid_role(role):
        raise UserCreateRefusedError("role is not valid")
    _check_password(password)


class _RefusalLog:
    """Log a known refusal raised inside the block; never the message or the input."""

    def __init__(self, action: str) -> None:
        self.action = action
        self.actor_id: str | None = None

    def __enter__(self) -> _RefusalLog:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if kind is None or not issubclass(kind, _REFUSALS):
            return
        _log.warning(
            "user action refused action=%s error=%s actor_id=%s",
            self.action,
            kind.__name__,
            self.actor_id,
            extra={"actor_id": self.actor_id, "action": self.action, "error": kind.__name__},
        )


class UserService:
    """Admin-only user management in the current tenant."""

    def __init__(self, repo: UserRepository, limiter: CreateRateLimiter) -> None:
        self._repo = repo
        self._limiter = limiter

    def _actor(self) -> UserRecord:
        """Return the active admin row of the current principal in the current tenant."""
        if not get_current_tenant():
            raise PrincipalRequiredError("no tenant is set")
        principal = require_admin_principal()
        actor = self._repo.find_active_admin(normalise_email(principal.email))
        if actor is None:
            raise PrincipalRequiredError("request principal is not an active admin")
        return actor

    def create_user(self, email: str, password: str, role: str, name: str) -> UserRecord:
        """Count the attempt of the acting admin, then validate, hash and insert a new user.

        Every attempt that passes the actor check counts, also one with invalid input.

        Raises:
            PrincipalRequiredError: no tenant, or the caller is not an active admin.
            UserCreateThrottledError: the actor is over the create limit (before input checks).
            UserCreateRefusedError: invalid input or a taken email.
            RedisError: the limiter is unreachable (fail closed, nothing is inserted).

        Known refusals are logged at WARNING before they propagate.
        """
        with _RefusalLog("create_user") as refusal:
            actor = self._actor()
            refusal.actor_id = actor["id"]
            if not self._limiter.hit(actor["id"]):
                raise UserCreateThrottledError("too many user creations, try again later")
            email = normalise_email(email)
            _check_input(email, password, role, name)
            record = self._repo.insert_user(
                email=email,
                password_hash=hash_password(password),
                role=role,
                name=name,
                actor_id=actor["id"],
            )
        _audit(actor["id"], record["id"], "create_user", changed=True)
        return record

    def deactivate_user(self, user_id: str) -> bool:
        """Deactivate *user_id*; return ``True`` if the row changed.

        Port errors (not found, self, last admin) propagate unchanged.
        Known refusals are logged at WARNING before they propagate.
        """
        with _RefusalLog("deactivate_user") as refusal:
            actor = self._actor()
            refusal.actor_id = actor["id"]
            changed = self._repo.deactivate_user(user_id, actor_id=actor["id"])
        _audit(actor["id"], user_id, "deactivate_user", changed=changed)
        return changed

    def list_users(self) -> list[UserRecord]:
        """Return the users of the current tenant (no password hashes)."""
        with _RefusalLog("list_users"):
            self._actor()
        return self._repo.list_users()


def _audit(actor_id: str, target_id: str, action: str, *, changed: bool) -> None:
    _log.info(
        "user audit action=%s",
        action,
        extra={"actor_id": actor_id, "target_id": target_id, "action": action, "changed": changed},
    )
