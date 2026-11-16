"""Migrations run once (migration-run-once T1): the advisory lock in ``migrations/env.py``.

Marked ``integration``. Each test gets a scratch database (``miglock_<hex>``)
made by the test-only bootstrap superuser and owned by ``lawbyai_owner``; it is
dropped ``WITH (FORCE)`` at the end. Upgrades run as real ``alembic upgrade
head`` subprocesses with the owner URL, so they race like separate containers.
Skipped only if the PostgreSQL host is unreachable.

``migrations/env.py`` runs migrations on import, so ``LOCK_KEY`` is copied here.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from factories.scratch_db import ScratchDb, scratch_database
from sqlalchemy import Connection, create_engine, text

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_KEY = 0x6C61775F6D6967
WAIT_SECONDS = 60
OFFLINE_WAIT_SECONDS = 30
BLOCK_WAIT_SECONDS = 10
POLL_INTERVAL = 0.2
BAD_REVISION = "0000deadbeef"
URL_ENV = "MIGLOCK_TEST_URL"
REVISION_ENV = "MIGLOCK_TEST_REVISION"
SQL_ENV = "MIGLOCK_TEST_SQL"
# Runs in the subprocess; reads the URL, revision and offline flag from the environment.
UPGRADE_CODE = f"""
import os
from alembic import command
from alembic.config import Config
cfg = Config({str(REPO_ROOT / "alembic.ini")!r})
cfg.set_main_option("script_location", {str(REPO_ROOT / "migrations")!r})
cfg.set_main_option("sqlalchemy.url", os.environ[{URL_ENV!r}].replace("%", "%%"))
command.upgrade(cfg, os.environ[{REVISION_ENV!r}], sql=os.environ[{SQL_ENV!r}] == "1")
"""
# A waiting (not granted) session advisory lock on LOCK_KEY in the named database.
WAITING_SQL = """
    SELECT count(*) FROM pg_locks
    WHERE locktype = 'advisory' AND NOT granted
      AND database = (SELECT oid FROM pg_database WHERE datname = :name)
      AND ((classid::bigint << 32) | objid::bigint) = :key
"""


@pytest.fixture
def scratch() -> Iterator[ScratchDb]:
    """An empty scratch database owned by ``lawbyai_owner``."""
    with scratch_database("miglock") as db:
        yield db


def _scripts() -> ScriptDirectory:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return ScriptDirectory.from_config(cfg)


def _head() -> str:
    head = _scripts().get_current_head()
    assert head is not None
    return head


def _base() -> str:
    """Return the first revision. Offline mode stops there: a later migration reads data."""
    return _scripts().get_bases()[0]


def _start_upgrade(url: str, revision: str = "head", *, sql: bool = False) -> subprocess.Popen[str]:
    """Start ``alembic upgrade <revision>`` (``--sql`` if *sql*) against *url* in a new process."""
    env = dict(os.environ)
    env[URL_ENV] = url
    env[REVISION_ENV] = revision
    env[SQL_ENV] = "1" if sql else "0"
    src = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = os.pathsep.join(p for p in (src, env.get("PYTHONPATH")) if p)
    return subprocess.Popen(  # noqa: S603 - fixed argv: this interpreter and a constant script
        [sys.executable, "-c", UPGRADE_CODE],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _finish(proc: subprocess.Popen[str], timeout: float = WAIT_SECONDS) -> tuple[int, str]:
    """Wait up to *timeout* seconds; return (exit code, output)."""
    output, _ = proc.communicate(timeout=timeout)
    return proc.returncode, output


def _kill(procs: list[subprocess.Popen[str]]) -> None:
    for proc in procs:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()


def _run_upgrade(url: str, revision: str = "head", *, sql: bool = False) -> tuple[int, str]:
    proc = _start_upgrade(url, revision, sql=sql)
    try:
        return _finish(proc, OFFLINE_WAIT_SECONDS if sql else WAIT_SECONDS)
    finally:
        _kill([proc])


def _wait_for_waiter(holder: Connection, name: str) -> bool:
    """Poll pg_locks until a session waits on LOCK_KEY in *name*, up to BLOCK_WAIT_SECONDS."""
    deadline = time.monotonic() + BLOCK_WAIT_SECONDS
    while time.monotonic() < deadline:
        count = holder.execute(text(WAITING_SQL), {"name": name, "key": LOCK_KEY}).scalar_one()
        if count:
            return True
        time.sleep(POLL_INTERVAL)
    return False


def _rows(url: str, sql: str, **params: Any) -> list[tuple[object, ...]]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return [tuple(row) for row in conn.execute(text(sql), params).all()]
    finally:
        engine.dispose()


def test_concurrent_upgrades_apply_once(scratch: ScratchDb) -> None:
    """Scenario: Concurrent upgrades apply once."""
    procs = [_start_upgrade(scratch.owner_url) for _ in range(2)]
    try:
        results = [_finish(proc) for proc in procs]
    finally:
        _kill(procs)

    for code, output in results:
        assert code == 0, output
    rows = _rows(scratch.owner_url, "SELECT version_num FROM alembic_version")
    assert rows == [(_head(),)]


def test_upgrade_blocks_while_lock_held(scratch: ScratchDb) -> None:
    """Scenario: Upgrade blocks while the key is held."""
    engine = create_engine(scratch.owner_url, isolation_level="AUTOCOMMIT")
    procs: list[subprocess.Popen[str]] = []
    try:
        with engine.connect() as holder:
            holder.execute(text("SELECT pg_advisory_lock(:key)"), {"key": LOCK_KEY})
            procs.append(_start_upgrade(scratch.owner_url))
            waiting = _wait_for_waiter(holder, scratch.name)
            still_running = procs[0].poll() is None
            holder.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
        assert waiting, "upgrade never waited on the advisory lock"
        assert still_running, "upgrade did not wait for the advisory lock"
        code, output = _finish(procs[0])
        assert code == 0, output
    finally:
        _kill(procs)
        engine.dispose()


def test_failed_upgrade_releases_lock(scratch: ScratchDb) -> None:
    """Scenario: A failed upgrade releases the lock and keeps its error."""
    code, output = _run_upgrade(scratch.owner_url, BAD_REVISION)
    assert code != 0, output
    assert BAD_REVISION in output, output

    engine = create_engine(scratch.owner_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            got = conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY})
            assert got.scalar_one() is True
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
    finally:
        engine.dispose()

    code, output = _run_upgrade(scratch.owner_url)
    assert code == 0, output


def test_offline_sql_ignores_held_lock(scratch: ScratchDb) -> None:
    """Scenario: Offline SQL generation does not take the lock."""
    engine = create_engine(scratch.owner_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as holder:
            holder.execute(text("SELECT pg_advisory_lock(:key)"), {"key": LOCK_KEY})
            try:
                code, output = _run_upgrade(scratch.owner_url, _base(), sql=True)
            finally:
                holder.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
    finally:
        engine.dispose()
    assert code == 0, output
    assert "CREATE TABLE" in output, output
