"""Login lookup, email normalisation and session version on the ``users`` table.

Marked ``integration``: runs against a live PostgreSQL. The store tests use the
configured database with unique emails. The migration tests downgrade the
schema, so they run in a scratch database (``migusers_<hex>``) that each test
creates and drops. Skipped if PostgreSQL is unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, inspect, make_url, text
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
INSERT_USER = text(
    "INSERT INTO users (id, tenant_id, email, password_hash, role, name, is_active) "
    "VALUES (:id, 't', :email, 'h', 'user', '', true)"
)


def _all_tenants(conn: Connection) -> None:
    """Make every ``users`` row visible to this transaction (RLS)."""
    conn.execute(text("SELECT set_config('app.current_tenant', '', true)"))


def _hex() -> str:
    return uuid.uuid4().hex[:12]


# --- store ------------------------------------------------------------------


TEST_TENANT = "login-store-test"
PLAIN = "secret-pass"


@pytest.fixture
def store(postgres_url: str) -> Iterator[PostgreSQLStore]:
    """Real store on the configured database; deletes the test users afterwards."""
    s = PostgreSQLStore()
    s.initialize()
    yield s
    s.close()
    engine = create_engine(postgres_url, future=True)
    with engine.begin() as conn:
        _all_tenants(conn)
        conn.execute(text("DELETE FROM users WHERE tenant_id = :t"), {"t": TEST_TENANT})
    engine.dispose()


def _create(store: PostgreSQLStore, email: str) -> dict:
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
    found = store.get_user_by_email(f"{local.upper()}@CASE.COM")
    assert found is not None
    assert found["id"] == created["id"]


def test_direct_sql_cannot_store_non_normalised_email(
    store: PostgreSQLStore, postgres_url: str
) -> None:
    engine = create_engine(postgres_url, future=True)
    try:
        with engine.connect() as conn:
            _all_tenants(conn)
            with pytest.raises(IntegrityError, match="ck_users_email_normalised"):
                conn.execute(INSERT_USER, {"id": _hex(), "email": f"UPPER{_hex()}@x.com"})
    finally:
        engine.dispose()


# --- migration and trigger (scratch database) -------------------------------


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


@pytest.fixture
def scratch_url(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """URL of a throwaway database at head; ``POSTGRES_URL`` points at it for one test."""
    base_url = postgres_url
    admin = create_engine(base_url, isolation_level="AUTOCOMMIT")
    name = f"migusers_{_hex()}"
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except DBAPIError:
        admin.dispose()
        pytest.skip("cannot create a scratch database for migration tests")
    url = make_url(base_url).set(database=name).render_as_string(hide_password=False)
    try:
        monkeypatch.setenv("POSTGRES_URL", url)
        command.upgrade(_alembic_config(), "head")
        yield url
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def engine(scratch_url: str) -> Iterator[Engine]:
    """Engine on an empty ``users`` table in the scratch database, at head afterwards."""
    eng = create_engine(scratch_url, future=True)
    yield eng
    with eng.begin() as conn:
        _all_tenants(conn)
        conn.execute(text("DELETE FROM users"))
    eng.dispose()
    command.upgrade(_alembic_config(), "head")


def _insert(engine: Engine, *emails: str) -> None:
    with engine.begin() as conn:
        _all_tenants(conn)
        for email in emails:
            conn.execute(INSERT_USER, {"id": _hex(), "email": email})


def _users(engine: Engine) -> list[tuple]:
    with engine.begin() as conn:
        _all_tenants(conn)
        return [tuple(r) for r in conn.execute(text("SELECT * FROM users ORDER BY email"))]


def _columns(engine: Engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("users")}


def _check_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM pg_constraint WHERE conname = 'ck_users_email_normalised'")
        ).scalar_one()


def test_migration_refuses_case_duplicate_emails(engine: Engine) -> None:
    cfg = _alembic_config()
    command.downgrade(cfg, PREVIOUS_REVISION)
    _insert(engine, "a@x.com", "A@x.com")
    before = _users(engine)

    with pytest.raises(DBAPIError, match="collide"):
        command.upgrade(cfg, "head")

    assert _users(engine) == before
    assert "session_version" not in _columns(engine)
    assert _check_count(engine) == 0


def test_migration_normalises_existing_emails(engine: Engine) -> None:
    cfg = _alembic_config()
    command.downgrade(cfg, PREVIOUS_REVISION)
    _insert(engine, " Mixed@X.com")

    command.upgrade(cfg, "head")

    with engine.begin() as conn:
        _all_tenants(conn)
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
    engine: Engine, update: str, expected: int
) -> None:
    _insert(engine, "bump@x.com")

    with engine.begin() as conn:
        _all_tenants(conn)
        conn.execute(text(update))
        version = conn.execute(text("SELECT session_version FROM users")).scalar_one()

    assert version == expected


def test_downgrade_removes_objects_and_keeps_lowercase_emails(engine: Engine) -> None:
    _insert(engine, "lower@x.com")

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
    assert [r[2] for r in _users(engine)] == ["lower@x.com"]
