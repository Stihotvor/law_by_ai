"""Password hashing helpers (ADR-0013).

bcrypt wrappers used by the PostgreSQL user store and by the login form.
The work factor is controlled by the ``BCRYPT_ROUNDS`` environment variable
(default 12).
"""

from __future__ import annotations

import os
import secrets

import bcrypt


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*.

    Cost factor comes from ``BCRYPT_ROUNDS`` (default 12).
    """
    rounds = int(os.getenv("BCRYPT_ROUNDS", "12"))
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("utf-8")


def check_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the bcrypt *hashed* password."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# Checked when no user matches, so a login takes the same time either way.
# Built with the BCRYPT_ROUNDS value at import time.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))
