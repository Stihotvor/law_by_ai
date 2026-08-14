"""Password hashing helpers (ADR-0013).

bcrypt wrappers used by the PostgreSQL user store and by the
streamlit-authenticator credential builder. The work factor is controlled by
the ``BCRYPT_ROUNDS`` environment variable (default 12).
"""

from __future__ import annotations

import os

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
