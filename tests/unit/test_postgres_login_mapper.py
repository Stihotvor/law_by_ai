"""Login mapper of the PostgreSQL store: the row it returns for a login lookup.

Unit tests: the mapper works on an unsaved ``User``, so no database is needed.
"""

from __future__ import annotations

from plugins.relational_db.postgres import User, _login_user_to_dict

BCRYPT_HASH = "$2b$12$hash"


def test_login_mapper_returns_every_login_field() -> None:
    row = User(
        id="u-1",
        tenant_id="t-1",
        email="admin@example.com",
        name="Admin",
        role="admin",
        password_hash=BCRYPT_HASH,
        is_active=False,
        session_version=3,
    )

    assert _login_user_to_dict(row) == {
        "id": "u-1",
        "tenant_id": "t-1",
        "email": "admin@example.com",
        "name": "Admin",
        "role": "admin",
        "password_hash": BCRYPT_HASH,
        "is_active": False,
        "session_version": 3,
    }
