"""PostgreSQLStore backs the fetcher's RejectionChecker (issue #10).

Unit test: constructing the store does not connect, so no PostgreSQL instance is needed.
"""

from __future__ import annotations

import pytest

from agents.fetch.document_fetcher import DocumentFetcherAgent, RejectionChecker
from plugins.relational_db.postgres import PostgreSQLStore


def test_store_is_a_rejection_checker(monkeypatch: pytest.MonkeyPatch) -> None:
    store = PostgreSQLStore()

    def _no_db() -> None:
        raise AssertionError("store touched the database")

    monkeypatch.setattr(store, "initialize", _no_db)
    # pyright checks this assignment against the Protocol.
    checker: RejectionChecker = store

    assert callable(getattr(checker, "is_rejected", None))
    DocumentFetcherAgent(rejection=checker)
