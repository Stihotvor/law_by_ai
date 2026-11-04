#!/usr/bin/env python
"""Initialize the database with a test tenant and admin user.

Run from the repository root: PYTHONPATH=src python scripts/seed_db.py
"""

import os

from core.security import ADMIN
from plugins.relational_db.postgres import PostgreSQLStore

BCRYPT_MAX_BYTES = 72  # bcrypt rejects longer inputs (core.security.passwords uses bcrypt)


def admin_password() -> str:
    """Return the seed admin password from SEED_ADMIN_PASSWORD (required)."""
    password = os.environ.get("SEED_ADMIN_PASSWORD")
    if not password:
        raise SystemExit("SEED_ADMIN_PASSWORD must be set to seed the admin user.")
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise SystemExit(
            f"SEED_ADMIN_PASSWORD must be at most {BCRYPT_MAX_BYTES} bytes in UTF-8 (bcrypt limit)."
        )
    return password


def main() -> None:
    password = admin_password()
    plugin = PostgreSQLStore()
    plugin.initialize()

    # Create platform tenant
    try:
        plugin.create_tenant("Platform", "platform")
        print("✓ Tenant created: platform")
    except Exception as e:
        print(f"✗ Tenant creation failed (may already exist): {e}")

    # Create admin user
    try:
        user = plugin.create_user(
            email="admin@example.com",
            password=password,
            role=ADMIN,
            tenant_id="platform",
            name="Admin",
        )
        print(f"✓ Admin user created: {user['email']} (role: {user['role']})")
    except Exception as e:
        print(f"✗ Admin user creation failed: {e}")

    plugin.close()


if __name__ == "__main__":
    main()
