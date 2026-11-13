"""Old-volume upgrade (rls-201 T5): the docs SQL block, then ``alembic upgrade head``.

Marked ``integration``. A scratch database (``migold_<hex>``) owned by the
test-only bootstrap superuser plays the old volume: the superuser migrates it to
the revision before rls-201, so it owns every object. Then the docs block runs
as the superuser and the owner upgrades to head. (Before the block the owner
cannot even read ``alembic_version``, so the stop is not asserted here.)

Roles are cluster-wide and the init script already made them, so the block's
``CREATE ROLE`` statements (and the psql meta-commands) are skipped here; the
test checks the role attributes instead. Skipped only if the PostgreSQL host is
unreachable; auth and other database errors fail the test.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from factories.db_probe import is_unreachable
from factories.scratch_db import superuser_url
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.exc import OperationalError

from config.settings import get_settings

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "docs" / "migrations.md"
HEADING = "## Upgrade an old volume"
OLD_REVISION = "77985ac8fa22"
SKIPPED_PREFIXES = ("CREATE ROLE", "BEGIN", "COMMIT", "SET LOG_")
ROLE_SQL = """
    SELECT rolname, rolcanlogin, rolsuper, rolbypassrls, rolinherit, rolcreatedb, rolcreaterole
    FROM pg_roles WHERE rolname LIKE 'lawbyai\\_%' ORDER BY rolname
"""
# (login, superuser, bypassrls, inherit, createdb, createrole) as the init script sets them.
EXPECTED_ROLES = {
    "lawbyai_app": (True, False, False, False, False, False),
    "lawbyai_auth": (False, False, True, False, False, False),
    "lawbyai_owner": (True, False, False, True, False, False),
}
OWNERS_SQL = """
    SELECT DISTINCT pg_get_userbyid(c.relowner)
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'S')
"""


def _docs_statements() -> list[str]:
    """Return the SQL statements of the docs block that a scratch database can run."""
    section = DOC.read_text().split(HEADING, 1)[1]
    match = re.search(r"```sql\n(.*?)```", section, re.DOTALL)
    assert match, "no sql block in the old-volume section"
    lines = [
        line for line in match.group(1).splitlines() if not line.lstrip().startswith(("--", "\\"))
    ]
    statements = [" ".join(part.split()) for part in "\n".join(lines).split(";")]
    return [s for s in statements if s and not s.upper().startswith(SKIPPED_PREFIXES)]


def _with_database(url: str, name: str) -> str:
    return make_url(url).set(database=name).render_as_string(hide_password=False)


def _alembic_config(url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def _autocommit(url: str, sql: str) -> None:
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(sql))
    finally:
        engine.dispose()


@pytest.fixture
def old_volume(postgres_url: str) -> Iterator[str]:
    """Name of a scratch database at OLD_REVISION; the superuser owns every object."""
    name = f"migold_{uuid.uuid4().hex[:12]}"
    admin = superuser_url()
    try:
        _autocommit(admin, f'CREATE DATABASE "{name}"')
    except OperationalError as error:
        # Only an unreachable host skips; bad bootstrap credentials and SQL errors fail.
        if is_unreachable(error):
            pytest.skip("database host unreachable; cannot create the old-volume database")
        raise
    try:
        command.upgrade(_alembic_config(_with_database(admin, name)), OLD_REVISION)
        yield name
    finally:
        _autocommit(admin, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _run_docs_block(url: str) -> None:
    engine = create_engine(url, future=True)
    try:
        with engine.begin() as conn:
            for statement in _docs_statements():
                conn.execute(text(statement))
    finally:
        engine.dispose()


def _rows(url: str, sql: str) -> list[tuple[object, ...]]:
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as conn:
            return [tuple(row) for row in conn.execute(text(sql)).all()]
    finally:
        engine.dispose()


def test_docs_statements_cover_the_owner_changes() -> None:
    statements = _docs_statements()
    assert sum(s.startswith("ALTER TABLE") for s in statements) == 5
    assert any(s.startswith("ALTER SEQUENCE rejected_document_id_seq") for s in statements)
    assert any(s.startswith("ALTER FUNCTION users_bump_session_version()") for s in statements)


def test_old_volume_upgrades_after_the_docs_block(old_volume: str) -> None:
    """Scenario: Old volume upgrades after the SQL block."""
    settings = get_settings()
    owner = _with_database(settings.postgres_owner_url, old_volume)
    _run_docs_block(_with_database(superuser_url(), old_volume))
    command.upgrade(_alembic_config(owner), "head")

    roles = {str(row[0]): row[1:] for row in _rows(owner, ROLE_SQL)}
    assert {name: roles.get(name) for name in EXPECTED_ROLES} == EXPECTED_ROLES
    assert _rows(owner, OWNERS_SQL) == [("lawbyai_owner",)]
    app = _with_database(settings.postgres_url, old_volume)
    assert _rows(app, "SELECT count(*) FROM users") == [(0,)]
    assert _rows(app, "SELECT count(*) FROM public.auth_lookup_user('nobody@x.pl')") == [(0,)]
