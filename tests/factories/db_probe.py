"""Probe a PostgreSQL URL for the integration fixtures.

Only an unreachable host (connection refused, name resolution) means "skip".
Any other connect error, such as a wrong password or a missing role, is a
broken setup and must fail the test run.
"""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# Substrings of libpq / psycopg errors for a host that cannot be reached.
UNREACHABLE_MARKERS = (
    "Connection refused",
    "could not translate host name",
    "failed to resolve host",
    "Name or service not known",
    "Temporary failure in name resolution",
    "nodename nor servname provided",
)


def is_unreachable(error: OperationalError) -> bool:
    """Return True when the error says the host refused or could not be resolved."""
    message = str(error.orig) if error.orig is not None else str(error)
    return any(marker in message for marker in UNREACHABLE_MARKERS)


def can_connect(url: str) -> bool:
    """Return True when the database answers, False when its host is unreachable.

    Raises every other connect error, so auth and role problems are not skipped.
    """
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError as error:
        if is_unreachable(error):
            return False
        raise
    finally:
        engine.dispose()
