"""PostgreSQL session advisory lock with a deadline.

``advisory_lock`` polls ``pg_try_advisory_lock`` until it gets the key or the
deadline passes. On the deadline it looks up the holder pid in ``pg_locks`` and
raises ``AdvisoryLockTimeout``; the body never runs. Clock and sleep are
injectable so the poll loop is testable without delays.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.engine import Connection

logger = logging.getLogger(__name__)

_TRY_LOCK = text("SELECT pg_try_advisory_lock(:key)")
_UNLOCK = text("SELECT pg_advisory_unlock(:key)")
# A bigint advisory key is stored split: high 32 bits in classid, low 32 bits in
# objid, with objsubid = 1 (objsubid = 2 marks the two-int4 form).
_HOLDER = text(
    "SELECT pid FROM pg_locks"
    " WHERE locktype = 'advisory' AND granted"
    " AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
    " AND classid = CAST(:classid AS oid) AND objid = CAST(:objid AS oid)"
    " AND objsubid = 1"
    " LIMIT 1"
)


class AdvisoryLockTimeout(RuntimeError):
    """The advisory lock was not acquired before the deadline."""

    def __init__(self, key: int, timeout_s: float, holder_pid: int | None) -> None:
        self.key = key
        self.timeout_s = timeout_s
        self.holder_pid = holder_pid
        holder = str(holder_pid) if holder_pid is not None else "unknown"
        super().__init__(
            f"Could not acquire advisory lock 0x{key:X} within {timeout_s:g} s; "
            f"held by backend pid {holder}"
        )


def _try_lock(connection: Connection, key: int) -> bool:
    """One non-blocking try; ends the transaction so no snapshot stays open."""
    acquired = bool(connection.execute(_TRY_LOCK, {"key": key}).scalar())
    connection.commit()
    return acquired


def _holder_pid(connection: Connection, key: int) -> int | None:
    """Backend pid that holds the key, or None if no session holds it now."""
    params = {"classid": (key >> 32) & 0xFFFFFFFF, "objid": key & 0xFFFFFFFF}
    pid = connection.execute(_HOLDER, params).scalar()
    connection.commit()
    return int(pid) if pid is not None else None


def _acquire(
    connection: Connection,
    key: int,
    timeout_s: float,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    poll_s: float,
) -> None:
    """Poll until the key is held; raise AdvisoryLockTimeout at the deadline."""
    deadline = clock() + timeout_s
    waited = False
    while not _try_lock(connection, key):
        if clock() >= deadline:
            raise AdvisoryLockTimeout(key, timeout_s, _holder_pid(connection, key))
        if not waited:
            logger.info("Waiting for advisory lock 0x%X (deadline %g s)", key, timeout_s)
            waited = True
        sleep(poll_s)


def _release(connection: Connection, key: int) -> None:
    """Unlock the key; log a failure and do not raise it."""
    try:
        if connection.in_transaction():
            connection.rollback()
        connection.execute(_UNLOCK, {"key": key})
        connection.commit()
    except Exception:
        logger.exception("Could not release advisory lock 0x%X", key)


@contextmanager
def advisory_lock(
    connection: Connection,
    key: int,
    timeout_s: float,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    poll_s: float = 1.0,
) -> Iterator[None]:
    """Hold the session advisory lock ``key`` for the body.

    Raises ``AdvisoryLockTimeout`` if the key is not free within ``timeout_s``.
    Database errors from a poll or the holder query propagate unchanged. A failed
    release is logged; closing the connection ends the session and frees the lock.
    """
    _acquire(connection, key, timeout_s, clock, sleep, poll_s)
    try:
        yield
    finally:
        _release(connection, key)
