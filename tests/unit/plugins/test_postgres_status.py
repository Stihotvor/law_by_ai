"""Status validation and reject errors in the PostgreSQL store (issue #92).

Unit tests: an unknown status must raise before the store touches the database,
so no PostgreSQL instance is needed.
"""

from __future__ import annotations

import pytest

from plugins.relational_db.postgres import PostgreSQLStore, StoreDocumentNotFoundError


def _doc(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "title": "t",
        "content": "c",
        "source": "test",
        "source_url": "https://example.invalid/",
    }
    return {**base, **overrides}


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> PostgreSQLStore:
    """Store whose initialize() fails loudly if the code reaches the database."""
    s = PostgreSQLStore()

    def _no_db() -> None:
        raise AssertionError("store touched the database")

    monkeypatch.setattr(s, "initialize", _no_db)
    return s


@pytest.mark.parametrize("bad", ["bogus", "rejected", "", None])
def test_save_document_rejects_unknown_status(store: PostgreSQLStore, bad: object) -> None:
    with pytest.raises(ValueError, match="Unknown document status"):
        store.save_document(_doc(status=bad))


@pytest.mark.parametrize("bad", ["bogus", "rejected"])
def test_update_document_rejects_unknown_status(store: PostgreSQLStore, bad: str) -> None:
    with pytest.raises(ValueError, match="Unknown document status"):
        store.update_document("any-id", {"status": bad})


def test_update_document_does_not_mutate_input_on_error(store: PostgreSQLStore) -> None:
    update = {"status": "bogus"}
    with pytest.raises(ValueError, match="Unknown document status"):
        store.update_document("any-id", update)
    assert update == {"status": "bogus"}


def test_not_found_error_is_lookup_error_not_value_error() -> None:
    assert issubclass(StoreDocumentNotFoundError, LookupError)
    assert not issubclass(StoreDocumentNotFoundError, ValueError)
