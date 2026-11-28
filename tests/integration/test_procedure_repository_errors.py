"""PostgresProcedureRepository error mapping against PostgreSQL.

A stored row that fails validation and a lock timeout both map to
``ProcedureStoreError``. The owner ``lawbyai_owner`` plants the bad row, holds
the row lock and removes the test procedures. Skipped if PostgreSQL is unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError

from core.procedures import Procedure, ProcedureStoreError, Step
from plugins.relational_db.procedures import PostgresProcedureRepository

pytestmark = pytest.mark.integration

ACTOR = "admin@example.com"
LOCK_NOT_AVAILABLE = "55P03"
SECRET = "Secret step text"  # noqa: S105 - test data


def _run(url: str, sql: str, **params: Any) -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(text(sql), params)
    finally:
        engine.dispose()


def _procedure(slug: str, step_text: str = "One.") -> Procedure:
    step = Step(
        key="step-0",
        text=step_text,
        source_url="https://example.gov.pl/pesel",
        last_checked=date(2026, 11, 1),
        verify_with_office="Ask the municipal office.",
    )
    return Procedure(schema_version=1, slug=slug, title="Get a PESEL", steps=(step,))


@pytest.fixture
def slug(owner_url: str) -> Iterator[str]:
    made = f"t4err-{uuid.uuid4().hex[:12]}"
    try:
        yield made
    finally:
        _run(
            owner_url,
            "DELETE FROM procedure_revision WHERE procedure_id IN "
            "(SELECT id FROM procedure WHERE slug = :slug)",
            slug=made,
        )
        _run(owner_url, "DELETE FROM procedure WHERE slug = :slug", slug=made)


@pytest.fixture
def repo(postgres_url: str) -> Iterator[PostgresProcedureRepository]:
    engine: Engine = create_engine(postgres_url)
    try:
        yield PostgresProcedureRepository(engine)
    finally:
        engine.dispose()


def test_invalid_stored_row_maps_to_store_error(
    repo: PostgresProcedureRepository, slug: str, owner_url: str
) -> None:
    """A row that passes the database checks but not the model raises ProcedureStoreError."""
    repo.save(_procedure(slug, step_text=SECRET), ACTOR)
    _run(
        owner_url,
        "UPDATE procedure_step SET source_url = 'https://example.gov.pl/a b' "
        "WHERE procedure_id = (SELECT id FROM procedure WHERE slug = :slug)",
        slug=slug,
    )
    with pytest.raises(ProcedureStoreError) as info:
        repo.get(slug)
    assert isinstance(info.value.__cause__, ValidationError)
    message = str(info.value)
    for secret in (SECRET, slug, "a b"):
        assert secret not in message


def test_lock_timeout_maps_to_store_error(
    repo: PostgresProcedureRepository, slug: str, owner_url: str
) -> None:
    """A save that waits longer than the lock timeout raises ProcedureStoreError."""
    repo.save(_procedure(slug), ACTOR)
    owner = create_engine(owner_url)
    try:
        with owner.begin() as conn:
            conn.execute(
                text("SELECT id FROM procedure WHERE slug = :slug FOR UPDATE"), {"slug": slug}
            )
            with pytest.raises(ProcedureStoreError) as info:
                repo.save(_procedure(slug, step_text="Two."), ACTOR)
    finally:
        owner.dispose()
    cause = info.value.__cause__
    assert isinstance(cause, OperationalError)
    assert getattr(cause.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE
    assert str(info.value) == "procedure store failed: save"
    assert repo.get(slug) == _procedure(slug).model_copy(update={"revision": 1})
