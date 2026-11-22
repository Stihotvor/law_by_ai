"""Hand-written fakes for the user service: a ``UserRepository`` and a ``CreateRateLimiter``."""

from __future__ import annotations

from typing import Any

from core.users import UserRecord

TENANT = "t1"
Calls = list[tuple[str, dict[str, Any]]]


def user_record(user_id: str, email: str, role: str = "user") -> UserRecord:
    return UserRecord(id=user_id, tenant_id=TENANT, email=email, role=role, name="", is_active=True)


class FakeRepo:
    """In-memory UserRepository that records every call."""

    def __init__(self, admin: UserRecord | None = None) -> None:
        self.admin: UserRecord | None = admin or user_record("A1", "a@x.pl", "admin")
        self.calls: Calls = []
        self.writes: Calls = []
        self.deactivate_result: bool | Exception = True

    def find_active_admin(self, email: str) -> UserRecord | None:
        self.calls.append(("find_active_admin", {"email": email}))
        if self.admin is None or self.admin["email"] != email:
            return None
        return self.admin

    def insert_user(
        self, *, email: str, password_hash: str, role: str, name: str, actor_id: str
    ) -> UserRecord:
        args = {
            "email": email,
            "password_hash": password_hash,
            "role": role,
            "name": name,
            "actor_id": actor_id,
        }
        self.calls.append(("insert_user", args))
        self.writes.append(("insert_user", args))
        return UserRecord(
            id="U9", tenant_id=TENANT, email=email, role=role, name=name, is_active=True
        )

    def list_users(self) -> list[UserRecord]:
        self.calls.append(("list_users", {}))
        return [self.admin] if self.admin else []

    def deactivate_user(self, user_id: str, *, actor_id: str) -> bool:
        args = {"user_id": user_id, "actor_id": actor_id}
        self.calls.append(("deactivate_user", args))
        if isinstance(self.deactivate_result, Exception):
            raise self.deactivate_result
        self.writes.append(("deactivate_user", args))
        return self.deactivate_result


class FakeLimiter:
    """CreateRateLimiter that records each hit, also in *log* when given.

    ``allow`` is the result of ``hit``; an exception there is raised instead.
    """

    def __init__(self, log: Calls | None = None) -> None:
        self.hits: list[str] = []
        self.allow: bool | Exception = True
        self._log = log

    def hit(self, actor_id: str) -> bool:
        self.hits.append(actor_id)
        if self._log is not None:
            self._log.append(("hit", {"actor_id": actor_id}))
        if isinstance(self.allow, Exception):
            raise self.allow
        return self.allow
