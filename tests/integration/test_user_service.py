"""``UserService`` on the real ``PostgreSQLStore`` and a live PostgreSQL (T6).

Marked ``integration``: the store runs as ``lawbyai_app``; the owner
``lawbyai_owner`` reads and deletes rows inside the two test tenants. Each
service call runs under ``tenant_context`` and ``principal_context``, as
``require_auth`` sets them after login. Login uses the real credential lookup
and ``session_version`` check of ``ui.components.auth``. Only the network edge
is faked: the browser cookie (``FakeCookie``) and the Redis login throttle.
Skipped if PostgreSQL is unreachable.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import jwt
import pytest
from factories.auth import COOKIE, KEY, FakeCookie
from streamlit.testing.v1 import AppTest

from core.security import (
    PrincipalRequiredError,
    RequestPrincipal,
    principal_context,
    tenant_context,
)
from core.users.errors import UserCreateRefusedError
from core.users.service import UserService
from plugins.relational_db.postgres import PostgreSQLStore
from ui.components import auth

pytestmark = pytest.mark.integration

TENANT_A = "user-service-a"
TENANT_B = "user-service-b"
SEED_PLAIN = "seed-password-1"
NEW_PLAIN = "correct-horse-12"
MAX_SECONDS = 1.0
OwnerSql = Callable[..., list[Any]]


class _OpenThrottle:
    """Stand-in for the Redis login throttle: never locked, records nothing."""

    def is_locked(self, email: str) -> bool:
        return False

    def record_failure(self, email: str) -> bool:
        return False

    def reset(self, email: str) -> None:
        return None


def _clean(owner_sql: OwnerSql) -> None:
    for tenant in (TENANT_A, TENANT_B):
        owner_sql(tenant, "DELETE FROM users WHERE tenant_id = :t", t=tenant)


@pytest.fixture
def store(
    postgres_url: str, owner_sql: OwnerSql, monkeypatch: pytest.MonkeyPatch
) -> Iterator[PostgreSQLStore]:
    """Real store behind the auth adapter; the owner empties both test tenants."""
    monkeypatch.setenv("AUTH_COOKIE_KEY", KEY)
    monkeypatch.delenv("AUTH_COOKIE_NAME", raising=False)
    monkeypatch.delenv("AUTH_COOKIE_EXPIRY_DAYS", raising=False)
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")
    FakeCookie.reset()
    _clean(owner_sql)
    s = PostgreSQLStore()
    s.initialize()
    with (
        patch.object(auth, "_store", lambda: s),
        patch.object(auth, "CookieModel", FakeCookie),
        patch.object(auth, "_cookie_sent", lambda name: name in FakeCookie.jar),
        patch.object(auth, "_throttle", lambda: _OpenThrottle()),
    ):
        yield s
    s.close()
    _clean(owner_sql)


@pytest.fixture
def service(store: PostgreSQLStore) -> UserService:
    return UserService(store)


def _email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


def _seed(store: PostgreSQLStore, tenant: str, role: str) -> tuple[str, str]:
    """Insert an active user with the seed path; return ``(id, email)``."""
    email = _email(role)
    with tenant_context(tenant):
        record = store.create_user(
            email=email, password=SEED_PLAIN, role=role, tenant_id=tenant, name="Seed"
        )
    return str(record["id"]), email


@contextmanager
def _as(email: str, role: str, tenant: str = TENANT_A) -> Iterator[None]:
    """Run the block as ``require_auth`` would after a login of *email*."""
    with tenant_context(tenant), principal_context(RequestPrincipal(email=email, role=role)):
        yield


def _rows(owner_sql: OwnerSql, tenant: str) -> list[tuple[Any, ...]]:
    sql = (
        "SELECT id, email, role, name, is_active, session_version, password_hash "
        "FROM users WHERE tenant_id = :t ORDER BY id"
    )
    return [tuple(r) for r in owner_sql(tenant, sql, t=tenant)]


def _count(owner_sql: OwnerSql, tenant: str, email: str) -> int:
    rows = owner_sql(tenant, "SELECT count(*) FROM users WHERE email = :e", e=email)
    return int(rows[0][0])


# --- login through the real auth adapter ------------------------------------


def _script() -> None:
    import streamlit as st

    from ui.components.auth import require_auth

    user = require_auth()
    st.markdown(f"hello {user['role']} {user['tenant_id']}")


def _text(at: AppTest) -> str:
    return " ".join(str(m.value) for m in at.markdown)


def _login(email: str, password: str) -> AppTest:
    at = AppTest.from_function(_script).run()
    at.text_input(key="login_email").input(email)
    at.text_input(key="login_password").input(password)
    at.button[0].click()
    return at.run()


def _reload() -> AppTest:
    return AppTest.from_function(_script).run()


def _cookie_version() -> int:
    """Return the ``session_version`` the browser cookie claims (``email|version``)."""
    token = jwt.decode(FakeCookie.jar[COOKIE], options={"verify_signature": False})
    return int(str(token["username"]).rsplit("|", 1)[1])


# --- scenarios ----------------------------------------------------------------


def test_created_user_logs_in(store: PostgreSQLStore, service: UserService) -> None:
    """Scenario: Created user logs in (QA-001)."""
    _, admin_email = _seed(store, TENANT_A, "admin")
    email = _email("carol")

    with _as(admin_email, "admin"):
        record = service.create_user(email, NEW_PLAIN, "user", "Carol Nowak")

    user = auth.authenticate(email, NEW_PLAIN)
    assert user is not None
    assert user["id"] == record["id"]
    assert user["tenant_id"] == TENANT_A
    assert record["tenant_id"] == TENANT_A
    assert auth.authenticate(email, "wrong-password-1") is None


def test_deactivated_user_is_refused(store: PostgreSQLStore, service: UserService) -> None:
    """Scenario: Deactivated user is refused (QA-002, QA-003)."""
    _, admin_email = _seed(store, TENANT_A, "admin")
    email = _email("bob")
    with _as(admin_email, "admin"):
        record = service.create_user(email, NEW_PLAIN, "user", "Bob")
    logged_in = _login(email, NEW_PLAIN)
    assert f"hello user {TENANT_A}" in _text(logged_in)
    claimed = _cookie_version()

    with _as(admin_email, "admin"):
        assert service.deactivate_user(record["id"]) is True

    assert auth.authenticate(email, NEW_PLAIN) is None
    row = store.get_login_user(email)
    assert row is not None
    assert row["is_active"] is False
    assert row["session_version"] != claimed
    reloaded = _reload()
    assert "hello" not in _text(reloaded)
    assert FakeCookie.deleted == 1


def test_role_outside_valid_roles_is_refused(
    store: PostgreSQLStore, service: UserService, owner_sql: OwnerSql
) -> None:
    """Scenario: Privilege escalation (QA-019)."""
    _, admin_email = _seed(store, TENANT_A, "admin")
    email = _email("escalate")

    with _as(admin_email, "admin"), pytest.raises(UserCreateRefusedError):
        service.create_user(email, NEW_PLAIN, "superadmin", "Escalate")

    for tenant in (TENANT_A, TENANT_B):
        assert _count(owner_sql, tenant, email) == 0
    assert store.get_login_user(email) is None


def _attempts(service: UserService, admin_id: str, own_email: str) -> list[Callable[[], Any]]:
    return [
        lambda: service.create_user(_email("zed"), NEW_PLAIN, "user", "Zed"),
        lambda: service.create_user(own_email, NEW_PLAIN, "admin", "Self Promote"),
        lambda: service.create_user(_email("adm"), NEW_PLAIN, "admin", "New Admin"),
        lambda: service.deactivate_user(admin_id),
    ]


def test_role_user_changes_nothing(
    store: PostgreSQLStore, service: UserService, owner_sql: OwnerSql
) -> None:
    """Scenario: Role user (QA-030, QA-031, QA-048)."""
    admin_id, _ = _seed(store, TENANT_A, "admin")
    _seed(store, TENANT_A, "admin")
    _, user_email = _seed(store, TENANT_A, "user")
    before = _rows(owner_sql, TENANT_A)
    successes = 0

    with _as(user_email, "user"):
        for attempt in _attempts(service, admin_id, user_email):
            try:
                attempt()
                successes += 1
            except PrincipalRequiredError:
                pass

    assert successes == 0
    assert _rows(owner_sql, TENANT_A) == before


def test_duplicate_email_same_error_in_any_tenant(
    store: PostgreSQLStore, service: UserService, owner_sql: OwnerSql
) -> None:
    """Scenario: Duplicate email gives one generic error (QA-007, QA-008)."""
    _, admin_email = _seed(store, TENANT_A, "admin")
    _, own_email = _seed(store, TENANT_A, "user")
    _, foreign_email = _seed(store, TENANT_B, "user")
    before_a, before_b = _rows(owner_sql, TENANT_A), _rows(owner_sql, TENANT_B)

    with _as(admin_email, "admin"):
        with pytest.raises(UserCreateRefusedError) as own:
            service.create_user(own_email, NEW_PLAIN, "user", "Dup")
        with pytest.raises(UserCreateRefusedError) as foreign:
            service.create_user(foreign_email, NEW_PLAIN, "user", "Dup")

    assert str(own.value) == str(foreign.value)
    assert _rows(owner_sql, TENANT_A) == before_a
    assert _rows(owner_sql, TENANT_B) == before_b


def _timed[T](call: Callable[[], T]) -> tuple[T, float]:
    start = time.perf_counter()
    result = call()
    return result, time.perf_counter() - start


def test_each_action_under_one_second(
    store: PostgreSQLStore, service: UserService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Speed (QA-046), with the default bcrypt cost."""
    _, admin_email = _seed(store, TENANT_A, "admin")
    monkeypatch.delenv("BCRYPT_ROUNDS", raising=False)

    with _as(admin_email, "admin"):
        record, create_s = _timed(
            lambda: service.create_user(_email("fast"), NEW_PLAIN, "user", "Fast")
        )
        listed, list_s = _timed(service.list_users)
        changed, deactivate_s = _timed(lambda: service.deactivate_user(record["id"]))

    assert record["id"] in {r["id"] for r in listed}
    assert changed is True
    assert create_s < MAX_SECONDS
    assert list_s < MAX_SECONDS
    assert deactivate_s < MAX_SECONDS
