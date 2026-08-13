#!/usr/bin/env python
"""Initialize the database with a test tenant and admin user."""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from core.security import ADMIN
from plugins.relational_db.postgres import PostgreSQLStore


def main():
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
            password="admin",
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
