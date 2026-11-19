"""Reject audit is append only for the app role (migration ``81dde4a27be7``).

Marked ``integration``. ``lawbyai_app`` (``postgres_url``) must be denied
UPDATE, DELETE and TRUNCATE on ``rejected_document`` (SQLSTATE 42501) and keep
INSERT and SELECT. Each denied statement runs in its own transaction. The owner
``lawbyai_owner`` (``postgres_owner_url``) cleans test rows and runs the
Alembic round trip upgrade head, downgrade to ``b7e2d41c9a30``, upgrade head; head is always
restored. Skipped if PostgreSQL is unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from factories.db_probe import can_connect
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from config.settings import get_settings

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "b7e2d41c9a30"
APP_ROLE = "lawbyai_app"
TABLE = "public.rejected_document"
INSUFFICIENT_PRIVILEGE = "42501"
INSERT_ROW = (
    "INSERT INTO rejected_document (document_id, source_url, admin, rejected_at) "
    "VALUES (:doc, :url, 'priv-test', now())"
)
DENIED_SQL = {
    "UPDATE": "UPDATE rejected_document SET admin = 'x' WHERE source_url = :url",
    "DELETE": "DELETE FROM rejected_document WHERE source_url = :url",
    "TRUNCATE": "TRUNCATE rejected_document",
}
TABLE_PRIV_SQL = "SELECT has_table_privilege(:role, :table, :priv)"
COLUMN_PRIV_SQL = "SELECT has_any_column_privilege(:role, :table, 'UPDATE')"
PUBLIC_ACL_SQL = """
    SELECT count(*)
    FROM pg_class c, aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) acl
    WHERE c.oid = CAST(:table AS regclass) AND acl.grantee = 0
"""
PUBLIC_GRANTS_SQL = """
    SELECT count(*) FROM information_schema.role_table_grants
    WHERE table_schema = 'public' AND table_name = 'rejected_document'
      AND grantee = 'PUBLIC'
"""


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


def _app_url() -> str:
    url = get_settings().postgres_url
    if not can_connect(url):
        pytest.skip("PostgreSQL unavailable")
    return url


def _owner_url() -> str:
    url = get_settings().postgres_owner_url
    if not can_connect(url):
        pytest.skip("PostgreSQL unavailable (owner URL)")
    return url


def _run(db_url: str, sql: str, **params: Any) -> list[tuple[Any, ...]]:
    """Run *sql* in one transaction of its own and return plain tuples."""
    engine = create_engine(db_url, future=True)
    try:
        with engine.begin() as conn:
            result = conn.execute(text(sql), params)
            return [tuple(row) for row in result.all()] if result.returns_rows else []
    finally:
        engine.dispose()


def _scalar(db_url: str, sql: str, **params: Any) -> Any:
    return _run(db_url, sql, **params)[0][0]


def _sqlstate(error: ProgrammingError) -> str | None:
    orig = error.orig
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


def _has_table_privilege(url: str, priv: str) -> bool:
    return bool(_scalar(url, TABLE_PRIV_SQL, role=APP_ROLE, table=TABLE, priv=priv))


@pytest.fixture
def app_url() -> str:
    return _app_url()


@pytest.fixture
def owner_url() -> str:
    return _owner_url()


@pytest.fixture
def source_url(app_url: str, owner_url: str) -> Iterator[str]:
    """Unique source URL with one audit row; the owner removes its rows afterwards."""
    value = f"https://example.invalid/priv/{uuid.uuid4().hex}"
    _run(owner_url, INSERT_ROW, doc=f"priv-{uuid.uuid4().hex[:12]}", url=value)
    yield value
    _run(owner_url, "DELETE FROM rejected_document WHERE source_url = :url", url=value)


# --- privileges at head --------------------------------------------------------


@pytest.mark.parametrize("statement", ["UPDATE", "DELETE", "TRUNCATE"])
def test_app_role_is_denied(app_url: str, source_url: str, statement: str) -> None:
    """Scenario Outline: app role is denied (SQLSTATE 42501)."""
    with pytest.raises(ProgrammingError) as info:
        _run(app_url, DENIED_SQL[statement], url=source_url)
    assert _sqlstate(info.value) == INSUFFICIENT_PRIVILEGE
    assert (
        _scalar(
            app_url,
            "SELECT count(*) FROM rejected_document WHERE source_url = :url",
            url=source_url,
        )
        == 1
    )


def test_app_role_keeps_insert_and_select(app_url: str, source_url: str) -> None:
    """Scenario: app role keeps insert and select."""
    _run(app_url, INSERT_ROW, doc="priv-app", url=source_url)
    rows = _run(
        app_url, "SELECT admin FROM rejected_document WHERE source_url = :url", url=source_url
    )
    assert len(rows) == 2


# --- schema guard on the head schema -------------------------------------------


@pytest.mark.parametrize("priv", ["UPDATE", "DELETE", "TRUNCATE"])
def test_schema_guard_table_privilege_false(app_url: str, priv: str) -> None:
    """Scenario: schema guard (has_table_privilege)."""
    assert _has_table_privilege(app_url, priv) is False


def test_schema_guard_no_column_update(app_url: str) -> None:
    """Scenario: schema guard (has_any_column_privilege UPDATE)."""
    assert _scalar(app_url, COLUMN_PRIV_SQL, role=APP_ROLE, table=TABLE) is False


def test_schema_guard_public_has_no_privilege(app_url: str) -> None:
    """Scenario: schema guard (PUBLIC has no privilege on the table)."""
    assert _scalar(app_url, PUBLIC_ACL_SQL, table=TABLE) == 0
    assert _scalar(app_url, PUBLIC_GRANTS_SQL) == 0


# --- migration round trip as the owner -----------------------------------------


def _privileges(url: str) -> dict[str, bool]:
    return {priv: _has_table_privilege(url, priv) for priv in ("UPDATE", "DELETE", "TRUNCATE")}


def test_migration_round_trip(app_url: str, owner_url: str) -> None:
    """Scenario: migration round trip (upgrade, downgrade, upgrade)."""
    cfg = _alembic_config()
    try:
        command.upgrade(cfg, "head")
        command.downgrade(cfg, PREVIOUS_REVISION)
        assert _privileges(app_url) == {"UPDATE": True, "DELETE": True, "TRUNCATE": False}
        command.upgrade(cfg, "head")
        assert _privileges(app_url) == {"UPDATE": False, "DELETE": False, "TRUNCATE": False}
    finally:
        command.upgrade(cfg, "head")


def test_qa_006_sequence_grant_gives_distinct_ids(app_url: str, source_url: str) -> None:
    """QA-006: two app-role inserts without an id get two different ids."""
    ids = [
        _scalar(app_url, INSERT_ROW + " RETURNING id", doc=f"priv-seq-{n}", url=source_url)
        for n in range(2)
    ]
    assert ids[0] != ids[1]


def test_qa_007_owner_keeps_update_delete_truncate(owner_url: str, source_url: str) -> None:
    """QA-007: the owner can UPDATE, DELETE and TRUNCATE (rolled back at the end)."""
    engine = create_engine(owner_url, future=True)
    try:
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                updated = conn.execute(text(DENIED_SQL["UPDATE"]), {"url": source_url})
                assert updated.rowcount == 1
                deleted = conn.execute(text(DENIED_SQL["DELETE"]), {"url": source_url})
                assert deleted.rowcount == 1
                conn.execute(text(DENIED_SQL["TRUNCATE"]))
                assert conn.execute(text("SELECT count(*) FROM rejected_document")).scalar() == 0
            finally:
                trans.rollback()
    finally:
        engine.dispose()


def test_qa_011_existing_rows_survive_upgrade(app_url: str, owner_url: str) -> None:
    """QA-011: 5 rows written at the previous revision are intact after upgrade head."""
    cfg = _alembic_config()
    tag = uuid.uuid4().hex
    urls = [f"https://example.invalid/qa011/{tag}/{n}" for n in range(5)]
    try:
        command.upgrade(cfg, "head")
        command.downgrade(cfg, PREVIOUS_REVISION)
        for n, url in enumerate(urls):
            _run(owner_url, INSERT_ROW, doc=f"qa011-{tag[:8]}-{n}", url=url)
        command.upgrade(cfg, "head")
        rows = _run(
            owner_url,
            "SELECT document_id, source_url, admin FROM rejected_document "
            "WHERE source_url LIKE :pat ORDER BY source_url",
            pat=f"https://example.invalid/qa011/{tag}/%",
        )
        assert rows == [(f"qa011-{tag[:8]}-{n}", url, "priv-test") for n, url in enumerate(urls)]
    finally:
        command.upgrade(cfg, "head")
        _run(
            owner_url,
            "DELETE FROM rejected_document WHERE source_url LIKE :pat",
            pat=f"https://example.invalid/qa011/{tag}/%",
        )


def test_qa_015_repeated_upgrade_is_safe(app_url: str, owner_url: str) -> None:
    """QA-015: a second upgrade head is a no-op and the privileges stay revoked."""
    cfg = _alembic_config()
    command.upgrade(cfg, "head")
    before = _privileges(app_url)
    command.upgrade(cfg, "head")
    after = _privileges(app_url)
    assert before == after == {"UPDATE": False, "DELETE": False, "TRUNCATE": False}
