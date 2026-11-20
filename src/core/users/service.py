"""User service: principal binding, input checks, hashing and audit.

Uses only the ``UserRepository`` port. The tenant comes from the context and is
never an argument. Logs never hold a password or a password hash.
"""

from __future__ import annotations

import logging

from core.security import (
    PrincipalRequiredError,
    get_current_tenant,
    hash_password,
    require_admin_principal,
    valid_role,
)
from core.security.login_throttle import normalise_email
from core.security.passwords import MAX_PASSWORD_BYTES, MIN_PASSWORD_CHARS

from .errors import UserCreateRefusedError
from .ports import UserRecord, UserRepository

_log = logging.getLogger(__name__)

MAX_EMAIL_CHARS = 256
MAX_NAME_CHARS = 256


def _check_email(email: str) -> None:
    if not email or email.count("@") != 1 or len(email) > MAX_EMAIL_CHARS:
        raise UserCreateRefusedError("email must hold one @ and at most 256 characters")


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_CHARS or len(password.encode()) > MAX_PASSWORD_BYTES:
        raise UserCreateRefusedError("password needs 12 or more characters and 72 or fewer bytes")


def _check_input(email: str, password: str, role: str, name: str) -> None:
    _check_email(email)
    if len(name) > MAX_NAME_CHARS:
        raise UserCreateRefusedError("name must hold at most 256 characters")
    if not valid_role(role):
        raise UserCreateRefusedError("role is not valid")
    _check_password(password)


class UserService:
    """Admin-only user management in the current tenant."""

    def __init__(self, repo: UserRepository) -> None:
        self._repo = repo

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
        """Validate, hash and insert a new active user.

        Raises:
            PrincipalRequiredError: no tenant, or the caller is not an active admin.
            UserCreateRefusedError: invalid input or a taken email.
        """
        actor = self._actor()
        email = normalise_email(email)
        _check_input(email, password, role, name)
        record = self._repo.insert_user(
            email=email, password_hash=hash_password(password), role=role, name=name
        )
        _audit(actor["id"], record["id"], "create_user", changed=True)
        return record

    def deactivate_user(self, user_id: str) -> bool:
        """Deactivate *user_id*; return ``True`` if the row changed.

        Port errors (not found, self, last admin) propagate unchanged.
        """
        actor = self._actor()
        changed = self._repo.deactivate_user(user_id, actor_id=actor["id"])
        _audit(actor["id"], user_id, "deactivate_user", changed=changed)
        return changed

    def list_users(self) -> list[UserRecord]:
        """Return the users of the current tenant (no password hashes)."""
        self._actor()
        return self._repo.list_users()


def _audit(actor_id: str, target_id: str, action: str, *, changed: bool) -> None:
    _log.info(
        "user audit action=%s",
        action,
        extra={"actor_id": actor_id, "target_id": target_id, "action": action, "changed": changed},
    )
