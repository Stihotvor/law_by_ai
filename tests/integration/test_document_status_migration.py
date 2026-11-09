"""Document status column and reject audit table migration (issue #92).

Marked ``integration``: runs Alembic against a live PostgreSQL. The tests
downgrade the schema, so they never touch the configured database: the module
creates a dedicated scratch database (``mig92_<hex>``), points ``POSTGRES_URL``
at it, and drops it afterwards. Skipped if PostgreSQL is unreachable or the
role cannot create databases.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, create_engine, inspect, make_url, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from config.settings import get_settings
from data.models import Base

pytestmark = pytest.mark.integration

PREVIOUS_REVISION = "4439761c5e40"
REPO_ROOT = Path(__file__).resolve().parents[2]

INSERT_DOC = text(
    "INSERT INTO legal_document "
    "(id, title, content, source, source_url, last_updated, is_processed) "
    "VALUES (:id, 't', 'c', 'test', 'https://example.invalid/', now(), false)"
)
INSERT_DOC_WITH_STATUS = text(
    "INSERT INTO legal_document "
    "(id, title, content, source, source_url, last_updated, is_processed, status) "
    "VALUES (:id, 't', 'c', 'test', 'https://example.invalid/', now(), false, :status)"
)


def _can_connect(url: str) -> bool:
    """Return True when the database at the URL answers a query."""
    try:
        engine = create_engine(url, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


@pytest.fixture(scope="module")
def scratch_url() -> Iterator[str]:
    """URL of a throwaway database at head; ``POSTGRES_URL`` points at it."""
    base_url = get_settings().postgres_url
    if not _can_connect(base_url):
        pytest.skip("PostgreSQL unavailable")
    name = f"mig92_{uuid.uuid4().hex[:12]}"
    admin = create_engine(base_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except DBAPIError:
        admin.dispose()
        pytest.skip("cannot create a scratch database for migration tests")
    url = make_url(base_url).set(database=name).render_as_string(hide_password=False)
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("POSTGRES_URL", url)
            command.upgrade(_alembic_config(), "head")
            yield url
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def engine(scratch_url: str) -> Iterator[Engine]:
    """Engine on the scratch database; the schema is back at head afterwards."""
    eng = create_engine(scratch_url, future=True)
    yield eng
    eng.dispose()
    command.upgrade(_alembic_config(), "head")


def _doc_id() -> str:
    return f"mig92-{uuid.uuid4().hex[:12]}"


def _status(engine: Engine, doc_id: str) -> str:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT status FROM legal_document WHERE id = :id"), {"id": doc_id}
        ).scalar_one()


def test_scratch_database_is_not_the_configured_one(scratch_url: str) -> None:
    assert (make_url(scratch_url).database or "").startswith("mig92_")
    assert get_settings().postgres_url == scratch_url


def test_existing_rows_backfilled_to_approved(engine: Engine) -> None:
    cfg = _alembic_config()
    command.downgrade(cfg, PREVIOUS_REVISION)
    doc_id = _doc_id()
    with engine.begin() as conn:
        conn.execute(INSERT_DOC, {"id": doc_id})

    command.upgrade(cfg, "head")

    assert _status(engine, doc_id) == "approved"


def test_new_rows_default_to_needs_review(engine: Engine) -> None:
    doc_id = _doc_id()
    with engine.begin() as conn:
        conn.execute(INSERT_DOC, {"id": doc_id})

    assert _status(engine, doc_id) == "needs_review"


@pytest.mark.parametrize("bad_status", ["bogus", "rejected"])
def test_status_outside_allowed_values_rejected(engine: Engine, bad_status: str) -> None:
    with pytest.raises(IntegrityError, match="ck_legal_document_status"), engine.begin() as conn:
        conn.execute(INSERT_DOC_WITH_STATUS, {"id": _doc_id(), "status": bad_status})


def test_check_constraint_definition_and_validated(engine: Engine) -> None:
    with engine.connect() as conn:
        definition, validated = conn.execute(
            text(
                "SELECT pg_get_constraintdef(oid), convalidated FROM pg_constraint "
                "WHERE conname = 'ck_legal_document_status' "
                "AND conrelid = 'legal_document'::regclass"
            )
        ).one()

    assert definition.startswith("CHECK")
    assert "'needs_review'" in definition
    assert "'approved'" in definition
    assert "rejected" not in definition
    assert validated is True


def test_source_url_index_exists(engine: Engine) -> None:
    indexes = inspect(engine).get_indexes("rejected_document")
    assert {"name": "ix_rejected_document_source_url", "columns": ["source_url"]} in [
        {"name": ix["name"], "columns": ix["column_names"]} for ix in indexes
    ]


def test_downgrade_removes_column_and_table_then_upgrade_restores(engine: Engine) -> None:
    cfg = _alembic_config()

    command.downgrade(cfg, PREVIOUS_REVISION)
    after_down = inspect(engine)
    assert "status" not in {c["name"] for c in after_down.get_columns("legal_document")}
    assert not after_down.has_table("rejected_document")

    command.upgrade(cfg, "head")
    after_up = inspect(engine)
    assert "status" in {c["name"] for c in after_up.get_columns("legal_document")}
    assert after_up.has_table("rejected_document")


def test_autogenerate_finds_no_changes(engine: Engine) -> None:
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)

    assert diff == []


def test_rls_only_on_tenants_and_users(engine: Engine) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.relname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = current_schema() AND c.relkind = 'r' "
                "AND c.relrowsecurity"
            )
        ).scalars()
        assert set(rows) == {"tenants", "users"}
