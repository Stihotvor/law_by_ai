"""PostgreSQLStore.initialize() checks the Alembic head and never migrates (rls-201 T2).

A SQLite file stands in for the database: the check only reads
``alembic_version``. The tenant hook (``set_config``) is PostgreSQL-only, so
the tests replace it with a no-op.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from config.settings import get_settings
from plugins.relational_db import postgres
from plugins.relational_db.postgres import (
    Base,
    PostgreSQLStore,
    SchemaNotAtHeadError,
    Tenant,
)

ROOT = Path(__file__).resolve().parents[3]


def _revisions() -> tuple[str, str]:
    """Return the head revision and the one before it."""
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    assert head is not None
    previous = script.get_revision(head).down_revision
    assert isinstance(previous, str)
    return head, previous


@pytest.fixture
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Point the app URL at an empty SQLite file with a tenants table."""
    url = f"sqlite:///{tmp_path / 'store.db'}"
    monkeypatch.setenv("POSTGRES_URL", url)
    monkeypatch.setattr(postgres, "_set_tenant_setting", lambda _conn: None)
    engine = create_engine(url)
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[Tenant.__tablename__]])
    engine.dispose()
    get_settings.cache_clear()
    yield url
    get_settings.cache_clear()


def _stamp(url: str, revision: str) -> None:
    """Write one revision into ``alembic_version``."""
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version VALUES (:r)"), {"r": revision})
    engine.dispose()


def _schema(url: str) -> tuple[list[str], list[tuple[str, ...]]]:
    """Return the table names and the alembic_version rows."""
    engine = create_engine(url)
    with engine.connect() as conn:
        tables = sorted(inspect(conn).get_table_names())
        rows = [tuple(r) for r in conn.execute(text("SELECT version_num FROM alembic_version"))]
    engine.dispose()
    return tables, rows


def test_initialize_head_fails_on_database_behind_head(db_url: str) -> None:
    """Scenario: initialize() fails on a database not at head."""
    head, previous = _revisions()
    _stamp(db_url, previous)
    before = _schema(db_url)
    store = PostgreSQLStore()

    with pytest.raises(SchemaNotAtHeadError) as err:
        store.initialize()

    assert previous in str(err.value)
    assert head in str(err.value)
    assert _schema(db_url) == before
    store.close()


def test_initialize_head_passes_at_head(db_url: str) -> None:
    """Scenario: initialize() passes at head."""
    head, _ = _revisions()
    _stamp(db_url, head)
    store = PostgreSQLStore()

    store.initialize()

    assert store.list_tenants() == []
    store.close()
