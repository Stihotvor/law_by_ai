"""Email lookups of the PostgreSQL store, with a fake session.

Unit tests: the store builds the query and maps the row without a database.
The real query runs in the integration tests.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from core.security import get_current_tenant, set_current_tenant
from plugins.relational_db import postgres
from plugins.relational_db.postgres import PostgreSQLStore, User

BCRYPT_HASH = "$2b$12$hash"

ROW = User(
    id="u-1",
    tenant_id="t-1",
    email="admin@example.com",
    name="Admin",
    role="admin",
    password_hash=BCRYPT_HASH,
    is_active=True,
    session_version=2,
)


class FakeSession:
    """Records the statement and the tenant seen inside the session."""

    seen: ClassVar[dict[str, Any]] = {}

    def __init__(self, _engine: object, row: User | None) -> None:
        self._row = row

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, stmt: Any) -> FakeSession:
        FakeSession.seen["email"] = stmt.compile().params["email_1"]
        FakeSession.seen["tenant"] = get_current_tenant()
        return self

    def scalar_one_or_none(self) -> User | None:
        return self._row


@pytest.fixture
def store_with(monkeypatch: pytest.MonkeyPatch):
    def make(row: User | None) -> PostgreSQLStore:
        store = PostgreSQLStore()
        monkeypatch.setattr(store, "_ensure_initialized", lambda: None)
        monkeypatch.setattr(postgres, "Session", lambda engine: FakeSession(engine, row))
        FakeSession.seen = {}
        return store

    return make


def test_get_login_user_normalises_email_and_ignores_tenant(store_with) -> None:
    store = store_with(ROW)
    set_current_tenant("t-other")
    try:
        result = store.get_login_user("  Admin@Example.COM ")
    finally:
        set_current_tenant(None)

    assert FakeSession.seen == {"email": "admin@example.com", "tenant": None}
    assert result is not None
    assert result["session_version"] == 2
    assert result["password_hash"] == BCRYPT_HASH


def test_get_login_user_returns_none_for_unknown_email(store_with) -> None:
    assert store_with(None).get_login_user("nobody@example.com") is None


def test_get_user_by_email_normalises_email(store_with) -> None:
    store = store_with(ROW)
    result = store.get_user_by_email(" ADMIN@example.com")

    assert FakeSession.seen["email"] == "admin@example.com"
    assert result is not None
    assert "password_hash" not in result


def test_get_user_by_email_returns_none_for_unknown_email(store_with) -> None:
    assert store_with(None).get_user_by_email("nobody@example.com") is None
