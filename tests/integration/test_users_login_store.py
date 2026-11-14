"""Login lookup, email normalisation and session version on the ``users`` table.

Marked ``integration``: runs against a live PostgreSQL as ``lawbyai_app``. The
store tests use the configured database with unique emails; the owner
``lawbyai_owner`` cleans up inside the test tenant. The migration tests
downgrade the schema, so they run in a scratch database (``migusers_<hex>``)
that each test creates and drops: the test-only superuser creates and drops it,
the owner migrates it and writes the rows (tenant ``t``), the app role asserts.
Skipped if PostgreSQL is unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from factories.scratch_db import TENANT_SQL, ScratchDb, scratch_database, tenant_sql
from sqlalchemy import Connection, Engine, create_engine, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

from core.security import tenant_context
from plugins.relational_db.postgres import PostgreSQLStore

pytestmark = pytest.mark.integration

PREVIOUS_REVISION = "963e40b83003"
REPO_ROOT = Path(__file__).resolve().parents[2]
LOGIN_FIELDS = {
    "id",
    "tenant_id",
    "email",
    "name",
    "role",
    "password_hash",
    "is_active",
    "session_version",
}
# Rows of the migration tests and of the direct SQL test live in tenant ``t``.
ROW_TENANT = "t"
INSERT_USER = (
    "INSERT INTO users (id, tenant_id, email, password_hash, role, name, is_active) "
    "VALUES (:id, 't', :email, 'h', 'user', '', true)"
)
OwnerSql = Callable[..., list[Any]]


def _in_tenant(conn: Connection, tenant: str) -> None:
    """Scope this transaction to *tenant* (the RLS policies fail closed)."""
    conn.execute(text(TENANT_SQL), {"tenant": tenant})


def _hex() -> str:
    return uuid.uuid4().hex[:12]


# --- store ------------------------------------------------------------------


TEST_TENANT = "login-store-test"
PLAIN = "secret-pass"


@pytest.fixture
def store(postgres_url: str, owner_sql: OwnerSql) -> Iterator[PostgreSQLStore]:
    """Real store as the app role; the owner deletes the test users afterwards."""
    s = PostgreSQLStore()
    s.initialize()
    yield s
    s.close()
    owner_sql(TEST_TENANT, "DELETE FROM users WHERE tenant_id = :t", t=TEST_TENANT)


def _create(store: PostgreSQLStore, email: str) -> dict:
    with tenant_context(TEST_TENANT):
        return store.create_user(
            email=email, password=PLAIN, role="admin", tenant_id=TEST_TENANT, name="Admin"
        )


def test_login_lookup_returns_full_row(store: PostgreSQLStore) -> None:
    email = f"admin-{_hex()}@example.com"
    _create(store, email)

    row = store.get_login_user(f"  {email.upper()}")

    assert row is not None
    assert set(row) == LOGIN_FIELDS
    assert row["email"] == email
    assert row["password_hash"].startswith("$2")
    assert row["session_version"] == 0


def test_login_lookup_unknown_email_returns_none(store: PostgreSQLStore) -> None:
    assert store.get_login_user(f"nobody-{_hex()}@example.com") is None


def test_login_lookup_uses_no_pattern_matching(store: PostgreSQLStore) -> None:
    suffix = _hex()
    _create(store, f"a_b{suffix}@example.com")

    assert store.get_login_user(f"a%b{suffix}@example.com") is None


def test_login_lookup_raises_when_database_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_URL", "postgresql+psycopg://u:p@127.0.0.1:1/none")
    s = PostgreSQLStore()

    with pytest.raises(OperationalError):
        s.get_login_user("admin@example.com")


def test_logout_bump_makes_old_session_version_stale(store: PostgreSQLStore) -> None:
    email = f"admin-{_hex()}@example.com"
    created = _create(store, email)
    old = store.get_login_user(email)
    assert old is not None

    with tenant_context(TEST_TENANT):
        store.bump_session_version(created["id"])

    row = store.get_login_user(email)
    assert row is not None
    assert row["session_version"] == old["session_version"] + 1


def test_writes_are_normalised(store: PostgreSQLStore) -> None:
    local = f"Mixed{_hex()}"
    created = _create(store, f" {local}@Case.com ")

    assert created["email"] == f"{local.lower()}@case.com"
    with tenant_context(TEST_TENANT):
        found = store.get_user_by_email(f"{local.upper()}@CASE.COM")
    assert found is not None
    assert found["id"] == created["id"]


def test_direct_sql_cannot_store_non_normalised_email(
    store: PostgreSQLStore, postgres_url: str
) -> None:
    engine = create_engine(postgres_url, future=True)
    try:
        with engine.connect() as conn:
            _in_tenant(conn, ROW_TENANT)
            with pytest.raises(IntegrityError, match="ck_users_email_normalised"):
                conn.execute(text(INSERT_USER), {"id": _hex(), "email": f"UPPER{_hex()}@x.com"})
    finally:
        engine.dispose()


# --- migration and trigger (scratch database) -------------------------------


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


@pytest.fixture
def scratch(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[ScratchDb]:
    """Throwaway database at head, migrated by the owner, for one test.

    ``POSTGRES_URL`` and ``POSTGRES_OWNER_URL`` point at it, so Alembic migrates
    it as ``lawbyai_owner``. The superuser only creates and drops it.
    """
    with scratch_database("migusers") as db:
        monkeypatch.setenv("POSTGRES_URL", db.app_url)
        monkeypatch.setenv("POSTGRES_OWNER_URL", db.owner_url)
        command.upgrade(_alembic_config(), "head")
        yield db


@pytest.fixture
def engine(scratch: ScratchDb) -> Iterator[Engine]:
    """App-role engine on the scratch database; empty ``users`` and head afterwards."""
    eng = create_engine(scratch.app_url, future=True)
    yield eng
    eng.dispose()
    tenant_sql(scratch.owner_url, ROW_TENANT, "DELETE FROM users")
    command.upgrade(_alembic_config(), "head")


def _insert(scratch: ScratchDb, *emails: str) -> None:
    """Insert users in tenant ``t`` as the owner (the app has no grants below head)."""
    for email in emails:
        tenant_sql(scratch.owner_url, ROW_TENANT, INSERT_USER, id=_hex(), email=email)


def _users(scratch: ScratchDb) -> list[tuple]:
    """Read tenant ``t`` users as the owner (the app has no grants below head)."""
    rows = tenant_sql(scratch.owner_url, ROW_TENANT, "SELECT * FROM users ORDER BY email")
    return [tuple(r) for r in rows]


def _columns(engine: Engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("users")}


def _check_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM pg_constraint WHERE conname = 'ck_users_email_normalised'")
        ).scalar_one()


def test_migration_refuses_case_duplicate_emails(engine: Engine, scratch: ScratchDb) -> None:
    cfg = _alembic_config()
    command.downgrade(cfg, PREVIOUS_REVISION)
    _insert(scratch, "a@x.com", "A@x.com")
    before = _users(scratch)

    with pytest.raises(DBAPIError, match="collide"):
        command.upgrade(cfg, "head")

    assert _users(scratch) == before
    assert "session_version" not in _columns(engine)
    assert _check_count(engine) == 0


def test_migration_normalises_existing_emails(engine: Engine, scratch: ScratchDb) -> None:
    cfg = _alembic_config()
    command.downgrade(cfg, PREVIOUS_REVISION)
    _insert(scratch, " Mixed@X.com")

    command.upgrade(cfg, "head")

    with engine.begin() as conn:
        _in_tenant(conn, ROW_TENANT)
        row = conn.execute(text("SELECT email, session_version FROM users")).one()
    assert tuple(row) == ("mixed@x.com", 0)


@pytest.mark.parametrize(
    ("update", "expected"),
    [
        ("UPDATE users SET is_active = false", 1),
        ("UPDATE users SET password_hash = 'h2'", 1),
        ("UPDATE users SET is_active = false, password_hash = 'h2'", 1),
        ("UPDATE users SET name = 'renamed'", 0),
        ("UPDATE users SET is_active = true", 0),
    ],
)
def test_session_version_bumps_on_password_or_active_change(
    engine: Engine, scratch: ScratchDb, update: str, expected: int
) -> None:
    _insert(scratch, "bump@x.com")

    with engine.begin() as conn:
        _in_tenant(conn, ROW_TENANT)
        conn.execute(text(update))
        version = conn.execute(text("SELECT session_version FROM users")).scalar_one()

    assert version == expected


def test_downgrade_removes_objects_and_keeps_lowercase_emails(
    engine: Engine, scratch: ScratchDb
) -> None:
    _insert(scratch, "lower@x.com")

    command.downgrade(_alembic_config(), PREVIOUS_REVISION)

    with engine.connect() as conn:
        found = conn.execute(
            text(
                "SELECT (SELECT count(*) FROM pg_trigger "
                "WHERE tgname = 'trg_users_session_version'), "
                "(SELECT count(*) FROM pg_proc WHERE proname = 'users_bump_session_version'), "
                "(SELECT count(*) FROM pg_constraint WHERE conname = 'ck_users_email_normalised')"
            )
        ).one()
    assert tuple(found) == (0, 0, 0)
    assert "session_version" not in _columns(engine)
    assert [r[2] for r in _users(scratch)] == ["lower@x.com"]
