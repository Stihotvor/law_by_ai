"""Integration tests: the store ignores ``status`` on save and update.

``save_document`` inserts with ``needs_review`` and the upsert and update paths
never change ``status``. Each call logs one warning with the dropped key names,
never their values. Needs a live PostgreSQL; skipped when it is unreachable.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from factories.db_probe import can_connect
from sqlalchemy import create_engine, text

from config.settings import get_settings
from plugins.relational_db.postgres import PostgreSQLStore

pytestmark = pytest.mark.integration

_LOGGER = "plugins.relational_db.postgres"
_REPO_ROOT = Path(__file__).resolve().parents[3]
DocFactory = Callable[..., dict[str, Any]]


@pytest.fixture
def store() -> Iterator[PostgreSQLStore]:
    """Fresh store as the app role; the owner empties ``legal_document``."""
    if not can_connect(get_settings().postgres_url):
        pytest.skip("PostgreSQL unavailable")
    _owner_exec("TRUNCATE legal_document")
    s = PostgreSQLStore()
    s.initialize()
    yield s
    s.close()


@pytest.fixture
def make_document() -> DocFactory:
    """Factory for a minimal document dict without an id."""

    def _factory(**overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "title": "Untitled",
            "content": "Body",
            "source": "test",
            "source_url": "https://example.invalid/",
            "metadata": {"pages": 1},
            "is_processed": False,
            "tenant_id": "tenant-7",
        }
        return {**base, **overrides}

    return _factory


def _owner_exec(sql: str, **params: Any) -> None:
    """Run *sql* as the owner (the app role cannot set status or truncate)."""
    engine = create_engine(get_settings().postgres_owner_url, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text(sql), params)
    finally:
        engine.dispose()


def _set_status(doc_id: str, status: str) -> None:
    _owner_exec("UPDATE legal_document SET status = :s WHERE id = :i", s=status, i=doc_id)


def _stored_status(store: PostgreSQLStore, doc_id: str) -> str:
    fetched = store.get_document(doc_id)
    assert fetched is not None
    return fetched["status"]


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage() for r in caplog.records if r.name == _LOGGER and r.levelno == logging.WARNING
    ]


def test_update_cannot_change_status(store: PostgreSQLStore, make_document: DocFactory) -> None:
    doc_id = store.save_document(make_document())

    store.update_document(doc_id, {"status": "approved", "title": "x"})

    fetched = store.get_document(doc_id)
    assert fetched is not None
    assert fetched["status"] == "needs_review"
    assert fetched["title"] == "x"


def test_insert_ignores_status(
    store: PostgreSQLStore, make_document: DocFactory, caplog: pytest.LogCaptureFixture
) -> None:
    doc = make_document(id=str(uuid.uuid4()), status="approved")
    assert store.get_document(doc["id"]) is None
    caplog.set_level(logging.WARNING, logger=_LOGGER)

    doc_id = store.save_document(doc)

    assert _stored_status(store, doc_id) == "needs_review"
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "status" in warnings[0]
    assert "approved" not in warnings[0]


def test_insert_without_status_logs_no_warning(
    store: PostgreSQLStore, make_document: DocFactory, caplog: pytest.LogCaptureFixture
) -> None:
    doc = make_document()
    caplog.set_level(logging.WARNING, logger=_LOGGER)

    doc_id = store.save_document(doc)

    assert _stored_status(store, doc_id) == "needs_review"
    assert not [w for w in _warnings(caplog) if "status" in w]
    assert set(doc) == set(make_document()) | {"id"}


@pytest.mark.parametrize("value", ["needs_review", "approved"])
def test_upsert_keeps_stored_status(
    store: PostgreSQLStore, make_document: DocFactory, value: str
) -> None:
    doc = make_document()
    doc_id = store.save_document(doc)
    _set_status(doc_id, "approved")

    store.save_document({**doc, "status": value})

    assert _stored_status(store, doc_id) == "approved"


@pytest.mark.parametrize("value", ["bogus", "rejected", "", None])
def test_unknown_status_does_not_raise(
    store: PostgreSQLStore, make_document: DocFactory, value: str | None
) -> None:
    doc_id = store.save_document(make_document())

    store.update_document(doc_id, {"status": value})

    assert _stored_status(store, doc_id) == "needs_review"


def test_warning_names_keys_not_values(
    store: PostgreSQLStore, make_document: DocFactory, caplog: pytest.LogCaptureFixture
) -> None:
    doc_id = store.save_document(make_document())
    caplog.set_level(logging.WARNING, logger=_LOGGER)

    store.update_document(doc_id, {"status": "approved-secret", "foo": 1})

    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "status" in warnings[0]
    assert "foo" in warnings[0]
    assert "approved-secret" not in warnings[0]


def test_reads_still_return_status(store: PostgreSQLStore, make_document: DocFactory) -> None:
    doc_id = store.save_document(make_document())

    fetched = store.get_document(doc_id)

    assert fetched is not None
    assert fetched["status"] == "needs_review"


def test_validate_status_gone_and_no_new_migration() -> None:
    """Static check; needs no database."""
    hits = [
        p for p in (_REPO_ROOT / "src").rglob("*.py") if "validate_status" in p.read_text("utf-8")
    ]
    assert hits == []
    git = shutil.which("git")
    if git is None or not (_REPO_ROOT / ".git").exists():
        pytest.skip("git checkout not available for the migration check")
    out = subprocess.run(  # noqa: S603 - fixed argv: git from PATH and constant args
        [git, "status", "--porcelain", "migrations/versions"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert out == ""
