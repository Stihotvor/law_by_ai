"""Unit tests for the advisory_lock context manager.

A fake connection answers the try, holder and unlock queries; a fake clock and
sleep drive the poll loop without real delays.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any, cast

import pytest
from sqlalchemy.engine import Connection
from sqlalchemy.exc import OperationalError

from storage.advisory_lock import AdvisoryLockTimeout, advisory_lock

KEY = 0x6C61775F6D6967
LOGGER = "storage.advisory_lock"


def _db_error() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("server closed the connection"))


class _Result:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar(self) -> object:
        return self._value


class _FakeConnection:
    """Answers each query by the SQL function it calls."""

    def __init__(
        self,
        tries: list[bool | Exception],
        holder: int | Exception | None = None,
        unlock_error: Exception | None = None,
        in_transaction: bool = False,
    ) -> None:
        self._tries: Iterator[bool | Exception] = iter(tries)
        self._holder = holder
        self._unlock_error = unlock_error
        self._in_transaction = in_transaction
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self.events: list[str] = []
        self.commits = 0

    def execute(self, statement: object, parameters: dict[str, Any] | None = None) -> _Result:
        sql = str(statement)
        self.statements.append((sql, dict(parameters or {})))
        self.events.append(sql)
        if "pg_try_advisory_lock" in sql:
            return _Result(self._answer(next(self._tries)))
        if "pg_locks" in sql:
            return _Result(self._answer(self._holder))
        if "pg_advisory_unlock" in sql and self._unlock_error is not None:
            raise self._unlock_error
        return _Result(True)

    @staticmethod
    def _answer(value: object) -> object:
        if isinstance(value, Exception):
            raise value
        return value

    def commit(self) -> None:
        self.commits += 1
        self.events.append("commit")

    def rollback(self) -> None:
        self.events.append("rollback")

    def in_transaction(self) -> bool:
        return self._in_transaction

    def count(self, function: str) -> int:
        """Number of executed statements that call ``function``."""
        return sum(function in sql for sql, _ in self.statements)


class _FakeClock:
    """Monotonic clock that advances only when the fake sleep runs."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _enter(conn: _FakeConnection, clock: _FakeClock, timeout_s: float = 300.0) -> list[str]:
    """Enter the lock context and return the body's record of having run."""
    ran: list[str] = []
    with advisory_lock(
        cast(Connection, conn), KEY, timeout_s, clock=clock.clock, sleep=clock.sleep
    ):
        ran.append("body")
    return ran


def _wait_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == LOGGER and "Waiting" in r.message]


def test_free_lock_runs_body_without_wait_or_sleep(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    clock = _FakeClock()

    conn = _FakeConnection(tries=[True])

    ran = _enter(conn, clock)

    assert ran == ["body"]
    assert _wait_lines(caplog) == []
    assert clock.sleeps == []
    assert conn.count("pg_advisory_unlock") == 1


def test_lock_freed_before_deadline_is_taken_at_next_poll(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    clock = _FakeClock()

    conn = _FakeConnection(tries=[False, True])

    ran = _enter(conn, clock)

    assert clock.sleeps == [1.0]
    assert len(_wait_lines(caplog)) == 1
    assert ran == ["body"]
    assert conn.count("pg_try_advisory_lock") == 2
    assert conn.count("pg_advisory_unlock") == 1
    # One commit per try, plus one after the unlock.
    assert conn.commits == 2 + 1


def test_deadline_with_known_holder_raises_timeout_naming_key_deadline_and_pid() -> None:
    clock = _FakeClock()
    conn = _FakeConnection(tries=[False] * 400, holder=4242)
    ran: list[str] = []

    with (
        pytest.raises(AdvisoryLockTimeout) as excinfo,
        advisory_lock(cast(Connection, conn), KEY, 300.0, clock=clock.clock, sleep=clock.sleep),
    ):
        ran.append("body")

    message = str(excinfo.value)
    assert "0x6C61775F6D6967" in message
    assert "300" in message
    assert "4242" in message
    assert excinfo.value.holder_pid == 4242
    assert excinfo.value.key == KEY
    assert excinfo.value.timeout_s == 300.0
    assert ran == []
    holder_params = next(p for sql, p in conn.statements if "pg_locks" in sql)
    assert holder_params == {"classid": 0x6C6177, "objid": 0x5F6D6967}
    # Tries at t = 0, 1, ..., 300 s; the one at the deadline is the last.
    assert conn.count("pg_try_advisory_lock") == 301
    # One commit per try, plus one after the holder query.
    assert conn.commits == 301 + 1
    assert conn.count("pg_advisory_unlock") == 0


def test_deadline_with_unknown_holder_says_unknown() -> None:
    clock = _FakeClock()
    conn = _FakeConnection(tries=[False] * 400, holder=None)

    with pytest.raises(AdvisoryLockTimeout) as excinfo:
        _enter(conn, clock, timeout_s=2.0)

    assert "unknown" in str(excinfo.value)
    assert excinfo.value.holder_pid is None
    assert conn.commits == conn.count("pg_try_advisory_lock") + 1
    assert conn.count("pg_advisory_unlock") == 0


@pytest.mark.parametrize(
    ("tries", "holder"),
    [
        pytest.param([_db_error()], None, id="poll"),
        pytest.param([False] * 10, _db_error(), id="pg_locks"),
    ],
)
def test_database_error_propagates_unchanged(
    tries: list[bool | Exception], holder: int | Exception | None
) -> None:
    expected = tries[0] if isinstance(tries[0], Exception) else holder
    conn = _FakeConnection(tries=tries, holder=holder)

    with pytest.raises(OperationalError) as excinfo:
        _enter(conn, _FakeClock(), timeout_s=2.0)

    assert excinfo.value is expected
    assert not isinstance(excinfo.value, AdvisoryLockTimeout)
    assert conn.count("pg_advisory_unlock") == 0


def test_release_failure_is_logged_and_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    conn = _FakeConnection(tries=[True], unlock_error=_db_error())

    ran = _enter(conn, _FakeClock())

    assert ran == ["body"]
    assert conn.count("pg_advisory_unlock") == 1
    failures = [r for r in caplog.records if r.name == LOGGER and r.levelno >= logging.ERROR]
    assert len(failures) == 1


def test_body_error_rolls_back_before_unlock_and_propagates() -> None:
    conn = _FakeConnection(tries=[True], in_transaction=True)
    clock = _FakeClock()
    error = ValueError("migration failed")

    with (
        pytest.raises(ValueError, match="migration failed") as excinfo,
        advisory_lock(cast(Connection, conn), KEY, 300.0, clock=clock.clock, sleep=clock.sleep),
    ):
        raise error

    assert excinfo.value is error
    unlock_at = next(i for i, e in enumerate(conn.events) if "pg_advisory_unlock" in e)
    assert "rollback" in conn.events[:unlock_at]
    assert conn.count("pg_advisory_unlock") == 1


@pytest.mark.parametrize(
    ("key", "classid", "objid"),
    [
        pytest.param(KEY, 0x6C6177, 0x5F6D6967, id="migration-key"),
        pytest.param(-1, 0xFFFFFFFF, 0xFFFFFFFF, id="negative"),
        pytest.param(0xFFFFFFFF, 0, 0xFFFFFFFF, id="low-word-only"),
    ],
)
def test_holder_query_splits_key_into_classid_and_objid(key: int, classid: int, objid: int) -> None:
    clock = _FakeClock()
    conn = _FakeConnection(tries=[False] * 10, holder=7)

    with (
        pytest.raises(AdvisoryLockTimeout),
        advisory_lock(cast(Connection, conn), key, 2.0, clock=clock.clock, sleep=clock.sleep),
    ):
        pass

    holder_params = next(p for sql, p in conn.statements if "pg_locks" in sql)
    assert holder_params == {"classid": classid, "objid": objid}


@pytest.mark.parametrize(
    ("tries", "acquired"),
    [
        pytest.param([False, False], False, id="held-past-deadline"),
        pytest.param([False, True], True, id="freed-at-deadline-try"),
    ],
)
def test_last_sleep_is_capped_at_the_deadline(
    tries: list[bool | Exception], acquired: bool
) -> None:
    clock = _FakeClock()
    conn = _FakeConnection(tries=tries, holder=4242)
    ran: list[str] = []

    def enter() -> None:
        with advisory_lock(
            cast(Connection, conn), KEY, 0.25, clock=clock.clock, sleep=clock.sleep, poll_s=1.0
        ):
            ran.append("body")

    if acquired:
        enter()
    else:
        with pytest.raises(AdvisoryLockTimeout):
            enter()

    assert clock.sleeps == [0.25]
    assert conn.count("pg_try_advisory_lock") == 2
    assert ran == (["body"] if acquired else [])
